from app.importer import merge_subscriber


def make(signup, status, source, last_open):
    return {"signup_date": signup, "status": status,
            "acquisition_source": source, "last_open_date": last_open}


def test_merge_keeps_earliest_signup_and_its_source():
    existing = make("2026-08-20", "active", "facebook", None)
    merge_subscriber(existing, make("2026-07-05", "active", "instagram", None))
    assert existing["signup_date"] == "2026-07-05"
    assert existing["acquisition_source"] == "instagram"


def test_merge_keeps_latest_open():
    existing = make("2026-07-05", "active", "instagram", "2026-08-01")
    merge_subscriber(existing, make("2026-07-05", "active", "instagram", "2026-09-10"))
    assert existing["last_open_date"] == "2026-09-10"


def test_merge_keeps_an_open_date_over_no_open_date():
    existing = make("2026-07-05", "active", "instagram", "2026-08-01")
    merge_subscriber(existing, make("2026-07-05", "active", "instagram", None))
    assert existing["last_open_date"] == "2026-08-01"


def test_merge_unsubscribed_wins():
    existing = make("2026-07-05", "active", "instagram", None)
    merge_subscriber(existing, make("2026-07-05", "unsubscribed", "instagram", None))
    assert existing["status"] == "unsubscribed"

    existing = make("2026-07-05", "unsubscribed", "instagram", None)
    merge_subscriber(existing, make("2026-07-05", "active", "instagram", None))
    assert existing["status"] == "unsubscribed"
