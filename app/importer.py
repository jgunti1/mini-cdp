"""Load the three CSVs into the database. Run with: python -m app.importer"""
import csv
import json
from pathlib import Path

from app.db import get_connection, init_db
from app.normalize import normalize_email, normalize_source

DATA_DIR = Path("data")


def read_csv(filename):
    """Yield (row_number, row) for each row. Row 1 is the header, so data starts at 2."""
    with open(DATA_DIR / filename, newline="", encoding="utf-8") as f:
        for number, row in enumerate(csv.DictReader(f), start=2):
            yield number, row


def is_blank(row):
    return all((value or "").strip() == "" for value in row.values())


def reject(conn, filename, number, reason, row):
    conn.execute(
        "INSERT INTO rejected_rows (source_file, row_number, reason, raw_data) VALUES (?, ?, ?, ?)",
        (filename, number, reason, json.dumps(row)),
    )


def get_or_create_profile(conn, email):
    """Return the profile id for this normalized email, creating the profile if needed."""
    found = conn.execute("SELECT id FROM profiles WHERE email = ?", (email,)).fetchone()
    if found:
        return found["id"]
    return conn.execute("INSERT INTO profiles (email) VALUES (?)", (email,)).lastrowid


def merge_subscriber(existing, new):
    """Combine two rows for the same email, field by field (see DECISIONS.md)."""
    if new["signup_date"] < existing["signup_date"]:
        existing["signup_date"] = new["signup_date"]
        existing["acquisition_source"] = new["acquisition_source"]
    if (new["last_open_date"] or "") > (existing["last_open_date"] or ""):
        existing["last_open_date"] = new["last_open_date"]
    if new["status"] == "unsubscribed":
        existing["status"] = "unsubscribed"


def load_subscribers(conn):
    filename = "subscribers.csv"
    counts = {"rows": 0, "blank": 0, "rejected": 0, "duplicates_merged": 0}
    merged = {}  # normalized email -> cleaned subscriber

    for number, row in read_csv(filename):
        counts["rows"] += 1
        if is_blank(row):
            counts["blank"] += 1
            continue
        email = normalize_email(row["email"])
        if email is None:
            reject(conn, filename, number, "invalid_email", row)
            counts["rejected"] += 1
            continue
        cleaned = {
            "signup_date": row["signup_date"].strip(),
            "status": row["status"].strip().lower(),
            "acquisition_source": normalize_source(row["acquisition_source"]),
            "last_open_date": row["last_open_date"].strip() or None,
        }
        if email in merged:
            merge_subscriber(merged[email], cleaned)
            counts["duplicates_merged"] += 1
        else:
            merged[email] = cleaned

    for email, sub in merged.items():
        profile_id = get_or_create_profile(conn, email)
        conn.execute(
            "INSERT INTO subscribers (profile_id, signup_date, status, acquisition_source, last_open_date)"
            " VALUES (?, ?, ?, ?, ?)",
            (profile_id, sub["signup_date"], sub["status"], sub["acquisition_source"], sub["last_open_date"]),
        )
    counts["loaded"] = len(merged)
    return counts


def load_app_users(conn):
    filename = "app_users.csv"
    counts = {"rows": 0, "blank": 0, "rejected": 0, "loaded": 0}

    for number, row in read_csv(filename):
        counts["rows"] += 1
        if is_blank(row):
            counts["blank"] += 1
            continue
        email = normalize_email(row["email"])
        if email is None:
            reject(conn, filename, number, "invalid_email", row)
            counts["rejected"] += 1
            continue
        profile_id = get_or_create_profile(conn, email)
        conn.execute(
            "INSERT OR IGNORE INTO app_users (user_id, profile_id, created_at) VALUES (?, ?, ?)",
            (row["user_id"].strip(), profile_id, row["created_at"].strip()),
        )
        counts["loaded"] += 1
    return counts


def load_web_events(conn):
    filename = "web_events.csv"
    counts = {"rows": 0, "blank": 0, "loaded": 0, "linked": 0}
    rows = [(number, row) for number, row in read_csv(filename)]

    # Pass 1: learn which visitor belongs to which person.
    visitor_profile = {}  # visitor_id -> profile id
    for number, row in rows:
        email = normalize_email(row["email"])
        if email is not None and row["visitor_id"] not in visitor_profile:
            visitor_profile[row["visitor_id"]] = get_or_create_profile(conn, email)

    # Pass 2: store every visit, attaching the person when the visitor is known.
    for number, row in rows:
        counts["rows"] += 1
        if is_blank(row):
            counts["blank"] += 1
            continue
        profile_id = visitor_profile.get(row["visitor_id"])
        conn.execute(
            "INSERT INTO web_events (visitor_id, page, timestamp, utm_source, profile_id) VALUES (?, ?, ?, ?, ?)",
            (row["visitor_id"], row["page"], row["timestamp"], normalize_source(row["utm_source"]), profile_id),
        )
        counts["loaded"] += 1
        if profile_id is not None:
            counts["linked"] += 1
    return counts


def run_import():
    """Load the CSVs. Safe to run again: it never deletes people.

    Subscribers, web events and rejects come only from the CSVs, so they are cleared
    and reloaded. Profiles and app users are kept and added to, because the webhook
    also creates them and those people are in no CSV.
    """
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM web_events")
    conn.execute("DELETE FROM subscribers")
    conn.execute("DELETE FROM rejected_rows")
    report = {
        "subscribers": load_subscribers(conn),
        "app_users": load_app_users(conn),
        "web_events": load_web_events(conn),
    }
    report["profiles"] = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    conn.commit()
    conn.close()
    return report


if __name__ == "__main__":
    for name, counts in run_import().items():
        print(name, counts)
