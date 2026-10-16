"""
Feedback and Feature Request MCP tools.

Allows coding agents or human users to submit feedback, bug reports,
or feature requests directly to configured webhooks (Discord, Slack, custom HTTP),
GitHub Issues, or a local audit log.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Optional
import uuid

import httpx

import src.utils.config as config
from src.utils.logger import logger

_FILE_LOCK = threading.Lock()


def _format_discord_payload(
    feedback_id: str,
    title: str,
    message: str,
    category: str,
    email: Optional[str],
    metadata: Optional[dict[str, Any]],
    timestamp: str,
) -> dict[str, Any]:
    """Build a rich embed payload suitable for Discord webhooks."""
    color_map = {
        "feature_request": 0x2ECC71,  # Green
        "bug": 0xE74C3C,              # Red
        "feedback": 0x3498DB,         # Blue
        "general": 0x9B59B6,          # Purple
    }
    color = color_map.get(category.lower(), 0x3498DB)

    fields: list[dict[str, Any]] = [
        {"name": "Category", "value": category, "inline": True},
        {"name": "Submitter", "value": email or "Anonymous", "inline": True},
        {"name": "Feedback ID", "value": f"`{feedback_id}`", "inline": True},
    ]

    if metadata:
        meta_str = json.dumps(metadata, indent=2)
        if len(meta_str) > 500:
            meta_str = meta_str[:497] + "..."
        fields.append({"name": "Metadata", "value": f"```json\n{meta_str}\n```", "inline": False})

    return {
        "content": f"New **{category}** submitted via LegacyGraph-MCP",
        "embeds": [
            {
                "title": title[:250],
                "description": message[:2000],
                "color": color,
                "fields": fields,
                "footer": {"text": "LegacyGraph-MCP Feedback System"},
                "timestamp": timestamp,
            }
        ],
    }


def _format_slack_payload(
    feedback_id: str,
    title: str,
    message: str,
    category: str,
    email: Optional[str],
    metadata: Optional[dict[str, Any]],
    timestamp: str,
) -> dict[str, Any]:
    """Build a Block Kit payload suitable for Slack incoming webhooks."""
    text_summary = f"[{category.upper()}] {title}: {message}"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"New {category.capitalize()}: {title[:90]}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Message:*\n{message}\n\n"
                    f"*Category:* `{category}` | *Contact:* {email or 'Anonymous'} | "
                    f"*ID:* `{feedback_id}`"
                ),
            },
        },
    ]

    if metadata:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Metadata:* `{json.dumps(metadata)}`",
                    }
                ],
            }
        )

    return {"text": text_summary, "blocks": blocks}


def _format_generic_payload(
    feedback_id: str,
    title: str,
    message: str,
    category: str,
    email: Optional[str],
    metadata: Optional[dict[str, Any]],
    timestamp: str,
) -> dict[str, Any]:
    """Build a standard JSON payload for generic webhooks."""
    return {
        "id": feedback_id,
        "title": title,
        "message": message,
        "category": category,
        "email": email,
        "metadata": metadata or {},
        "timestamp": timestamp,
        "source": "LegacyGraph-MCP",
    }


def _send_to_webhook(url: str, payload_dict: dict[str, Any]) -> tuple[bool, str]:
    """Post feedback payload to a webhook URL with provider-specific formatting."""
    try:
        lower_url = url.lower()
        if "discord.com/api/webhooks" in lower_url:
            body = _format_discord_payload(
                feedback_id=payload_dict["id"],
                title=payload_dict["title"],
                message=payload_dict["message"],
                category=payload_dict["category"],
                email=payload_dict.get("email"),
                metadata=payload_dict.get("metadata"),
                timestamp=payload_dict["timestamp"],
            )
        elif "hooks.slack.com" in lower_url:
            body = _format_slack_payload(
                feedback_id=payload_dict["id"],
                title=payload_dict["title"],
                message=payload_dict["message"],
                category=payload_dict["category"],
                email=payload_dict.get("email"),
                metadata=payload_dict.get("metadata"),
                timestamp=payload_dict["timestamp"],
            )
        else:
            body = payload_dict

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=body)
            if resp.status_code in (200, 201, 202, 204):
                return True, f"Webhook accepted (HTTP {resp.status_code})"
            return False, f"Webhook rejected (HTTP {resp.status_code}): {resp.text[:200]}"
    except Exception as exc:
        logger.warning(f"Failed to deliver feedback to webhook: {exc}")
        return False, f"Webhook connection error: {str(exc)}"


def _send_to_github(
    repo: str,
    token: str,
    title: str,
    message: str,
    category: str,
    feedback_id: str,
    email: Optional[str],
    metadata: Optional[dict[str, Any]],
    timestamp: str,
) -> tuple[bool, str]:
    """Create a GitHub Issue for the feedback or feature request."""
    try:
        url = f"https://api.github.com/repos/{repo}/issues"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "LegacyGraph-MCP",
        }

        # Build issue body in Markdown
        body_lines = [
            "### Description",
            message,
            "",
            "---",
            "### Submission Details",
            f"- **Feedback ID**: `{feedback_id}`",
            f"- **Category**: `{category}`",
            f"- **Submitter**: {email or 'Anonymous'}",
            f"- **Submitted At**: `{timestamp}`",
        ]
        if metadata:
            body_lines.append(f"- **Metadata**:\n```json\n{json.dumps(metadata, indent=2)}\n```")

        # Pick labels
        labels = ["feedback"]
        cat_lower = category.lower()
        if cat_lower == "bug":
            labels.append("bug")
        elif cat_lower in ("feature_request", "feature", "enhancement"):
            labels.append("enhancement")

        issue_data = {
            "title": f"[{category.capitalize()}] {title}",
            "body": "\n".join(body_lines),
            "labels": labels,
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=issue_data)
            if resp.status_code == 201:
                data = resp.json()
                issue_url = data.get("html_url", "")
                issue_num = data.get("number", "")
                return True, f"GitHub Issue #{issue_num} created: {issue_url}"
            return False, f"GitHub API error (HTTP {resp.status_code}): {resp.text[:200]}"
    except Exception as exc:
        logger.warning(f"Failed to create GitHub issue: {exc}")
        return False, f"GitHub request error: {str(exc)}"


def _save_local_feedback(entry: dict[str, Any]) -> tuple[bool, str]:
    """Append the feedback entry to a local JSONL audit file."""
    try:
        filepath = Path(config.FEEDBACK_LOCAL_PATH)
        with _FILE_LOCK:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return True, str(filepath)
    except Exception as exc:
        logger.error(f"Failed to record local feedback: {exc}")
        return False, str(exc)


def send_feedback(
    message: str,
    category: str = "feedback",
    title: Optional[str] = None,
    target: Optional[str] = None,
    email: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    webhook_url: Optional[str] = None,
    github_repo: Optional[str] = None,
) -> str:
    """
    Send feedback, bug reports, or feature requests directly to a webhook or GitHub issue.

    Dispatches the message to configured endpoints (webhook, GitHub Issues, or local
    audit log). Designed for both human developers and coding agents to submit ideas,
    edge-case findings, or feature requests programmatically.

    Args:
        message: The feedback content, bug description, or feature request details (required).
        category: Type of submission: 'feature_request', 'bug', 'feedback', or 'general'.
        title: Short summary/title. If not provided, the first line of message is used.
        target: Dispatch destination: 'auto' (default), 'webhook', 'github', or 'local'.
        email: Optional contact email or user identifier.
        metadata: Optional dictionary of context (e.g. project_id, environment, tool name).
        webhook_url: Optional runtime webhook URL override (overrides FEEDBACK_WEBHOOK_URL).
        github_repo: Optional runtime GitHub repository override (e.g. 'owner/repo').

    Returns:
        A formatted status message detailing where the feedback was dispatched.
    """
    cleaned_message = (message or "").strip()
    if not cleaned_message:
        return "Error: Feedback message cannot be empty."

    resolved_title = (title or "").strip()
    if not resolved_title:
        # Use first non-empty line as title, capped at 80 characters
        first_line = cleaned_message.splitlines()[0].strip()
        resolved_title = first_line[:77] + "..." if len(first_line) > 80 else first_line

    feedback_id = f"fb_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    entry = {
        "id": feedback_id,
        "title": resolved_title,
        "message": cleaned_message,
        "category": category,
        "email": email,
        "metadata": metadata or {},
        "timestamp": now_iso,
        "source": "LegacyGraph-MCP",
    }

    # Always persist locally for audit & reliability
    saved_local, local_info = _save_local_feedback(entry)

    resolved_target = (target or "auto").strip().lower()
    if resolved_target not in ("auto", "webhook", "github", "local"):
        return f"Error: Invalid target '{target}'. Expected 'auto', 'webhook', 'github', or 'local'."

    # If target is explicitly local, return immediately
    if resolved_target == "local":
        if saved_local:
            return (
                f"### Feedback Logged Locally\n"
                f"- **ID**: `{feedback_id}`\n"
                f"- **Category**: `{category}`\n"
                f"- **Title**: {resolved_title}\n"
                f"- **Log File**: `{local_info}`\n\n"
                f"Feedback recorded to local storage."
            )
        return f"Error recording local feedback: {local_info}"

    active_webhook = (webhook_url or config.FEEDBACK_WEBHOOK_URL).strip()
    active_token = config.GITHUB_TOKEN.strip()
    active_repo = (github_repo or config.GITHUB_REPO).strip()

    actions_taken: list[str] = []
    errors: list[str] = []

    # Handle Webhook dispatch
    should_send_webhook = (resolved_target == "webhook") or (
        resolved_target == "auto" and bool(active_webhook)
    )
    if should_send_webhook:
        if not active_webhook:
            errors.append("Webhook dispatch failed: No webhook URL configured or provided.")
        else:
            success, msg = _send_to_webhook(active_webhook, entry)
            if success:
                actions_taken.append(f"Webhook: {msg}")
            else:
                errors.append(f"Webhook: {msg}")

    # Handle GitHub Issue dispatch
    should_send_github = (resolved_target == "github") or (
        resolved_target == "auto" and bool(active_token)
    )
    if should_send_github:
        if not active_token:
            errors.append("GitHub Issue creation failed: GITHUB_TOKEN is not configured.")
        else:
            success, msg = _send_to_github(
                repo=active_repo,
                token=active_token,
                title=resolved_title,
                message=cleaned_message,
                category=category,
                feedback_id=feedback_id,
                email=email,
                metadata=metadata,
                timestamp=now_iso,
            )
            if success:
                actions_taken.append(f"GitHub: {msg}")
            else:
                errors.append(f"GitHub: {msg}")

    # Handle Auto mode when neither external endpoint is configured
    if resolved_target == "auto" and not active_webhook and not active_token:
        actions_taken.append(
            f"Saved locally to `{local_info}` (No external FEEDBACK_WEBHOOK_URL or GITHUB_TOKEN configured)."
        )

    # Format result report
    lines = [
        "### Feedback Submission Report",
        f"- **ID**: `{feedback_id}`",
        f"- **Category**: `{category}`",
        f"- **Title**: {resolved_title}",
    ]

    if actions_taken:
        lines.append("- **Dispatched To**:")
        for action in actions_taken:
            lines.append(f"  - {action}")

    if errors:
        lines.append("- **Dispatch Warnings / Errors**:")
        for err in errors:
            lines.append(f"  - {err}")

    if saved_local and resolved_target != "auto":
        lines.append(f"- **Local Audit Record**: `{local_info}`")

    return "\n".join(lines)


def submit_feedback(
    message: str,
    category: str = "feedback",
    title: Optional[str] = None,
    target: Optional[str] = None,
    email: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    webhook_url: Optional[str] = None,
    github_repo: Optional[str] = None,
) -> str:
    """
    Alias for send_feedback.

    Submits feedback, bug reports, or feature requests directly to a webhook or GitHub issue.
    """
    return send_feedback(
        message=message,
        category=category,
        title=title,
        target=target,
        email=email,
        metadata=metadata,
        webhook_url=webhook_url,
        github_repo=github_repo,
    )
