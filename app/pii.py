"""Keeping personal data away from the AI model.

Two jobs:
  scrub_text     - remove emails and IDs from text a person typed, before it is sent.
  assert_no_pii  - a final check on everything about to be sent; it refuses if anything slipped through.
"""
import json
import re

# An email anywhere inside a longer piece of text.
EMAIL_IN_TEXT = re.compile(r"[^\s@\"'<>(),;:]+@[^\s@\"'<>(),;:]+\.[A-Za-z]{2,}")
# Our own identifiers: app users (u_), devices (d_), web visitors (v_), events (evt_).
ID_IN_TEXT = re.compile(r"\b(?:u|d|v|evt)_[0-9A-Za-z]{4,}\b")


class PIILeak(Exception):
    """Raised when something identifying is about to be sent to the model."""


def scrub_text(text: str) -> tuple[str, bool]:
    """Return (cleaned text, whether anything was removed)."""
    cleaned = EMAIL_IN_TEXT.sub("[email removed]", text)
    cleaned = ID_IN_TEXT.sub("[id removed]", cleaned)
    return cleaned, cleaned != text


def assert_no_pii(payload) -> None:
    """Refuse to continue if the payload contains an email or one of our IDs."""
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    if EMAIL_IN_TEXT.search(text) or ID_IN_TEXT.search(text):
        raise PIILeak("Blocked: personal data was about to be sent to the model.")
