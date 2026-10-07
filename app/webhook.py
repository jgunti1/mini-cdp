"""Receive app events: check the signature, then store the event and work out whose it is."""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

MAX_AGE_SECONDS = 300      # reject requests signed more than 5 minutes ago (or in the future)
MAX_BODY_BYTES = 64_000


class AppEvent(BaseModel):
    """The shape of one event. Anything that does not fit is rejected before it is stored."""
    event_id: str = Field(min_length=1, max_length=100)
    event: Literal["app_open", "read_story", "link_click", "login"]
    user_id: str | None = Field(default=None, max_length=100)
    device_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    properties: dict = Field(default_factory=dict)


# ---------- signature ----------

def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The fingerprint of one request: HMAC-SHA256 over '<timestamp>.<body>'."""
    message = timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(secret, timestamp, signature, body, now=None):
    """Return None if the request is genuine, otherwise a short reason it was refused."""
    if not timestamp or not signature:
        return "missing signature headers"
    try:
        sent_at = int(timestamp)
    except ValueError:
        return "bad timestamp"
    now = time.time() if now is None else now
    if abs(now - sent_at) > MAX_AGE_SECONDS:
        return "timestamp too old"          # stops an old captured request being replayed
    expected = sign(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature):
        return "signature does not match"
    return None


def get_secret():
    return os.environ.get("WEBHOOK_SECRET")


# ---------- storing an event ----------

def profile_for_user(conn, user_id):
    """Return the profile for this app user. An unknown user_id gets a new profile."""
    found = conn.execute("SELECT profile_id FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
    if found:
        return found["profile_id"]
    profile_id = conn.execute("INSERT INTO profiles (email) VALUES (NULL)").lastrowid
    conn.execute(
        "INSERT INTO app_users (user_id, profile_id, created_at) VALUES (?, ?, NULL)",
        (user_id, profile_id),
    )
    return profile_id


def process_event(conn, event: AppEvent) -> str:
    """Store one event. Returns 'stored' or 'duplicate'."""
    # Rule: arrives twice -> the second copy changes nothing.
    already = conn.execute("SELECT 1 FROM app_events WHERE event_id = ?", (event.event_id,)).fetchone()
    if already:
        return "duplicate"

    device = conn.execute("SELECT profile_id FROM devices WHERE device_id = ?", (event.device_id,)).fetchone()

    if event.user_id:
        # Rule: unknown user_id -> still gets a profile.
        profile_id = profile_for_user(conn, event.user_id)
        if device is None:
            # First time this device shows a user: remember who it belongs to...
            conn.execute(
                "INSERT INTO devices (device_id, profile_id) VALUES (?, ?)",
                (event.device_id, profile_id),
            )
            # ...and attach the anonymous events it sent earlier.
            conn.execute(
                "UPDATE app_events SET profile_id = ?"
                " WHERE device_id = ? AND user_id IS NULL AND profile_id IS NULL",
                (profile_id, event.device_id),
            )
    else:
        # Anonymous event. If we already know the device (a late arrival), attach it now.
        profile_id = device["profile_id"] if device else None

    # Rule: out of order -> we keep the event's own timestamp and sort by it when showing.
    happened_at = event.timestamp
    if happened_at.tzinfo is not None:
        happened_at = happened_at.astimezone(timezone.utc)
    conn.execute(
        "INSERT INTO app_events"
        " (event_id, event, user_id, device_id, timestamp, properties, profile_id, received_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event.event_id,
            event.event,
            event.user_id,
            event.device_id,
            happened_at.strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(event.properties),
            profile_id,
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    return "stored"
