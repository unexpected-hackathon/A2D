"""JobNest: 결함을 일부러 심은 가상 채용·인재 매칭 플랫폼.

nginx가 TLS를 끝내고 Host 헤더를 그대로 넘기면, 이 앱이 호스트 이름으로 하위 자산을 나눈다.
결함마다 FIX_<번호> 환경 변수로 고친 상태를 켤 수 있다(config.fixed).
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Host, Route, Router

from . import config as c
from . import pages
from .data import APPLICANTS

PLANTED = Path("/srv/planted")
EXTERNAL_HOSTS = {c.EXT_PAGES, c.EXT_BUCKET, c.EXT_BOOKING, c.HOST_PROMO}

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def html(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(body, status_code=status)


def blocked() -> HTMLResponse:
    return html(pages.simple("접근이 제한되었습니다", "허용된 사내 IP에서만 접근할 수 있습니다."), 403)


def not_found(request: Request, exc=None) -> HTMLResponse:
    # #11: 고치기 전에는 없는 주소에 스택 트레이스를 보여 준다.
    if c.fixed(11):
        return html(pages.not_found(), 404)
    return html(pages.traceback_page(request.url.path), 500)


HANDLERS = {404: not_found, StarletteHTTPException: lambda r, e: not_found(r) if e.status_code == 404 else
            PlainTextResponse(str(e.detail), status_code=e.status_code)}


def planted_file(name: str, media_type: str, fix_no: int):
    """방치된 파일. 고친 뒤에는 404."""

    async def endpoint(request: Request):
        if c.fixed(fix_no):
            return not_found(request)
        return FileResponse(PLANTED / name, media_type=media_type)

    return endpoint


# ---------------------------------------------------------------- www (대표 홈페이지)

async def www_home(request: Request):
    resp = html(pages.home())
    if c.fixed(31):
        resp.set_cookie("jn_session", "demo-session-0001", httponly=True, secure=True, samesite="lax")
    else:
        # samesite=None으로 SameSite 속성 자체를 빼고, Secure·HttpOnly도 붙이지 않는다.
        resp.set_cookie("jn_session", "demo-session-0001", samesite=None)
    return resp


def page(title: str, text: str):
    async def endpoint(request: Request):
        return html(pages.simple(title, text))

    return endpoint


async def www_app_js(request: Request):
    js = pages.app_js(leak=not c.fixed(12), sourcemap=not c.fixed(13))
    return Response(js, media_type="application/javascript")


async def www_app_js_map(request: Request):
    if c.fixed(13):
        return not_found(request)
    return Response(pages.app_js_map(leak=not c.fixed(12)), media_type="application/json")


async def www_uploads(request: Request):
    if c.fixed(10):
        return blocked()
    return html(pages.uploads_index())


async def www_server_status(request: Request):
    if c.fixed(20):
        return not_found(request)
    return html(pages.server_status())


async def www_actuator_env(request: Request):
    if c.fixed(20):
        return not_found(request)
    return Response(pages.actuator_env(), media_type="application/json")


async def www_internal_reports(request: Request):
    """#16 숨은 경로의 입구. robots.txt(Disallow: /internal/reports/)가 가리키는 사내 보고서 목록이고,
    내보내기 주소로 가는 링크가 있다. 추가 점검이 이름을 추측하지 않고 단서만 따라가 닿게 하려는 단계다."""
    if c.fixed(16):
        return need_auth()
    return html(pages.internal_reports())


async def www_internal_export(request: Request):
    """#16 숨은 경로: 사내 보고서용 지원자 내보내기. robots.txt → /internal/reports/ 목록의 링크, 그리고
    소스맵 주석에만 나오고 화면·API 문서에는 없다. 기본 점검은 이 경로를 모르고, 추가 점검(Attack 에이전트)이
    단서를 따라가야 찾는다. #16을 고치면 /api/v1/applicants와 함께 막힌다(같은 조치)."""
    if c.fixed(16):
        return need_auth()
    rows = [{k: a[k] for k in ("id", "name", "email", "phone", "desired_job")} for a in APPLICANTS]
    return JSONResponse({"report": "applicants_export", "generated_by": "nightly-batch",
                         "count": len(rows), "rows": rows})


async def admin_page(request: Request):
    if c.fixed(18):
        return blocked()
    return html(pages.admin_login())


