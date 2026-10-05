from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # read settings from a local .env file, if there is one

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates

from app.auth import require_login
from app.db import get_connection, init_db
from app.importer import run_import
from app.queries import lookup_profile


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
