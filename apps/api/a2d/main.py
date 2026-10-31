"""A2D 백엔드 HTTP API (docs/A2D_API명세.md). 기본 주소 /api/v1.

실행: uvicorn a2d.main:app --port 8000
"""

from __future__ import annotations

import importlib
import json
import logging
from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import agents
from .auth import COOKIE, Auth
from .config import Settings
from .engine.base import Engine
from .engine.fixture import FixtureEngine
from .errors import ApiError, unauthenticated, validation
from .service import Service
from .store import Store
from .timeutil import now_iso

PREFIX = "/api/v1"
PUBLIC = {f"{PREFIX}/health", f"{PREFIX}/auth/login", f"{PREFIX}/auth/logout"}
STATE_CHANGING = {"POST", "PATCH", "PUT", "DELETE"}

log = logging.getLogger("a2d")


def load_engine(settings: Settings) -> Engine:
    if settings.engine == "fixture":
        return FixtureEngine(step_sec=settings.fixture_step_sec)
    module, _, cls = settings.engine.partition(":")
    return getattr(importlib.import_module(module), cls)(settings)


async def json_body(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise validation("요청 본문이 올바른 JSON이 아닙니다.") from None
    if not isinstance(body, dict):
        raise validation("요청 본문은 JSON 객체여야 합니다.")
    return body


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(settings.db_path)
        app.state.auth = Auth(settings)
        app.state.llm = agents.LlmClient(settings)
        app.state.svc = Service(settings, store, engine or load_engine(settings), app.state.llm)
        app.state.svc.recover()
        yield
        await app.state.svc.shutdown()

    app = FastAPI(
        title="A2D API",
        version="0.1.0",
        lifespan=lifespan,
        # 공개 API 설명서는 A2D 자신이 #17에 걸리므로 기본으로 끈다(API 명세 11장).
        docs_url=f"{PREFIX}/docs" if settings.expose_openapi else None,
        redoc_url=None,
        openapi_url=f"{PREFIX}/openapi.json" if settings.expose_openapi else None,
    )

    # ------------------------------------------------------------ 오류 형식

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(exc.body(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(validation("요청 형식이 올바르지 않습니다.").body(), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "요청한 주소가 없습니다."}}, status_code=404)
        if exc.status_code == 405:
            return JSONResponse({"error": {"code": "METHOD_NOT_ALLOWED", "message": "지원하지 않는 요청 방식입니다."}},
                                status_code=405)
        return JSONResponse({"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}}, status_code=exc.status_code)

    # ------------------------------------------------------------ CSRF·형식 검사 (API 명세 3장)

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if request.method in STATE_CHANGING and request.url.path.startswith(PREFIX):
            origin = request.headers.get("origin")
            if origin not in settings.web_origins:
                e = ApiError(403, "FORBIDDEN_ORIGIN", "허용되지 않은 화면에서 보낸 요청입니다.")
                return JSONResponse(e.body(), status_code=403)
            has_body = int(request.headers.get("content-length") or 0) > 0 or "transfer-encoding" in request.headers
            ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if has_body and ctype != "application/json":
                return JSONResponse(validation("Content-Type은 application/json이어야 합니다.").body(), status_code=400)
        resp = await call_next(request)
        if request.url.path.startswith(PREFIX):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def svc(request: Request) -> Service:
        return request.app.state.svc

    def require_login(request: Request) -> None:
        if request.url.path in PUBLIC:
            return
        if request.app.state.auth.touch(request.cookies.get(COOKIE)) is None:
            raise unauthenticated()

    r = APIRouter(prefix=PREFIX, dependencies=[Depends(require_login)])

    # ------------------------------------------------------------ 인증

    @r.post("/auth/login")
    async def login(request: Request, response: Response):
        body = await json_body(request)
        email, password = body.get("email"), body.get("password")
        if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
            raise validation("이메일과 비밀번호를 입력해 주세요.")
        auth: Auth = request.app.state.auth
        ip = request.client.host if request.client else "unknown"
        sess = auth.login(ip, email, password, request.cookies.get(COOKIE))
        response.set_cookie(COOKIE, sess.sid, httponly=True, samesite="lax", path="/", secure=settings.secure_cookie)
        return auth.session_body(sess)

    @r.post("/auth/logout", status_code=204)
    async def logout(request: Request):
        request.app.state.auth.logout(request.cookies.get(COOKIE))
        resp = Response(status_code=204)
        resp.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=settings.secure_cookie)
        return resp

    @r.get("/auth/me")
    async def me(request: Request):
        auth: Auth = request.app.state.auth
        return auth.session_body(auth.touch(request.cookies.get(COOKIE)))

    # ------------------------------------------------------------ 공통·도메인

    @r.get("/health")
    async def health(request: Request):
        return {"status": "ok", "llm": await request.app.state.llm.status(), "time": now_iso()}

    @r.get("/checks")
    async def checks():
        return Service.checks()

    @r.get("/domains")
    async def list_domains(s: Service = Depends(svc)):
        return {"items": s.list_domains()}

    @r.post("/domains")
    async def register_domain(request: Request, s: Service = Depends(svc)):
        body = await json_body(request)
        data, created = s.register_domain(body.get("domain"))
        return JSONResponse(data, status_code=201 if created else 200)

    @r.get("/domains/{domain_id}")
    async def get_domain(domain_id: str, s: Service = Depends(svc)):
        return s.get_domain(domain_id)

    @r.post("/domains/{domain_id}/verify")
    async def verify_domain(domain_id: str, s: Service = Depends(svc)):
        return await s.verify_domain(domain_id)

    # ------------------------------------------------------------ 점검

    @r.post("/domains/{domain_id}/scans", status_code=202)
    async def start_scan(domain_id: str, s: Service = Depends(svc)):
        return s.start_scan(domain_id)

    @r.get("/scans/{scan_id}")
    async def get_scan(scan_id: str, s: Service = Depends(svc)):
        return s.get_scan(scan_id)

    @r.post("/scans/{scan_id}/stop")
    async def stop_scan(scan_id: str, s: Service = Depends(svc)):
        return await s.stop_scan(scan_id)

    # ------------------------------------------------------------ 대시보드

    @r.get("/domains/{domain_id}/summary")
    async def summary(domain_id: str, s: Service = Depends(svc)):
        return s.summary(domain_id)

    @r.get("/scans/{scan_id}/assets")
    async def assets(scan_id: str, s: Service = Depends(svc)):
        return s.assets(scan_id)

    @r.patch("/domains/{domain_id}/assets/{asset_id}")
    async def patch_asset(domain_id: str, asset_id: str, request: Request, s: Service = Depends(svc)):
        body = await json_body(request)
        return s.set_importance(domain_id, asset_id, body.get("importance"))

    # ------------------------------------------------------------ 발견·조치 가이드

    @r.get("/scans/{scan_id}/findings")
    async def findings(scan_id: str, asset_id: str | None = None, severity: str | None = None,
                       status: str | None = None, check_id: str | None = None, s: Service = Depends(svc)):
        return s.findings(scan_id, asset_id=asset_id, severity_filter=severity, status=status, check_id=check_id)

    @r.get("/findings/{finding_id}")
    async def finding(finding_id: str, s: Service = Depends(svc)):
        return s.finding_detail(finding_id)

    @r.get("/scans/{scan_id}/report")
    async def report(scan_id: str, s: Service = Depends(svc)):
        return s.report(scan_id)

    @r.post("/scans/{scan_id}/questions")
    async def questions(scan_id: str, request: Request, s: Service = Depends(svc)):
        body = await json_body(request)
        return await s.ask(scan_id, body.get("question"))

    # ------------------------------------------------------------ 기록

    @r.get("/domains/{domain_id}/history")
    async def history(domain_id: str, s: Service = Depends(svc)):
        return s.history(domain_id)

    @r.get("/scans/{scan_id}/changes")
    async def changes(scan_id: str, s: Service = Depends(svc)):
        return s.changes(scan_id)

    @r.get("/scans/{scan_id}/audit")
    async def audit(scan_id: str, actor: str | None = None, rejected: str | None = None, s: Service = Depends(svc)):
        return s.audit(scan_id, actor=actor, rejected=rejected)

    app.include_router(r)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
