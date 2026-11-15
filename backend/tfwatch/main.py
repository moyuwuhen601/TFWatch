from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import accounts, admin, catalog, notifications
from .config import Config
from .db import database
from .security import RateLimiter


def create_app(config=None):
    config = config or Config()
    app = FastAPI(title="TFWatch", docs_url=None, openapi_url="/api/openapi.json", redoc_url=None)
    app.state.config = config
    app.state.sessions = database(config.database_url)
    app.state.limiter = RateLimiter()

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        fields = [".".join(str(part) for part in issue["loc"][1:]) for issue in error.errors()]
        return JSONResponse({"detail": "请检查填写的字段 · " + "、".join(filter(None, fields))}, status_code=422)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        api = request.url.path.startswith("/api/")
        if api and request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("x-tfwatch-request") != "1":
                return JSONResponse({"detail": "请求缺少安全标头"}, status_code=403)
            length = request.headers.get("content-length")
            if request.headers.get("transfer-encoding") or (length is not None
                    and (len(length) > 8 or not length.isdecimal() or int(length) > 16384)):
                return JSONResponse({"detail": "请求体过大或长度未知"}, status_code=413)
        response = await call_next(request)
        if api and request.url.path != "/api/source":
            response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' https://*.mzstatic.com data:; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response

    app.include_router(accounts.router, prefix="/api")
    app.include_router(catalog.router, prefix="/api")
    app.include_router(notifications.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    @app.get("/api/health")
    def health():
        with app.state.sessions() as session:
            session.execute(text("SELECT 1 FROM settings WHERE id=1")).scalar_one()
        return {"status": "ok"}

    @app.get("/api/source", include_in_schema=False)
    def source():
        if config.source_url.startswith(("https://", "http://")):
            return RedirectResponse(config.source_url)
        archive = config.static_dir / "tfwatch-source.tar.gz"
        if archive.is_file():
            return FileResponse(archive, filename="tfwatch-source.tar.gz")
        raise HTTPException(404, "此部署尚未配置源码地址")

    static_dir = Path(config.static_dir)
    if (static_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{page:path}", include_in_schema=False)
    def frontend(page: str):
        index = static_dir / "index.html"
        if page == "api" or page.startswith("api/") or not index.is_file():
            raise HTTPException(404)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()




