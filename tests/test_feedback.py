"""
Unit and integration tests for Discord send_feedback and submit_feedback MCP tools.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.utils.config as config
from src.tools.feedback import send_feedback, submit_feedback


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


def test_send_feedback_discord_success():
    """Feedback successfully delivered to Discord webhook."""
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = send_feedback(
            message="Please add qualified name resolution file::Class::method.",
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
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert embed["color"] == 0x2ECC71  # Emerald green for feature_request
        assert "qualified name resolution" in embed["description"]

        # Local audit log check
        log_file = Path(config.FEEDBACK_LOCAL_PATH)
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["category"] == "feature_request"
        assert entry["email"] == "developer@example.com"


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


def test_send_feedback_discord_http_warning():
    """Handles non-200/204 HTTP status without raising unhandled exception."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("httpx.Client.post", return_value=mock_resp):
        res = send_feedback("Testing failure mode")
        assert "Feedback Submission Warning" in res
        assert "Discord webhook returned HTTP 500" in res


def test_send_feedback_network_exception():
    """Handles connection errors gracefully."""
    with patch("httpx.Client.post", side_effect=Exception("Connection timed out")):
        res = send_feedback("Testing timeout resilience")
        assert "Feedback Submission Warning" in res
        assert "Failed to reach Discord" in res
        assert "Preserved locally" in res


def test_send_feedback_no_webhook_url():
    """Warns if webhook URL is empty."""
    config.FEEDBACK_WEBHOOK_URL = ""
    res = send_feedback("Testing missing webhook")
    assert "Error: No webhook URL configured" in res
    assert "Saved feedback locally" in res


def test_submit_feedback_alias():
    """submit_feedback functions as a direct alias for send_feedback."""
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("httpx.Client.post", return_value=mock_resp):
        res = submit_feedback("Testing alias call")
        assert "Feedback Delivered to Discord" in res


def test_feedback_tools_registration_local_and_cloud():
    """Verify send_feedback and submit_feedback are registered in both local and cloud modes."""
    import asyncio
    from fastmcp import FastMCP
    from src.server import _register_tools

    for mode in ("local", "cloud"):
        srv = FastMCP(name=f"test-reg-{mode}")
        _register_tools(mode, server=srv)
        registered = list(asyncio.run(srv.get_tools()).keys())

        assert "send_feedback" in registered, f"send_feedback not registered in {mode} mode"
        assert "submit_feedback" in registered, f"submit_feedback not registered in {mode} mode"
