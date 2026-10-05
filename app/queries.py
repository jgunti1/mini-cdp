"""Read-only questions we ask the database."""
from app.normalize import normalize_email


def lookup_profile(conn, raw_email):
    """Return everything we know about the person with this email, or None if not found."""
    email = normalize_email(raw_email)  # clean it the same way the import did
    if email is None:
        return None

    # 1. Find the person.
    profile = conn.execute("SELECT id, email FROM profiles WHERE email = ?", (email,)).fetchone()
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

    return {
        "profile": profile,
        "subscriber": subscriber,
        "web_events": web_events,
        "app_users": app_users,
    }
