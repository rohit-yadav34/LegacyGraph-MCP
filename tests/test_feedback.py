"""
Unit and integration tests for send_feedback and submit_feedback MCP tools.
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
    orig_token = config.GITHUB_TOKEN
    orig_repo = config.GITHUB_REPO
    orig_local_path = config.FEEDBACK_LOCAL_PATH

    temp_log = str(tmp_path / "feedback_test.jsonl")
    config.FEEDBACK_WEBHOOK_URL = ""
    config.GITHUB_TOKEN = ""
    config.GITHUB_REPO = "rohit-yadav34/LegacyGraph-MCP"
    config.FEEDBACK_LOCAL_PATH = temp_log

    yield tmp_path

    config.FEEDBACK_WEBHOOK_URL = orig_webhook
    config.GITHUB_TOKEN = orig_token
    config.GITHUB_REPO = orig_repo
    config.FEEDBACK_LOCAL_PATH = orig_local_path


def test_send_feedback_empty_message():
    """Empty or whitespace-only messages should be rejected."""
    res = send_feedback("")
    assert "Error: Feedback message cannot be empty" in res

    res2 = send_feedback("   \n\t  ")
    assert "Error: Feedback message cannot be empty" in res2


def test_send_feedback_invalid_target():
    """Invalid targets should return an informative error."""
    res = send_feedback("Some feedback", target="invalid_destination")
    assert "Error: Invalid target 'invalid_destination'" in res


def test_send_feedback_local_fallback_no_creds():
    """When no external creds exist in auto mode, feedback is saved to local log."""
    res = send_feedback(
        message="Please add support for Rust call graph analysis.",
        category="feature_request",
        email="dev@example.com",
    )

    assert "Feedback Submission Report" in res
    assert "Saved locally" in res
    assert "No external FEEDBACK_WEBHOOK_URL or GITHUB_TOKEN configured" in res

    # Verify JSONL entry was persisted
    log_file = Path(config.FEEDBACK_LOCAL_PATH)
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1
    data = json.loads(content[0])
    assert data["message"] == "Please add support for Rust call graph analysis."
    assert data["category"] == "feature_request"
    assert data["email"] == "dev@example.com"
    assert data["source"] == "LegacyGraph-MCP"


def test_send_feedback_explicit_local():
    """When target='local', feedback is recorded strictly to the local log."""
    res = send_feedback(
        message="Testing explicit local log.",
        category="bug",
        target="local",
    )

    assert "Feedback Logged Locally" in res
    assert "Feedback recorded to local storage." in res


def test_send_feedback_webhook_generic():
    """Webhook dispatch with generic JSON payload."""
    config.FEEDBACK_WEBHOOK_URL = "https://webhook.example.com/api"

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = send_feedback(
            message="Great tool for legacy code refactoring!",
            category="feedback",
            metadata={"source": "cli_agent"},
        )

        assert "Webhook accepted (HTTP 200)" in res
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["message"] == "Great tool for legacy code refactoring!"
        assert payload["category"] == "feedback"
        assert payload["metadata"] == {"source": "cli_agent"}


def test_send_feedback_webhook_discord():
    """Discord webhooks format with embeds and appropriate color."""
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    discord_url = "https://discord.com/api/webhooks/12345/abcdef"

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = send_feedback(
            message="Found memory spike in large AST parsing.",
            category="bug",
            webhook_url=discord_url,
        )

        assert "Webhook accepted (HTTP 204)" in res
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1
        assert payload["embeds"][0]["color"] == 0xE74C3C  # Red for bug
        assert "AST parsing" in payload["embeds"][0]["description"]


def test_send_feedback_webhook_slack():
    """Slack webhooks format with block kit."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    slack_url = "https://hooks.slack.com/services/T00/B00/XXXX"

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = send_feedback(
            message="Add support for exporting GraphML.",
            category="feature_request",
            webhook_url=slack_url,
        )

        assert "Webhook accepted (HTTP 200)" in res
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "blocks" in payload
        assert "GraphML" in payload["text"]


def test_send_feedback_webhook_failure():
    """Gracefully handle webhook server error or network exception."""
    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"

    with patch("httpx.Client.post", return_value=mock_resp):
        res = send_feedback(
            message="Testing failure resilience.",
            webhook_url="https://webhook.example.com/down",
        )

        assert "Webhook rejected (HTTP 502)" in res


def test_send_feedback_github_issue_success():
    """Creating a GitHub issue with authorization header and labels."""
    config.GITHUB_TOKEN = "ghp_mock_token_12345"
    config.GITHUB_REPO = "rohit-yadav34/LegacyGraph-MCP"

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "html_url": "https://github.com/rohit-yadav34/LegacyGraph-MCP/issues/99",
        "number": 99,
    }

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = send_feedback(
            message="Feature: Support Doxygen comment extraction.",
            category="feature_request",
            target="github",
            email="tester@domain.com",
        )

        assert "GitHub Issue #99 created" in res
        assert "https://github.com/rohit-yadav34/LegacyGraph-MCP/issues/99" in res

        # Verify request details
        call_args, call_kwargs = mock_post.call_args
        assert "https://api.github.com/repos/rohit-yadav34/LegacyGraph-MCP/issues" in call_args[0]
        assert call_kwargs["headers"]["Authorization"] == "Bearer ghp_mock_token_12345"
        payload = call_kwargs["json"]
        assert "[Feature_request]" in payload["title"]
        assert "enhancement" in payload["labels"]
        assert "tester@domain.com" in payload["body"]


def test_send_feedback_github_issue_missing_token():
    """If target='github' but GITHUB_TOKEN is not configured, report error."""
    config.GITHUB_TOKEN = ""
    res = send_feedback("My suggestion", target="github")
    assert "GITHUB_TOKEN is not configured" in res


def test_submit_feedback_alias():
    """submit_feedback functions as a direct alias for send_feedback."""
    res = submit_feedback("Testing alias function.", target="local")
    assert "Feedback Logged Locally" in res
    assert "Testing alias function" in res


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
