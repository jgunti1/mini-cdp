"""Questions the assistant can ask the database, beyond a plain segment."""
from app.config import TODAY

BREAKDOWNS = {
    "source": "COALESCE(s.acquisition_source, 'unknown')",
    "status": "s.status",
    "signup_month": "substr(s.signup_date, 1, 7)",
}


def breakdown(conn, dimension, status="active"):
    """Count subscribers per source, status or signup month."""
    if dimension not in BREAKDOWNS:
        raise ValueError("unknown dimension")
    if status not in ("active", "unsubscribed", "any"):
        raise ValueError("unknown status")
    column = BREAKDOWNS[dimension]  # fixed text from the dictionary above, never user input
    where, params = ("1 = 1", []) if status == "any" else ("s.status = ?", [status])
    return conn.execute(
        f"SELECT {column} AS label, COUNT(*) AS subscribers FROM subscribers s"
        f" WHERE {where} GROUP BY label ORDER BY subscribers DESC",
        params,
    ).fetchall()


def first_pages(conn, signup_from=None):
    """For subscribers who signed up on or after a date, the first page each one visited."""
    signup_from = signup_from or _days_ago(30)
    return conn.execute(
        """
        SELECT w.page AS label, COUNT(*) AS subscribers
        FROM subscribers s
        JOIN web_events w ON w.id = (
            SELECT id FROM web_events
            WHERE profile_id = s.profile_id
            ORDER BY timestamp, id LIMIT 1
        )
        WHERE s.signup_date >= ?
        GROUP BY w.page ORDER BY subscribers DESC
        """,
        (signup_from,),
    ).fetchall()


# How "engaged" is scored. Written here once so the page, the assistant and the README agree.
ENGAGEMENT_RULE = (
    "Score = 5 if they opened an email in the last 7 days"
    " + 1 per site visit in the last 30 days"
    " + 2 per app event in the last 30 days. Active subscribers only."
)


def most_engaged(conn, limit=25):
    """Active subscribers ranked by the engagement score above."""
    limit = max(1, min(int(limit), 100))
    return conn.execute(
        """
        SELECT p.email, s.acquisition_source, s.last_open_date,
               (CASE WHEN s.last_open_date >= date(:today, '-7 days') THEN 5 ELSE 0 END)
               + (SELECT COUNT(*) FROM web_events w
                  WHERE w.profile_id = s.profile_id AND w.timestamp >= date(:today, '-30 days'))
               + 2 * (SELECT COUNT(*) FROM app_events e
                      WHERE e.profile_id = s.profile_id AND e.timestamp >= date(:today, '-30 days'))
               AS score
        FROM subscribers s JOIN profiles p ON p.id = s.profile_id
        WHERE s.status = 'active'
        ORDER BY score DESC, p.email
        LIMIT :limit
        """,
        {"today": TODAY, "limit": limit},
    ).fetchall()


def _days_ago(days):
    from datetime import date, timedelta
    return (date.fromisoformat(TODAY) - timedelta(days=days)).isoformat()


# ---------- Channel quality: which sources bring readers who stay? ----------

CHANNEL_MIN_DAYS = 30      # only count people who have had at least this long to drift away
SMALL_SAMPLE = 200         # groups smaller than this are flagged, not judged

CHANNEL_RULES = (
    f"Counts subscribers who signed up at least {CHANNEL_MIN_DAYS} days before {TODAY},"
    " so everyone has had the same chance to go cold."
    " 'Stayed' = still subscribed and opened an email in the last 30 days."
    f" Channels with fewer than {SMALL_SAMPLE} subscribers are marked as a small sample."
)


def channel_report(conn):
    """One row per acquisition source, best 'stayed' rate first."""
    rows = conn.execute(
        """
        SELECT COALESCE(acquisition_source, 'unknown') AS channel,
               COUNT(*) AS subscribers,
               SUM(status = 'active' AND last_open_date >= date(:today, '-30 days')) AS stayed,
               SUM(status = 'active' AND last_open_date <  date(:today, '-30 days')) AS gone_cold,
               SUM(status = 'active' AND last_open_date IS NULL) AS never_opened,
               SUM(status = 'unsubscribed') AS unsubscribed
        FROM subscribers
        WHERE signup_date <= date(:today, :min_age)
        GROUP BY channel
        """,
        {"today": TODAY, "min_age": f"-{CHANNEL_MIN_DAYS} days"},
    ).fetchall()

    total = sum(row["subscribers"] for row in rows)
    report = []
    for row in rows:
        n = row["subscribers"]
        report.append({
            "channel": row["channel"],
            "subscribers": n,
            "share_of_total": round(100 * n / total, 1) if total else 0.0,
            "stayed_pct": round(100 * row["stayed"] / n, 1),
            "gone_cold_pct": round(100 * row["gone_cold"] / n, 1),
            "never_opened_pct": round(100 * row["never_opened"] / n, 1),
            "unsubscribed_pct": round(100 * row["unsubscribed"] / n, 1),
            "small_sample": n < SMALL_SAMPLE,
        })
    report.sort(key=lambda item: item["stayed_pct"], reverse=True)
    return report
