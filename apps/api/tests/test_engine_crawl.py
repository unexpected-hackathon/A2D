"""크롤러(경로 찾기)가 내부 링크를 끝까지 따라가고, 찾은 모든 페이지·JS를 점검하는지 본다.

- 링크 여러 단계, SPA 라우터 경로, 나중에 불러오는 JS 조각, Next.js 빌드 목록, robots의 Sitemap 줄·사이트맵 목록
- 같은 주소·같은 틀의 페이지(/post/1, /post/2 …)는 건너뛴다. 상태를 바꿀 수 있는 이름은 열지 않는다
- 깊은 페이지에서 비밀키(#12)·관리자 로그인(#18)·오류 노출(#11)·처음 보는 우리 호스트(자산)를 찾는다
"""

import asyncio
import json

import httpx

from a2d.config import Settings
from a2d.engine.base import Budget, EngineContext
from a2d.engine.crawl import template_key
from a2d.engine.live import LiveEngine
from tests.test_engine_spa import SAFE_HEADERS, SafeTls

DOMAIN = "learnhub.example"
WWW = f"www.{DOMAIN}"


class SiteDns:
    def __init__(self, hosts):
        self.hosts = set(hosts)

    def a(self, name):
        return ["203.0.113.10"] if name in self.hosts else []

    def cname(self, name):
        return None

    def txt(self, name):
        if name == DOMAIN:
            return ["v=spf1 -all"]
        if name == f"_dmarc.{DOMAIN}":
            return ["v=DMARC1; p=reject"]
        return []


class FakeSite:
    """pages: {(호스트, 경로[?쿼리]): (상태, 본문, 형식)}. 없는 주소는 404."""

    def __init__(self, pages):
        self.pages = pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        u = request.url
        if u.scheme == "http":
            return httpx.Response(301, headers={"location": f"https://{u.host}{u.raw_path.decode()}"})
        key = (u.host, u.raw_path.decode())
        if key not in self.pages:
            key = (u.host, u.path)
        if key in self.pages:
            status, body, media = self.pages[key]
            return httpx.Response(status, text=body, headers={**SAFE_HEADERS, "content-type": media})
        return httpx.Response(404, text="not found", headers={**SAFE_HEADERS, "content-type": "text/plain"})

    def opened(self):
        return {r.url.raw_path.decode() for r in self.requests}


def html(body):
    return (200, f"<!doctype html><html><head><title>LearnHub</title></head><body>{body}</body></html>",
            "text/html")


def scan(site: FakeSite, hosts=(DOMAIN, WWW)):
    client = httpx.AsyncClient(transport=httpx.MockTransport(site))
    engine = LiveEngine(Settings(), dns=SiteDns(hosts), tls=SafeTls(), client=client, host_min_interval=0)
    assets, findings, audit = {}, [], []

    def add_asset(a):
        assets[a.host] = a
        return f"A-{len(assets):03d}"

    def add_finding(f):
        f.validate()
        assert f.host in assets
        findings.append(f)
        return f"F-{len(findings):04d}", "A-001"

    ctx = EngineContext("S-1", DOMAIN, 1, Budget(0, 20, 300), lambda *a: None, add_asset, add_finding,
                        lambda *a, **k: audit.append((a, k)))
    asyncio.run(engine.run(ctx))
    asyncio.run(client.aclose())
    return assets, findings, audit


def test_follows_internal_links_to_any_depth():
    site = FakeSite({
        (WWW, "/"): html('<a href="/learn">강의</a>'),
        (WWW, "/learn"): html('<a href="/learn/python">파이썬</a>'),
        (WWW, "/learn/python"): html('<a href="/learn/python/week-1">1주차</a>'),
        (WWW, "/learn/python/week-1"): html('<a href="https://www.learnhub.example/learn/python/week-1/quiz">퀴즈</a>'),
        (WWW, "/learn/python/week-1/quiz"): html("끝"),
    })
    scan(site)
    assert "/learn/python/week-1/quiz" in site.opened()


def test_spa_routes_and_lazy_chunks_from_js():
    main = ('import("./Learn-3f2a.js");const routes=[{path:"/learn",element:L},{path:"/mypage",element:M}];'
            'navigate("/settings/profile");')
    site = FakeSite({
        (WWW, "/"): html('<div id="root"></div><script type="module" src="/assets/index-1.js"></script>'),
        (WWW, "/assets/index-1.js"): (200, main, "application/javascript"),
        (WWW, "/assets/Learn-3f2a.js"): (200, 'router.push("/learn/live")', "application/javascript"),
    })
    scan(site)
    opened = site.opened()
    assert {"/learn", "/mypage", "/settings/profile", "/assets/Learn-3f2a.js", "/learn/live"} <= opened


def test_next_build_manifest_routes():
    manifest = 'self.__BUILD_MANIFEST={"/":["static/chunks/pages/index.js"],"/courses/[id]":[],"/pricing":[]}'
    site = FakeSite({
        (WWW, "/"): html('<script src="/_next/static/abc123/_buildManifest.js" defer></script>'),
        (WWW, "/_next/static/abc123/_buildManifest.js"): (200, manifest, "application/javascript"),
    })
    scan(site)
    opened = site.opened()
    assert "/pricing" in opened and "/_next/static/chunks/pages/index.js" in opened
    assert not any("[id]" in p for p in opened)  # 라우터의 변수 자리는 열지 않는다