www = Starlette(
    routes=[
        Route("/", www_home),
        Route("/robots.txt", lambda r: PlainTextResponse(pages.robots())),
        Route("/sitemap.xml", lambda r: Response(pages.sitemap(), media_type="application/xml")),
        Route("/login", lambda r: html(pages.login())),
        Route("/jobs", page("채용 공고", "이번 주 신규 공고를 준비하고 있습니다.")),
        Route("/jobs/{slug}", page("채용 공고", "공고 상세는 준비 중입니다.")),
        Route("/apply", page("지원서 작성", "로그인 후 지원서를 작성할 수 있습니다.")),
        Route("/support", page("고객센터", "평일 09:00~18:00 · help@example.com")),
        Route("/search", page("검색 결과", "검색 결과가 없습니다.")),
        Route("/static/js/app.js", www_app_js),
        Route("/static/js/app.js.map", www_app_js_map),
        Route("/static/js/jquery-1.12.4.min.js",
              lambda r: Response(pages.JQUERY_STUB, media_type="application/javascript")),
        Route("/backup.zip", planted_file("backup.zip", "application/zip", 8)),
        Route("/db.sql", planted_file("db.sql", "application/sql", 8)),
        Route("/.env", planted_file(".env", "text/plain", 9)),
        Route("/.git/HEAD", planted_file("git/HEAD", "text/plain", 9)),
        Route("/.git/config", planted_file("git/config", "text/plain", 9)),
        Route("/uploads/", www_uploads),
        Route("/server-status", www_server_status),
        Route("/actuator/env", www_actuator_env),
        Route("/admin", admin_page),
        Route("/admin/", admin_page),
        Route("/internal/reports/", www_internal_reports),
        Route("/internal/reports/export", www_internal_export),
    ],
    exception_handlers=HANDLERS,
)


# ---------------------------------------------------------------- admin

async def admin_root(request: Request):
    return await admin_page(request)


admin = Starlette(routes=[Route("/", admin_root), Route("/admin", admin_root), Route("/login", admin_root)],
                  exception_handlers=HANDLERS)


# ---------------------------------------------------------------- staging · dev (잊힌 시험 서버)

class StagingGate(BaseHTTPMiddleware):
    """#19를 고치면 시험 서버 전체를 사내 IP 전용으로 막는다."""

    async def dispatch(self, request, call_next):
        if c.fixed(19):
            return blocked()
        return await call_next(request)


async def staging_home(request: Request):
    return html(pages.staging(request.headers.get("host", "")))


async def staging_debug(request: Request):
    return JSONResponse({"DEBUG": True, "DATABASE_URL": "mysql://jobnest:***@10.0.12.5/jobnest_prod",
                         "GIT_SHA": "4f2c9e1", "ENV": "staging"})


STAGING_ROUTES = [Route("/", staging_home), Route("/debug/vars", staging_debug)]

staging = Starlette(routes=STAGING_ROUTES, exception_handlers=HANDLERS)
staging.add_middleware(StagingGate)

# 감시 시연용 test 서버: 수탁사가 새로 연 서버라 #19 조치(staging·dev 제한)와 별개로 열려 있다.
test_server = Starlette(routes=STAGING_ROUTES, exception_handlers=HANDLERS)


# ---------------------------------------------------------------- api

api = FastAPI(
    title="JobNest Public API",
    version="1.8.0",
    description="JobNest 채용 웹·앱이 쓰는 API. (A2D 시연용 가상 서비스)",
    docs_url=None if c.fixed(17) else "/swagger",
    redoc_url=None,
    openapi_url=None if c.fixed(17) else "/openapi.json",
    exception_handlers=HANDLERS,
)


class Cors(BaseHTTPMiddleware):
    """#21: 고치기 전에는 아무 Origin이나(null 포함) 자격 증명과 함께 허용한다."""

    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        if request.method == "OPTIONS" and origin:
            resp = Response(status_code=204)
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        else:
            resp = await call_next(request)
        if origin:
            if c.fixed(21):
                if origin in (f"https://{c.HOST_WWW}", f"https://{c.DOMAIN}"):
                    resp.headers["Access-Control-Allow-Origin"] = origin
                    resp.headers["Access-Control-Allow-Credentials"] = "true"
                    resp.headers["Vary"] = "Origin"
            else:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp


