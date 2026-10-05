"""Password protection for the web pages (HTTP Basic auth)."""
import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def require_login(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    """Allow the request only if the username and password match the configured ones."""
    expected_username = os.environ.get("UI_USERNAME", "growth")
    expected_password = os.environ.get("UI_PASSWORD")

    # Fail closed: with no password configured, nobody gets in.
    if not expected_password:
        raise HTTPException(status_code=503, detail="UI_PASSWORD is not configured")

    # compare_digest takes the same time whether the guess is close or far off.
    username_ok = secrets.compare_digest(credentials.username.encode(), expected_username.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), expected_password.encode())
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="Wrong username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
