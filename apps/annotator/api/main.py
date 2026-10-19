from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from apps.annotator.api.routes import router
from apps.annotator.api.services import seed_default_model
from apps.annotator.config import get_settings
from apps.annotator.db.session import get_db

# SPA shell must always revalidate so deploys pick up new hashed /assets/*.js
_HTML_NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
# Vite content-hashed bundles are safe to cache forever
_ASSET_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


class _AssetCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/assets/"):
            for key, value in _ASSET_CACHE.items():
                response.headers[key] = value
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    db = next(get_db())
    try:
        seed_default_model(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MoTranscript", version="0.1.0", lifespan=lifespan)
    # SessionMiddleware must be added before CORS so cookies are set correctly.
    https_only = bool(settings.public_base_url.startswith("https://"))
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="motranscript_session",
        max_age=14 * 24 * 60 * 60,
        same_site="lax",
        https_only=https_only,
    )
    allow_origins = [
        "http://localhost:8010",
        "http://127.0.0.1:8010",
    ]
    if settings.public_base_url:
        origin = settings.public_base_url.rstrip("/")
        if origin and origin not in allow_origins:
            allow_origins.append(origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(_AssetCacheMiddleware)
    app.include_router(router)

    web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if web_dist.exists():
        assets = web_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        index = web_dist / "index.html"

        @app.get("/")
        async def spa_root() -> FileResponse:
            if not index.is_file():
                raise HTTPException(status_code=404, detail="Frontend not built")
            return FileResponse(index, headers=_HTML_NO_CACHE)

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            """SPA deep links (/login, /sources, …) — refresh must serve index.html."""
            candidate = (web_dist / full_path).resolve()
            try:
                candidate.relative_to(web_dist.resolve())
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Not Found") from exc
            if candidate.is_file():
                # HTML must not be cached; other root files (favicon) use browser defaults
                if candidate.suffix.lower() == ".html":
                    return FileResponse(candidate, headers=_HTML_NO_CACHE)
                return FileResponse(candidate)
            if index.is_file():
                return FileResponse(index, headers=_HTML_NO_CACHE)
            raise HTTPException(status_code=404, detail="Frontend not built")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "apps.annotator.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )


if __name__ == "__main__":
    run()