api.add_middleware(Cors)


def need_auth() -> JSONResponse:
    return JSONResponse({"detail": "인증이 필요합니다"}, status_code=401,
                        headers={"WWW-Authenticate": "Bearer"})


@api.get("/api/v1/status", tags=["system"])
async def api_status():
    return {"status": "ok", "version": "1.8.0"}


@api.get("/api/v1/jobs", tags=["jobs"])
async def api_jobs():
    return [{"id": 1, "title": "백엔드 개발자 (3년 이상)", "company": "가상테크"},
            {"id": 2, "title": "UX 디자이너 (신입)", "company": "샘플랩스"}]


@api.get("/api/v1/applicants/me", tags=["applicants"])
async def api_me():
    return need_auth()


@api.get("/api/v1/applicants", tags=["applicants"], summary="지원자 목록")
async def api_applicants(page: int = 1, size: int = 20):
    if c.fixed(16):
        return need_auth()
    start = max(page - 1, 0) * size
    return {"page": page, "total": len(APPLICANTS), "items": APPLICANTS[start:start + size]}


@api.get("/api/v1/applicants/{applicant_id}", tags=["applicants"], summary="지원자 조회")
async def api_applicant(applicant_id: int):
    if c.fixed(16):
        return need_auth()
    for a in APPLICANTS:
        if a["id"] == applicant_id:
            return a
    return JSONResponse({"detail": "not found"}, status_code=404)


# ---------------------------------------------------------------- 외부 주소 흉내 (#4, #6, #14)

async def pages_404(request: Request):
    return html(pages.PAGES_404, 404)


async def bucket(request: Request):
    if c.fixed(14):
        return Response(pages.BUCKET_DENIED, status_code=403, media_type="application/xml")
    return Response(pages.bucket_list(), media_type="application/xml")


async def booking(request: Request):
    return html(pages.booking())


def catch_all(endpoint):
    return Starlette(routes=[Route("/{path:path}", endpoint)])


async def unknown_host(request: Request):
    return PlainTextResponse("unknown host", status_code=404)


router = Router(
    routes=[
        Host(c.DOMAIN, www),
        Host(c.HOST_WWW, www),
        Host(c.HOST_API, api),
        Host(c.HOST_ADMIN, admin),
        Host(c.HOST_STAGING, staging),
        Host(c.HOST_DEV, staging),
        Host(c.HOST_TEST, test_server if c.test_server() else catch_all(unknown_host)),
        Host(c.HOST_BOOKING, catch_all(booking)),
        Host(c.EXT_BOOKING, catch_all(booking)),
        Host(c.HOST_PROMO, catch_all(pages_404)),
        Host(c.EXT_PAGES, catch_all(pages_404)),
        Host(c.EXT_BUCKET, catch_all(bucket)),
        Host("{any}", catch_all(unknown_host)),
    ]
)


class Common:
    """모든 응답에 붙는 공통 동작: HTTPS 전환(#27), 서버 표시(#23·#25), 보안 헤더(#30)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        host = headers.get(b"host", b"").decode().split(":")[0].lower()
        external = host in EXTERNAL_HOSTS
        if (c.fixed(27) and scope.get("scheme") == "http" and not external
                and host in c.ALL_HOSTS):
            path = scope.get("raw_path", scope["path"].encode()).decode()
            qs = scope.get("query_string", b"").decode()
            url = f"https://{host}{path}" + (f"?{qs}" if qs else "")
            return await RedirectResponse(url, status_code=301)(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                h = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"server"]
                if host == c.EXT_BUCKET:
                    h.append((b"server", b"AmazonS3"))
                elif host in (c.EXT_PAGES, c.HOST_PROMO):
                    h.append((b"server", b"GitHub.com"))
                else:
                    h.append((b"server", b"Apache" if c.fixed(23) else b"Apache/2.4.49 (Unix)"))
                    if not c.fixed(25):
                        h.append((b"x-powered-by", b"PHP/8.1.2"))
                    if c.fixed(30):
                        h.extend((k.lower().encode(), v.encode()) for k, v in SECURITY_HEADERS.items())
                message["headers"] = h
            await send(message)

        await self.app(scope, receive, send_wrapper)


app = Common(router)
