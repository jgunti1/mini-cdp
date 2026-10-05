import pytest
from app.normalize import normalize_email, normalize_source


@pytest.mark.parametrize("raw, expected", [
    ("sam@gmail.com", "sam@gmail.com"),
    ("Sam@Gmail.Com", "sam@gmail.com"),
    ("  sam@gmail.com ", "sam@gmail.com"),
    ("not-an-email", None),
    ("@gmail.com", None),
    ("", None),
    (None, None),
])
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Instagram", "instagram"),
    ("instagram", "instagram"),
    ("twitter", "x"),
    ("X", "x"),
    ("", None),
])
def test_normalize_source(raw, expected):
    assert normalize_source(raw) == expected