def test_robots_sitemap_directive_and_index():
    site = FakeSite({
        (WWW, "/robots.txt"): (200, f"User-agent: *\nSitemap: https://{WWW}/sm/index.xml\n", "text/plain"),
        (WWW, "/sm/index.xml"): (200, f"<sitemapindex><sitemap><loc>https://{WWW}/sm/courses.xml</loc></sitemap>"
                                      "</sitemapindex>", "application/xml"),
        (WWW, "/sm/courses.xml"): (200, f"<urlset><url><loc>https://{WWW}/courses/intro</loc></url></urlset>",
                                   "application/xml"),
        (WWW, "/"): html("홈"),
    })
    scan(site)
    assert "/courses/intro" in site.opened()


def test_same_template_and_duplicates_are_skipped():
    links = "".join(f'<a href="/post/{i}">글 {i}</a><a href="/post/{i}">다시</a>' for i in range(1, 51))
    links += "".join(f'<a href="/board.php?id={i}">게시판</a>' for i in range(1, 21))
    site = FakeSite({(WWW, "/"): html(links)})
    _, _, audit = scan(site)
    posts = [p for p in site.opened() if p.startswith("/post/")]
    boards = [p for p in site.opened() if p.startswith("/board.php")]
    assert len(posts) == 3 and len(boards) == 3
    assert any("같은 틀이라 건너뜀" in (a[3] or "") for a, _ in audit if a[1] == "crawl")


def test_template_key():
    assert template_key("/post/123") == template_key("/post/456") == "/post/{x}"
    assert template_key("/blog/my-first-blog-post") == "/blog/{x}"
    assert template_key("/board.php?bo_table=free&wr_id=3") == "/board.php?bo_table&wr_id"
    assert template_key("/learn/python") != template_key("/learn/java")


def test_state_changing_links_are_not_opened():
    site = FakeSite({(WWW, "/"): html('<a href="/logout">로그아웃</a><a href="/cart/delete?id=1">삭제</a>'
                                      '<a href="/account/withdraw">탈퇴</a><a href="/courses">강의</a>')})
    scan(site)
    opened = site.opened()
    assert "/courses" in opened
    assert not {"/logout", "/cart/delete?id=1", "/account/withdraw"} & opened


def test_deep_page_checks_secret_admin_and_error():
    key = "sk-proj-" + "Q7w" * 10
    site = FakeSite({
        (WWW, "/"): html('<a href="/learn">강의</a>'),
        (WWW, "/learn"): html('<a href="/learn/editor">에디터</a><a href="/learn/report">리포트</a>'),
        (WWW, "/learn/editor"): html('<script src="/static/editor.js"></script>'),
        (WWW, "/static/editor.js"): (200, f'const OPENAI="{key}";', "application/javascript"),
        (WWW, "/learn/report"): (500, "<pre>Traceback (most recent call last):\n  File app.py</pre>", "text/html"),
        (WWW, "/learn/manage"): html('<form><input type="password" name="pw"></form>'),
        (WWW, "/robots.txt"): (200, "User-agent: *\nDisallow: /backoffice/\n", "text/plain"),
        (WWW, "/backoffice/"): html('<h1>관리자 로그인</h1><form><input type="password"></form>'),
    })
    _, findings, _ = scan(site)
    got = {(f.check_id, f.host) for f in findings}
    assert (12, WWW) in got and (11, WWW) in got and (18, WWW) in got
    secret = next(f for f in findings if f.check_id == 12)
    assert "/static/editor.js" in secret.location and key not in secret.evidence
    admin = next(f for f in findings if f.check_id == 18)
    assert "/backoffice/" in admin.location


def test_new_host_found_deep_in_site_becomes_asset():
    host = f"lms.{DOMAIN}"
    site = FakeSite({
        (WWW, "/"): html('<a href="/learn">강의</a>'),
        (WWW, "/learn"): html(f'<a href="https://{host}/course/1">강의실</a>'),
        (host, "/"): html("강의실 홈"),
        (host, "/course/1"): html("강의"),
    })
    assets, _, _ = scan(site, hosts=(DOMAIN, WWW, host))
    assert host in assets and 2 in assets[host].found_by
    assert "/course/1" in site.opened()


def test_other_domains_are_not_crawled():
    site = FakeSite({(WWW, "/"): html('<a href="https://evil.example.org/x">외부</a>'
                                      '<a href="https://cdn.other.com/lib.js">cdn</a>')})
    scan(site)
    assert all(r.url.host in (DOMAIN, WWW) for r in site.requests)


def test_pii_api_found_deep_is_reported_with_count():
    rows = json.dumps([{"name": "김민준", "email": "a@example.com", "phone": "010-0000-0001"}])
    js = 'fetch("/api/students");fetch("/api/teachers");'
    site = FakeSite({
        (WWW, "/"): html('<a href="/learn">강의</a>'),
        (WWW, "/learn"): html('<script src="/static/learn.js"></script>'),
        (WWW, "/static/learn.js"): (200, js, "application/javascript"),
        (WWW, "/api/students"): (200, rows, "application/json"),
        (WWW, "/api/teachers"): (200, rows, "application/json"),
    })
    _, findings, _ = scan(site)
    f = next(f for f in findings if f.check_id == 16)
    assert "/api/students" in f.location and "외 1곳" in f.evidence and "a@example.com" not in f.evidence
