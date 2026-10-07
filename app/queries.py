"""Read-only questions we ask the database."""
from app.normalize import normalize_email


def find_profile(conn, query):
    """Find a person by email, or by app user ID (for people whose email we don't know)."""
    email = normalize_email(query)  # clean it the same way the import did
    if email is not None:
        return conn.execute("SELECT id, email FROM profiles WHERE email = ?", (email,)).fetchone()
    return conn.execute(
        "SELECT p.id, p.email FROM profiles p JOIN app_users a ON a.profile_id = p.id"
        " WHERE a.user_id = ?",
        ((query or "").strip(),),
    ).fetchone()


def lookup_profile(conn, query):
    """Return everything we know about one person, or None if not found."""
    # 1. Find the person.
    profile = find_profile(conn, query)
    if profile is None:
        return None
    profile_id = profile["id"]

    # 2. Their newsletter info (None if they are not a subscriber).
    subscriber = conn.execute(
        "SELECT signup_date, status, acquisition_source, last_open_date"
        " FROM subscribers WHERE profile_id = ?",
        (profile_id,),
    ).fetchone()

    # 3. Their site visits, newest first.
    web_events = conn.execute(
        "SELECT page, timestamp, utm_source FROM web_events"
        " WHERE profile_id = ? ORDER BY timestamp DESC",
        (profile_id,),
    ).fetchall()

    # 4. Their app account(s).
    app_users = conn.execute(
        "SELECT user_id, created_at FROM app_users WHERE profile_id = ?",
        (profile_id,),
    ).fetchall()

    # 5. Their app activity from the webhook, newest first by when it happened.
    app_events = conn.execute(
        "SELECT event, timestamp, device_id, user_id, properties FROM app_events"
        " WHERE profile_id = ? ORDER BY timestamp DESC",
        (profile_id,),
    ).fetchall()

    return {
        "profile": profile,
        "subscriber": subscriber,
        "web_events": web_events,
        "app_users": app_users,
        "app_events": app_events,
    }
