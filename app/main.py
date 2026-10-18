from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine, SessionLocal, ensure_columns
from . import models  # noqa: F401  (register tables)
from .seed import seed
from .services import scheduler
from .routers import auth, leads, templates, clients, dashboard, discover, proposals, whatsapp_webhook, payments, updates, agreements
from .common import KIND_RE

STATIC = Path(__file__).parent / "static"


def startup_warnings() -> list[str]:
    out = []
    if settings.SECRET_KEY in ("dev-secret-change-me", "change-me-to-a-64-char-random-string") or len(settings.SECRET_KEY) < 32:
        out.append("SECRET_KEY is the default or shorter than 32 chars — set a random 64-char value in .env")
    if settings.ADMIN_PASSWORD == "ChangeMe123!":
        out.append("ADMIN_PASSWORD is the example value — change it (and the admin password in Settings)")
    if settings.ALLOWED_ORIGINS.strip() in ("", "*") and not settings.DATABASE_URL.startswith("sqlite"):
        out.append("ALLOWED_ORIGINS is '*' on a non-dev database — set it to your https origin")
    if settings.WHATSAPP_TOKEN and not settings.WHATSAPP_APP_SECRET:
        out.append("WHATSAPP_APP_SECRET is empty — inbound webhook posts are rejected until it is set")
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    for warning in startup_warnings():
        print("SECURITY WARNING:", warning)
    Base.metadata.create_all(bind=engine)
    added = ensure_columns(engine)
    if added:
        print("schema: added columns", ", ".join(added))
    with SessionLocal() as db:
        seed(db)
    if settings.SCHEDULER_ENABLED:
        scheduler.start(SessionLocal)
    yield
    scheduler.stop()


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return resp


for r in (auth.router, leads.router, templates.router, clients.router, dashboard.router, discover.router, proposals.router, whatsapp_webhook.router, payments.router, updates.router, agreements.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.APP_NAME}


app.mount("/static", StaticFiles(directory=STATIC), name="static")
UPLOADS = Path(settings.UPLOAD_DIR); UPLOADS.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")


@app.get("/demo/{kind}", include_in_schema=False)
def demo(kind: str):
    """Sample websites shared with leads. Personalised via ?n=<name>&c=<city>&p=<phone>&s=<sector> (see services.whatsapp.personal_demo)."""
    f = STATIC / "demo" / f"{kind}.html" if KIND_RE.match(kind) else None
    if not f or not f.is_file():
        f = STATIC / "demo" / "business.html"
    return FileResponse(f, headers={"Cache-Control": "public, max-age=300", "X-Frame-Options": "SAMEORIGIN"})


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str, request: Request):
    # A client's custom domain pointed at this server serves their live site at /
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host and path in ("", "index.html") and proposals.is_custom_domain(host):
        with SessionLocal() as db:
            return proposals.render_live_by_domain(host, request, db)
    return FileResponse(STATIC / "index.html")
