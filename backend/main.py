from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.ai_analyst.router import router as ai_analyst_router
from backend.config import get_settings
from backend.database import db_ping
from backend.routers.admin import router as admin_router
from backend.routers.public import router as public_router
from backend.ssot.validator import validate_ssot


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ProfileDNA (SSOT)")

    # static (SSOT)
    app.mount("/static", StaticFiles(directory="backend/static"), name="static")

    @app.on_event("startup")
    async def _startup():
        # Nesta fase: valida e reporta no /health; NÃO derruba o app.
        app.state.ssot_validation = validate_ssot(strict=False)

    @app.middleware("http")
    async def admin_csrf_middleware(request: Request, call_next):
        """
        SSOT: CSRF obrigatório para /admin em métodos mutáveis (double submit cookie).

        Exceções:
        - /admin/login
        - /admin/logout
        - /admin/ai/chat  -> validado localmente na própria rota para não quebrar Form(...)
        """
        path = request.url.path

        if path.startswith("/admin") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if path in ("/admin/login", "/admin/logout", "/admin/ai/chat"):
                return await call_next(request)

            cookie_token = request.cookies.get("csrf_token")
            header_token = request.headers.get("x-csrf-token")

            form_token = None

            if not header_token:
                try:
                    body = await request.body()
                    content_type = (request.headers.get("content-type") or "").lower()

                    if "application/x-www-form-urlencoded" in content_type and body:
                        parsed = parse_qs(body.decode("utf-8", errors="ignore"))
                        form_token = parsed.get("csrf_token", [None])[0]

                    async def receive() -> dict:
                        return {
                            "type": "http.request",
                            "body": body,
                            "more_body": False,
                        }

                    request._receive = receive  # type: ignore[attr-defined]

                except Exception:
                    form_token = None

            provided = header_token or form_token

            if not cookie_token or not provided or cookie_token != provided:
                return PlainTextResponse("CSRF validation failed.", status_code=403)

        return await call_next(request)

    @app.get("/health")
    async def health():
        db_ok = await db_ping()
        v = getattr(app.state, "ssot_validation", None)
        return {
            "status": "ok",
            "database": "connected" if db_ok else "disconnected",
            "ssot_version": "v1",
            "ai_enabled": settings.AI_ENABLED,
            "ssot_ok": bool(getattr(v, "ok", False)),
            "ssot_missing_files": getattr(v, "missing_files", []) if v else [],
            "ssot_invalid_json_files": getattr(v, "invalid_json_files", []) if v else [],
        }

    app.include_router(public_router)
    app.include_router(admin_router)
    app.include_router(ai_analyst_router)
    return app


app = create_app()
