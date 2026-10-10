from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # read settings from a local .env file, if there is one

import os
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import ValidationError
from fastapi.templating import Jinja2Templates

from app import assistant
from app.auth import require_login
from app.pii import PIILeak
from app.db import get_connection, init_db
from app.importer import run_import
from app.queries import lookup_profile
from app.insights import CHANNEL_RULES, channel_report
from app.segments import build_segment, list_sources
from app.webhook import MAX_BODY_BYTES, AppEvent, get_secret, process_event, verify_signature


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts: make sure the tables exist and have data."""
    init_db()
    conn = get_connection()
    is_empty = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 0
    conn.close()
    if is_empty:
        run_import()
    yield


app = FastAPI(title="Mini CDP", lifespan=lifespan)
templates = Jinja2Templates(directory="app/templates")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", dependencies=[Depends(require_login)])
def home(request: Request, email: str = ""):
    # "email" is the search box: it accepts an email or an app user ID.
    searched = email.strip() != ""
    result = None
    if searched:
        conn = get_connection()
        result = lookup_profile(conn, email)
        conn.close()
    return templates.TemplateResponse(
        request, "index.html", {"email": email, "searched": searched, "result": result}
    )


@app.get("/segments", dependencies=[Depends(require_login)])
def segments(
    request: Request,
    source: str = "any",
    status: str = "active",
    engagement: str = "any",
    days: int = 30,
    has_app: str = "any",
    run: str = "",
):
    conn = get_connection()
    sources = list_sources(conn)
    rows = None
    error = None
    if run:
        try:
            rows = build_segment(conn, source, status, engagement, days, has_app)
        except ValueError:
            error = "One of the filters has a value this page does not recognize."
    conn.close()
    filters = {"source": source, "status": status, "engagement": engagement, "days": days, "has_app": has_app}
    return templates.TemplateResponse(
        request, "segments.html", {"sources": sources, "filters": filters, "rows": rows, "error": error}
    )


@app.get("/channels", dependencies=[Depends(require_login)])
def channels(request: Request):
    conn = get_connection()
    report = channel_report(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "channels.html", {"report": report, "rules": CHANNEL_RULES}
    )


@app.get("/assistant", dependencies=[Depends(require_login)])
def assistant_page(request: Request, q: str = ""):
    question = q.strip()[:500]
    result = None
    error = None
    if question:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            error = "The assistant is not configured: ANTHROPIC_API_KEY is not set."
        else:
            conn = get_connection()
            try:
                result = assistant.answer_question(conn, question)
            except PIILeak as leak:
                error = str(leak)
            except Exception as problem:  # the AI service was unreachable, refused the key, etc.
                error = f"The assistant could not answer right now ({type(problem).__name__}: {str(problem)[:300]})."
            finally:
                conn.close()
    return templates.TemplateResponse(
        request, "assistant.html", {"question": question, "result": result, "error": error}
    )


@app.post("/webhooks/app")
async def app_webhook(request: Request):
    """Receive one event from the mobile app."""
    secret = get_secret()
    if not secret:
        # Fail closed: with no secret configured, nothing is accepted.
        raise HTTPException(status_code=503, detail="WEBHOOK_SECRET is not configured")

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large")

    # 1. Is it really from the app? Check the signature over the exact bytes received.
    problem = verify_signature(
        secret,
        request.headers.get("X-Webhook-Timestamp"),
        request.headers.get("X-Webhook-Signature"),
        body,
    )
    if problem:
        raise HTTPException(status_code=401, detail=f"Signature check failed: {problem}")

    # 2. Is it shaped like an event?
    try:
        event = AppEvent.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_url=False, include_input=False))

    # 3. Store it. Everything for one event is saved together or not at all.
    conn = get_connection()
    try:
        result = process_event(conn, event)
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        result = "duplicate"  # the same event arrived twice at the same moment
    finally:
        conn.close()
    return {"status": result, "event_id": event.event_id}
