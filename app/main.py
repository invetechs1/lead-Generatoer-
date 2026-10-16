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
from .routers import auth, leads, templates, clients, dashboard, discover, proposals, whatsapp_webhook, payments, updates

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
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


for r in (auth.router, leads.router, templates.router, clients.router, dashboard.router, discover.router, proposals.router, whatsapp_webhook.router, payments.router, updates.router):
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
    f = STATIC / "demo" / f"{kind}.html"
    if not f.is_file():
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
