"""Build a segment: a list of subscribers matching a set of filters."""
from app.config import TODAY
from app.normalize import normalize_source

STATUSES = ("active", "unsubscribed", "any")
ENGAGEMENTS = ("any", "not_opened_in_days", "never_opened")
APP_CHOICES = ("any", "yes", "no")


def list_sources(conn):
    rows = conn.execute(
        "SELECT DISTINCT acquisition_source FROM subscribers"
        " WHERE acquisition_source IS NOT NULL ORDER BY acquisition_source"
    ).fetchall()
    return [row["acquisition_source"] for row in rows]


def build_segment(conn, source="any", status="active", engagement="any", days=30, has_app="any"):
    """Return the subscribers matching the filters, as a list of rows.

    Every value the user chose is passed to the database as a ? parameter.
    The only text added to the SQL comes from the fixed strings written below.
    """
    if status not in STATUSES or engagement not in ENGAGEMENTS or has_app not in APP_CHOICES:
        raise ValueError("unknown filter value")

    conditions = []
    params = []

    if source != "any":
        conditions.append("s.acquisition_source = ?")
        params.append(normalize_source(source))

    # Default is active only, so unsubscribed people stay out unless asked for.
    if status != "any":
        conditions.append("s.status = ?")
        params.append(status)

    if engagement == "not_opened_in_days":
        # Opened at some point, but not within the last N days.
        # People who never opened are excluded here (NULL fails the comparison);
        # they have their own filter below. See DECISIONS.md.
        conditions.append("s.last_open_date < date(?, ?)")
        params.extend([TODAY, f"-{int(days)} days"])
    elif engagement == "never_opened":
        conditions.append("s.last_open_date IS NULL")

    if has_app == "yes":
        conditions.append("EXISTS (SELECT 1 FROM app_users a WHERE a.profile_id = s.profile_id)")
    elif has_app == "no":
        conditions.append("NOT EXISTS (SELECT 1 FROM app_users a WHERE a.profile_id = s.profile_id)")

    where = " AND ".join(conditions) if conditions else "1 = 1"
    sql = (
        "SELECT p.email, s.signup_date, s.status, s.acquisition_source, s.last_open_date"
        " FROM subscribers s JOIN profiles p ON p.id = s.profile_id"
        f" WHERE {where} ORDER BY s.signup_date DESC, p.email"
    )
    return conn.execute(sql, params).fetchall()
