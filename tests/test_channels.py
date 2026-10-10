import sqlite3

from app.db import SCHEMA
from app.insights import channel_report


def make_db(people):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for number, (source, signup, status, last_open) in enumerate(people, start=1):
        conn.execute("INSERT INTO profiles (id, email) VALUES (?, ?)", (number, f"p{number}@x.com"))
        conn.execute("INSERT INTO subscribers VALUES (?, ?, ?, ?, ?)", (number, signup, status, source, last_open))
    return conn


def test_recent_signups_are_left_out():
    conn = make_db([
        ("instagram", "2026-07-01", "active", "2026-09-20"),
        ("instagram", "2026-09-25", "active", "2026-09-26"),  # too new to judge
    ])
    report = channel_report(conn)
    assert report[0]["subscribers"] == 1


def test_percentages_and_order():
    conn = make_db([
        ("referral", "2026-07-01", "active", "2026-09-20"),       # stayed
        ("referral", "2026-07-01", "active", "2026-09-21"),       # stayed
        ("x", "2026-07-01", "active", "2026-08-01"),              # gone cold
        ("x", "2026-07-01", "unsubscribed", "2026-08-01"),        # unsubscribed
    ])
    report = channel_report(conn)
    assert [row["channel"] for row in report] == ["referral", "x"]
    assert report[0]["stayed_pct"] == 100.0
    assert report[1]["gone_cold_pct"] == 50.0
    assert report[1]["unsubscribed_pct"] == 50.0
    assert report[0]["share_of_total"] == 50.0
    assert all(row["small_sample"] for row in report)
