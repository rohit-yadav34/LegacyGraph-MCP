"""
Unit and integration tests for Discord send_feedback MCP tool.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.utils.config as config
from src.tools.feedback import send_feedback


@pytest.fixture(autouse=True)
def _reset_env_and_temp_file(tmp_path: Path):
    """Ensure clean config and temporary local feedback destination for tests."""
    orig_webhook = config.FEEDBACK_WEBHOOK_URL
    orig_local_path = config.FEEDBACK_LOCAL_PATH

    temp_log = str(tmp_path / "feedback_test.jsonl")
    config.FEEDBACK_WEBHOOK_URL = config.DISCORD_FEEDBACK_WEBHOOK
    config.FEEDBACK_LOCAL_PATH = temp_log

    yield tmp_path

    config.FEEDBACK_WEBHOOK_URL = orig_webhook
    config.FEEDBACK_LOCAL_PATH = orig_local_path


def test_send_feedback_empty_message():
    """Empty or whitespace-only messages should be rejected."""
    res = send_feedback("")
    assert "Error: Feedback message cannot be empty" in res

    res2 = send_feedback("   \n\t  ")
    assert "Error: Feedback message cannot be empty" in res2


def test_send_feedback_discord_success_no_local_fallback():
    """On success, feedback goes straight to Discord without touching fallback file."""
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = send_feedback(
            message="Add qualified name resolution file::Class::method.",
            category="feature_request",
            email="developer@example.com",
            metadata={"client": "antigravity-ide"},
        )

        assert "Feedback Delivered to Discord" in res
        assert "Successfully delivered to Discord channel." in res
        assert mock_post.called

        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == config.DISCORD_FEEDBACK_WEBHOOK
        payload = call_kwargs["json"]
        assert payload["username"] == "LegacyGraph MCP"
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert embed["color"] == 0x2ECC71  # Emerald green for feature_request
        assert "qualified name resolution" in embed["description"]

        # Successful Discord send does not create a local fallback file
        log_file = Path(config.FEEDBACK_LOCAL_PATH)
        assert not log_file.exists()


def test_send_feedback_discord_bug_color():
    """Bug reports use red embed color."""
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = send_feedback(
            message="Found memory leak on 100k line AST.",
            category="bug",
        )

        assert "Feedback Delivered to Discord" in res
        payload = mock_post.call_args[1]["json"]
        assert payload["embeds"][0]["color"] == 0xE74C3C  # Red for bug


def test_send_feedback_discord_failure_triggers_fallback():
    """When Discord returns an error (HTTP 404/500), it falls back to saving locally."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = '{"message": "Unknown Webhook", "code": 10015}'

    with patch("httpx.Client.post", return_value=mock_resp):
        res = send_feedback("Testing fallback on Discord 404")
        assert "Feedback Delivery Failed (Saved Locally as Fallback)" in res
        assert "HTTP 404" in res

        # Verify fallback saved to local file
        log_file = Path(config.FEEDBACK_LOCAL_PATH)
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["message"] == "Testing fallback on Discord 404"


def test_send_feedback_network_exception_triggers_fallback():
    """When network times out or fails, it falls back to saving locally."""
    with patch("httpx.Client.post", side_effect=Exception("Connection timed out")):
        res = send_feedback("Testing timeout fallback")
        assert "Feedback Delivery Failed (Saved Locally as Fallback)" in res
        assert "Connection Error" in res

        log_file = Path(config.FEEDBACK_LOCAL_PATH)
        assert log_file.exists()


def test_send_feedback_no_webhook_url_saves_locally():
    """When no webhook URL is configured, saves locally and informs the user."""
    config.FEEDBACK_WEBHOOK_URL = ""
    res = send_feedback("Testing missing webhook")
    assert "Feedback Saved Locally (No Webhook Configured)" in res

    log_file = Path(config.FEEDBACK_LOCAL_PATH)
    assert log_file.exists()


def test_feedback_tool_registration_local_and_cloud():
    """Verify send_feedback is registered in both local and cloud modes."""
    import asyncio
    from fastmcp import FastMCP
    from src.server import _register_tools

    for mode in ("local", "cloud"):
        srv = FastMCP(name=f"test-reg-{mode}")
        _register_tools(mode, server=srv)
        registered = list(asyncio.run(srv.get_tools()).keys())

        assert "send_feedback" in registered, f"send_feedback not registered in {mode} mode"
        assert "submit_feedback" not in registered, "submit_feedback should no longer be registered"
