"""
Discord Feedback and Feature Request MCP tool for LegacyGraph-MCP.

Sends feedback, bug reports, and feature requests directly to Discord.
If delivery to Discord fails or no webhook is configured, it falls back
to saving the feedback locally so nothing is ever lost.
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
    """Build a rich embed payload formatted for Discord incoming webhooks."""
    color_map = {
        "feature_request": 0x2ECC71,  # Emerald Green
        "feature": 0x2ECC71,
        "enhancement": 0x2ECC71,
        "bug": 0xE74C3C,              # Red
        "feedback": 0x3498DB,         # Blue
        "general": 0x9B59B6,          # Purple
    }
    color = color_map.get(category.lower(), 0x3498DB)

    fields: list[dict[str, Any]] = [
        {"name": "Category", "value": category, "inline": True},
        {"name": "Contact", "value": email or "Anonymous", "inline": True},
        {"name": "Feedback ID", "value": f"`{feedback_id}`", "inline": True},
    ]

    if metadata:
        meta_str = json.dumps(metadata, indent=2)
        if len(meta_str) > 500:
            meta_str = meta_str[:497] + "..."
        fields.append({"name": "Metadata", "value": f"```json\n{meta_str}\n```", "inline": False})

    return {
        "username": "LegacyGraph MCP",
        "content": f"New **{category}** submitted via LegacyGraph-MCP",
        "embeds": [
            {
                "title": title[:250],
                "description": message[:2000],
                "color": color,
                "fields": fields,
                "footer": {"text": "LegacyGraph-MCP • Discord Feedback"},
                "timestamp": timestamp,
            }
        ],
    }


def _save_local_feedback(entry: dict[str, Any]) -> tuple[bool, str]:
    """Append the feedback entry to a local JSONL audit file on fallback."""
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
    email: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    webhook_url: Optional[str] = None,
) -> str:
    """
    Send feedback, bug reports, or feature requests directly to Discord.

    Sends the message to the configured Discord webhook. If the webhook
    is unavailable or fails, it automatically saves to local feedback storage
    as a fallback.

    Args:
        message: The feedback content, bug description, or feature request details (required).
        category: Type of submission: 'feature_request', 'bug', 'feedback', or 'general'.
        title: Short summary/title. If not provided, extracted from the first line of message.
        email: Optional contact email or user identifier.
        metadata: Optional dictionary of context (e.g. project_id, environment, tool name).
        webhook_url: Optional webhook URL override (defaults to FEEDBACK_WEBHOOK_URL).

    Returns:
        A formatted confirmation message indicating delivery status.
    """
    cleaned_message = (message or "").strip()
    if not cleaned_message:
        return "Error: Feedback message cannot be empty."

    resolved_title = (title or "").strip()
    if not resolved_title:
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

    active_webhook = (webhook_url or config.FEEDBACK_WEBHOOK_URL).strip()
    if not active_webhook:
        _saved, local_path = _save_local_feedback(entry)
        return (
            f"### Feedback Saved Locally (No Webhook Configured)\n"
            f"- **ID**: `{feedback_id}`\n"
            f"- **Category**: `{category}`\n"
            f"- **Title**: {resolved_title}\n"
            f"- **Local Fallback File**: `{local_path}`\n\n"
            f"Note: Configure FEEDBACK_WEBHOOK_URL to send directly to Discord."
        )

    # Build Discord embed payload
    payload = _format_discord_payload(
        feedback_id=feedback_id,
        title=resolved_title,
        message=cleaned_message,
        category=category,
        email=email,
        metadata=metadata,
        timestamp=now_iso,
    )

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(active_webhook, json=payload)
            if resp.status_code in (200, 204):
                return (
                    f"### Feedback Delivered to Discord\n"
                    f"- **ID**: `{feedback_id}`\n"
                    f"- **Category**: `{category}`\n"
                    f"- **Title**: {resolved_title}\n"
                    f"- **Status**: Successfully delivered to Discord channel."
                )

            # Failure: Fall back to local file
            _saved, local_path = _save_local_feedback(entry)
            return (
                f"### Feedback Delivery Failed (Saved Locally as Fallback)\n"
                f"- **ID**: `{feedback_id}`\n"
                f"- **Discord Error**: HTTP {resp.status_code} ({resp.text[:200]})\n"
                f"- **Fallback Record**: Preserved locally in `{local_path}`."
            )
    except Exception as exc:
        logger.warning(f"Failed to deliver feedback to Discord: {exc}")
        _saved, local_path = _save_local_feedback(entry)
        return (
            f"### Feedback Delivery Failed (Saved Locally as Fallback)\n"
            f"- **ID**: `{feedback_id}`\n"
            f"- **Connection Error**: {str(exc)}\n"
            f"- **Fallback Record**: Preserved locally in `{local_path}`."
        )
