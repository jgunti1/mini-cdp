from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # read settings from a local .env file, if there is one

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates

from app.auth import require_login
from app.db import get_connection, init_db
from app.importer import run_import
from app.queries import lookup_profile
from app.segments import build_segment, list_sources


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
