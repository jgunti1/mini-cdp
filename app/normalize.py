"""Shared normalization. Anything that 
compares emails or sources must go through here."""
import re

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SOURCE_ALIASES = {"twitter": "x"}


def normalize_email(raw: str | None) -> str | None:
    """Return the cleaned email, or None if it is blank or not a valid address."""
    if raw is None:
        return None
    email = raw.strip().lower()
    if not EMAIL_PATTERN.match(email):
        return None
    return email


def normalize_source(raw: str | None) -> str | None:
    """Return the cleaned source name, or None if blank."""
    if raw is None:
        return None
    source = raw.strip().lower()
    if source == "":
        return None
    return SOURCE_ALIASES.get(source, source)