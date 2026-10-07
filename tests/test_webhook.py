import sqlite3
from datetime import datetime, timezone

import pytest

from app.db import SCHEMA
from app.webhook import AppEvent, process_event, sign, verify_signature


@pytest.fixture
def conn():
    """A throwaway database with one known app user (profile 1)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO profiles (id, email) VALUES (1, 'known@x.com')")
    conn.execute("INSERT INTO app_users VALUES ('u_known', 1, '2026-08-01')")
    return conn


def make(event_id, event="read_story", user_id=None, device_id="d_77", minute=0):
    return AppEvent(
        event_id=event_id, event=event, user_id=user_id, device_id=device_id,
        timestamp=datetime(2026, 9, 28, 14, minute, tzinfo=timezone.utc),
    )


def owner(conn, event_id):
    return conn.execute("SELECT profile_id FROM app_events WHERE event_id = ?", (event_id,)).fetchone()["profile_id"]


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_duplicate_event_is_stored_once(conn):
    assert process_event(conn, make("evt_A")) == "stored"
    assert process_event(conn, make("evt_A")) == "duplicate"
    assert count(conn, "app_events") == 1


def test_anonymous_event_stays_anonymous_until_login(conn):
    process_event(conn, make("evt_A"))
    assert owner(conn, "evt_A") is None


def test_login_attaches_earlier_anonymous_events(conn):
    process_event(conn, make("evt_A", minute=0))
    process_event(conn, make("evt_B", minute=2))
    process_event(conn, make("evt_C", event="login", user_id="u_known", minute=5))
    assert owner(conn, "evt_A") == 1
    assert owner(conn, "evt_B") == 1
    assert owner(conn, "evt_C") == 1


def test_late_anonymous_event_attaches_after_login(conn):
    """Out of order: happened before the login, but arrived after it."""
    process_event(conn, make("evt_C", event="login", user_id="u_known", minute=5))
    process_event(conn, make("evt_D", minute=3))
    assert owner(conn, "evt_D") == 1


def test_other_devices_are_not_affected(conn):
    process_event(conn, make("evt_X", device_id="d_other"))
    process_event(conn, make("evt_C", event="login", user_id="u_known", device_id="d_77"))
    assert owner(conn, "evt_X") is None


def test_unknown_user_gets_a_profile(conn):
    process_event(conn, make("evt_N", event="app_open", user_id="u_never_seen"))
    assert owner(conn, "evt_N") is not None
    assert owner(conn, "evt_N") != 1
    assert count(conn, "profiles") == 2
    # A second event from the same unknown user reuses that profile.
    process_event(conn, make("evt_N2", user_id="u_never_seen"))
    assert count(conn, "profiles") == 2
    assert owner(conn, "evt_N2") == owner(conn, "evt_N")


def test_good_signature_is_accepted():
    body = b'{"event_id": "evt_A"}'
    assert verify_signature("s3cret", "1000", sign("s3cret", "1000", body), body, now=1000) is None


def test_changed_body_is_refused():
    signature = sign("s3cret", "1000", b'{"event_id": "evt_A"}')
    assert verify_signature("s3cret", "1000", signature, b'{"event_id": "evt_HACKED"}', now=1000) is not None


def test_wrong_secret_is_refused():
    body = b"{}"
    assert verify_signature("s3cret", "1000", sign("guess", "1000", body), body, now=1000) is not None


def test_old_request_is_refused():
    body = b"{}"
    assert verify_signature("s3cret", "1000", sign("s3cret", "1000", body), body, now=1000 + 301) is not None


def test_missing_headers_are_refused():
    assert verify_signature("s3cret", None, None, b"{}") is not None
