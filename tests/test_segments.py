import sqlite3

import pytest

from app.db import SCHEMA
from app.segments import build_segment


@pytest.fixture
def conn():
    """A small throwaway database with five hand-made subscribers."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    people = [
        # email, signup, status, source, last_open
        ("cold@x.com", "2026-07-01", "active", "instagram", "2026-08-01"),
        ("warm@x.com", "2026-07-01", "active", "instagram", "2026-09-20"),
        ("never@x.com", "2026-07-01", "active", "instagram", None),
        ("gone@x.com", "2026-07-01", "unsubscribed", "instagram", "2026-08-01"),
        ("fb@x.com", "2026-07-01", "active", "facebook", "2026-08-01"),
    ]
    for number, (email, signup, status, source, last_open) in enumerate(people, start=1):
        conn.execute("INSERT INTO profiles (id, email) VALUES (?, ?)", (number, email))
        conn.execute(
            "INSERT INTO subscribers VALUES (?, ?, ?, ?, ?)",
            (number, signup, status, source, last_open),
        )
    conn.execute("INSERT INTO app_users VALUES ('u_1', 1, '2026-07-02')")
    return conn


def emails(rows):
    return sorted(row["email"] for row in rows)


def test_instagram_not_opened_in_30_days(conn):
    rows = build_segment(conn, source="instagram", engagement="not_opened_in_days", days=30)
    assert emails(rows) == ["cold@x.com"]


def test_unsubscribed_are_excluded_by_default(conn):
    assert "gone@x.com" not in emails(build_segment(conn))


def test_never_opened_is_its_own_filter(conn):
    assert emails(build_segment(conn, engagement="never_opened")) == ["never@x.com"]


def test_source_is_normalized(conn):
    assert emails(build_segment(conn, source=" Instagram ")) == ["cold@x.com", "never@x.com", "warm@x.com"]


def test_has_app_filter(conn):
    assert emails(build_segment(conn, has_app="yes")) == ["cold@x.com"]


def test_unknown_filter_value_is_rejected(conn):
    with pytest.raises(ValueError):
        build_segment(conn, status="active; DROP TABLE subscribers")
