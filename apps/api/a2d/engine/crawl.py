"""우리 호스트 안의 내부 링크를 끝까지 따라가는 크롤러(경로 찾기, #2·#3 확장).

호스트마다 첫 화면(/)·robots.txt(Allow·Disallow·Sitemap 줄)·사이트맵(목록 포함)에서 시작해
화면 링크(href·src·action), 리다이렉트, JS에 적힌 경로(SPA 라우터·API 호출·Next.js 빌드 목록)와
나중에 불러오는 JS 조각까지 따라간다. 요청 수 상한은 두지 않고, 같은 페이지만 건너뛴다.

- 같은 주소(경로 + 쿼리)는 한 번만 연다.
- 같은 틀의 페이지(/post/1, /post/2, /board.php?id=…)는 TEMPLATE_SAMPLES개만 연다. 게시글이 수만 개인
  사이트에서 점검이 끝나지 않는 것을 막는다(틀이 같으면 노출 여부도 같다).
- 읽기(GET)만 보낸다. logout·delete처럼 상태를 바꿀 수 있는 이름의 경로는 기록만 하고 열지 않는다.
- 우리 도메인의 처음 보는 호스트는 new_hosts에 모아 자산 찾기에 넘긴다(DNS 확인은 엔진이 한다).

찾은 페이지·JS·경로는 HostMap에 남기고, 점검(#8·#10·#11·#12·#13·#16·#18·#34)은 엔진이 이 기록으로 한다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, parse_qsl

from .base import ScanStopped
from .net import Fetched, HttpClient

log = logging.getLogger("a2d.engine.crawl")

TEMPLATE_SAMPLES = 3                 # 같은 틀의 페이지를 몇 개까지 여는지
SCRIPT_MAX_BYTES = 8 * 1024 * 1024   # JS 번들은 크다. 뒤쪽의 키·경로까지 읽는다
SITEMAP_MAX_BYTES = 4 * 1024 * 1024

# GET이라도 상태를 바꿀 수 있는 이름은 열지 않는다(읽기 전용 원칙)
UNSAFE_ROUTE = re.compile(r"log-?out|sign-?out|delete|remove|destroy|unsubscribe|reset|cancel|withdraw"
                          r"|revoke|pay|charge|send|confirm|activate|verify|callback|webhook", re.I)
# 열어도 얻을 것이 없는 정적 파일(경로로만 기록한다). 백업 확장자(.zip 등)는 #8이 따로 본다
STATIC_EXT = re.compile(r"\.(?:css|png|jpe?g|gif|svg|ico|webp|avif|bmp|woff2?|ttf|otf|eot|mp4|webm|mp3|wav"
                        r"|pdf|docx?|xlsx?|pptx?|hwp|zip|gz|tgz|tar|7z|rar|sql|bak|dump|map|txt|csv)$", re.I)
JS_EXT = re.compile(r"\.m?js$", re.I)

_LINK_ATTR = re.compile(r'(?:href|src|action|data-href|data-url|formaction)\s*=\s*["\']([^"\'#\s<>]+)', re.I)
_SCRIPT_SRC = re.compile(r'<script[^>]+src\s*=\s*["\']([^"\']+)["\']', re.I)
_META_REFRESH = re.compile(r'http-equiv=["\']refresh["\'][^>]*content=["\'][^"\']*url=([^"\'>\s]+)', re.I)
_ROBOTS_PATH = re.compile(r"(?im)^\s*(?:dis)?allow:\s*(/\S*)")
_ROBOTS_SITEMAP = re.compile(r"(?im)^\s*sitemap:\s*(\S+)")
_SITEMAP_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
# JS 속 경로. SPA 라우터(path·to·href·navigate·push…)와 API 호출 문자열(/api/…, /v1/…)
_ROUTE_IN_JS = re.compile(
    r"""(?:\bpath|\bto|\bhref|\bpathname|\bredirect(?:To)?|\bnavigate|\bpush|\breplace|\blink|\burl|\broute)"""
    r"""\s*[:=(]\s*\(?\s*["'`](/[A-Za-z0-9_\-./~%]*)["'`]""")
_API_IN_JS = re.compile(r"""["'`](/(?:api|v\d+|rest|graphql|internal|admin/api)(?:/[A-Za-z0-9_.\-]*)*)(?:\?[^"'`\s]*)?["'`]""")
_ABS_URL = re.compile(r"""https?://([a-z0-9.\-]+)(/[^\s"'`<>)\\]*)?""", re.I)
_NEXT_MANIFEST_ROUTE = re.compile(r'"(/[^"\s]*)"\s*:\s*\[')
# 나중에 불러오는 JS 조각(Vite: "./Learn-3f2a.js", Next: "static/chunks/pages/learn-…js")
_JS_CHUNK = re.compile(r"""["'`]((?:\.{0,2}/)?(?:[\w@.\-]+/)*[\w@.\-]+\.m?js)["'`]""")

_NUM = re.compile(r"\d+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_HEX = re.compile(r"[0-9a-f]{12,}", re.I)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){3,}", re.I)  # my-first-blog-post 같은 글 주소
_LONG = re.compile(r".{40,}")
# 민감해 보이는 이름이 든 칸은 같은 틀로 묶지 않는다(/admin-panel-secret-config 같은 경로를 놓치지 않게)
_SENSITIVE_SEG = re.compile(r"admin|adm|manage|config|secret|private|internal|backup|dump|export|debug|test|dev"
                            r"|staging|env|token|key|password|passwd|login|auth|api|graphql|upload|file|db|sql", re.I)


@dataclass
class HostMap:
    host: str
    pages: dict[str, Fetched] = field(default_factory=dict)    # 연 주소(경로+쿼리) → 응답
    scripts: dict[str, Fetched] = field(default_factory=dict)  # JS URL → 응답
    routes: dict[str, None] = field(default_factory=dict)      # 찾은 모든 경로(열지 않은 것 포함)
    skipped_same_template: int = 0
    skipped_unsafe: int = 0
    skipped_page_limit: int = 0
    opened_pages: int = 0

    def html_pages(self) -> list[tuple[str, Fetched]]:
        return [(p, r) for p, r in self.pages.items() if _is_html(r)]

    def json_pages(self) -> list[tuple[str, Fetched]]:
        return [(p, r) for p, r in self.pages.items() if "json" in (r.header("content-type") or "")]


def template_key(path_and_query: str) -> str:
    """같은 틀인지 비교하는 열쇠. 숫자·UUID·해시·글 제목 같은 칸은 {x}로, 쿼리는 이름만 남긴다."""
    parts = urlsplit(path_and_query)
    segs = []
    for s in parts.path.split("/"):
        if s and (_NUM.fullmatch(s) or _UUID.fullmatch(s) or _HEX.fullmatch(s)
                  or ((_SLUG.fullmatch(s) or _LONG.fullmatch(s) or "%" in s) and not _SENSITIVE_SEG.search(s))):
            segs.append("{x}")
        else:
            segs.append(s)
    key = "/".join(segs) or "/"
    names = sorted({k for k, _ in parse_qsl(parts.query, keep_blank_values=True)})
    return key + ("?" + "&".join(names) if names else "")


def _is_html(r: Fetched) -> bool:
    if "html" in (r.header("content-type") or ""):
        return True
    head = r.text[:256].lstrip().lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


class Crawler:
    """호스트별 대기열을 따로 두고, 서로 다른 호스트는 동시에 돈다(호스트별 속도 제한은 HttpClient가 지킨다)."""

    def __init__(self, http: HttpClient, domain: str, page_limit: int = 0):
        self.http = http
        self.domain = domain
        self.page_limit = page_limit  # 호스트당 여는 페이지 수 상한. 0이면 없음(A2D_CRAWL_PAGE_LIMIT)
        self.maps: dict[str, HostMap] = {}
        self.new_hosts: set[str] = set()
        self._queues: dict[str, deque[tuple[str, str]]] = {}
        self._seen: set[str] = set()                 # 대기열에 넣은 URL(종류 포함)
        self._templates: dict[str, int] = {}         # 호스트+틀 → 연 개수
        self.api_hosts: set[str] = set()             # 상대 API 경로를 같이 넣어 볼 API 서버
        self._pending: dict[str, list[tuple[str, str, bool]]] = {}  # 아직 자산이 아닌 우리 호스트로 가는 링크

    # ------------------------------------------------------------ 바깥에서 부르는 것
    async def crawl(self, hosts: list[str], extra_seeds: dict[str, list[str]] | None = None) -> None:
        """hosts를 대기열에 넣고 모든 대기열이 빌 때까지 돈다. 이미 돈 호스트는 다시 시작하지 않는다."""
        for h in hosts:
            if h in self.maps:
                continue
            self.maps[h] = HostMap(h)
            self._queues[h] = deque()
            self._enqueue(f"https://{h}/", "page")
            self._enqueue(f"https://{h}/robots.txt", "robots")
            self._enqueue(f"https://{h}/sitemap.xml", "sitemap")
            for p in (extra_seeds or {}).get(h, []):
                self._enqueue(f"https://{h}{p}", "page")
            for url, kind, force in self._pending.pop(h, []):  # 자산이 되기 전에 본 링크
                self._enqueue(url, kind, force=force)
        while any(self._queues.values()):
            tasks = [asyncio.ensure_future(self._drain(h)) for h, q in list(self._queues.items()) if q]
            try:
                await asyncio.gather(*tasks)
            except BaseException:
                # 중지 요청·제한 시간(ScanStopped)이면 다른 호스트의 크롤링도 바로 멈추고 엔진까지 올려 보낸다
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

    def in_scope(self, host: str) -> bool:
        return host in self.maps

    # ------------------------------------------------------------ 대기열
    def _enqueue(self, url: str, kind: str, *, force: bool = False) -> None:
        """force: robots·사이트맵처럼 운영자가 직접 적은 경로. 같은 틀이어도 연다(같은 주소만 건너뛴다)."""
        url = url.split("#", 1)[0]
        try:
            parts = urlsplit(url)
        except ValueError:
            return
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            return
        if host not in self.maps:
            if host == self.domain or host.endswith("." + self.domain):
                self.new_hosts.add(host)
                pend = self._pending.setdefault(host, [])
                if (url, kind, force) not in pend:
                    pend.append((url, kind, force))
            return
        path = parts.path or "/"
        pq = path + ("?" + parts.query if parts.query else "")
        hm = self.maps[host]
        hm.routes[path] = None
        if kind == "page":
            if "[" in path or "{" in path or "$" in path:
                return  # 라우터의 변수 자리(/post/[id], /users/:id 등)
            if UNSAFE_ROUTE.search(pq):
                hm.skipped_unsafe += 1
                return
            if JS_EXT.search(path):
                kind = "script"
            elif STATIC_EXT.search(path):
                return
        key = f"{kind} https://{host}{pq}"
        if key in self._seen:
            return
        if kind == "page":
            if self.page_limit and hm.opened_pages >= self.page_limit:
                hm.skipped_page_limit += 1
                return
            tkey = host + template_key(pq)
            if not force and self._templates.get(tkey, 0) >= TEMPLATE_SAMPLES:
                hm.skipped_same_template += 1
                return
            self._templates[tkey] = self._templates.get(tkey, 0) + 1
            hm.opened_pages += 1
        self._seen.add(key)
        self._queues[host].append((kind, f"https://{host}{pq}"))

    async def _drain(self, host: str) -> None:
        q = self._queues[host]
        while q:
            kind, url = q.popleft()
            try:
                await self._visit(host, kind, url)
            except ScanStopped:
                raise  # 중지 버튼·제한 시간은 삼키지 않는다
            except Exception:  # 한 페이지의 이상한 응답이 크롤링 전체를 멈추지 않게 한다
                log.exception("크롤링 실패 %s", url)

    # ------------------------------------------------------------ 방문
    async def _visit(self, host: str, kind: str, url: str) -> None:
        hm = self.maps[host]
        pq = url[len(f"https://{host}"):] or "/"
        if kind == "script":
            r = await self.http.get_cached(url, max_bytes=SCRIPT_MAX_BYTES)
            if r is None or r.status != 200 or _is_html(r):
                return
            hm.scripts[url] = r
            self._from_js(r.text, url)
            return
        if kind == "robots":
            r = await self.http.get_cached(url)
            if r is None or r.status != 200 or _is_html(r):
                return
            for p in _ROBOTS_PATH.findall(r.text):
                p = p.replace("*", "").rstrip("$")
                if p and p != "/":
                    self._enqueue(f"https://{host}{p}", "page", force=True)
            for sm in _ROBOTS_SITEMAP.findall(r.text):
                self._enqueue(urljoin(url, sm), "sitemap")
            return
        if kind == "sitemap":
            r = await self.http.get_cached(url, max_bytes=SITEMAP_MAX_BYTES)
            if r is None or r.status != 200 or _is_html(r):
                return
            nested = "<sitemapindex" in r.text[:2000].lower()
            for loc in _SITEMAP_LOC.findall(r.text):
                self._enqueue(urljoin(url, loc), "sitemap" if nested or loc.endswith(".xml") else "page", force=True)
            return

        r = await self.http.get_cached(url)
        if r is None:
            return
        hm.pages[pq] = r
        if r.status in (301, 302, 303, 307, 308) and r.location:
            self._enqueue(urljoin(url, r.location), "page")
            return
        if r.status >= 400 and r.status < 500:
            return
        if _is_html(r):
            self._from_html(r.text, url)

    def _from_html(self, text: str, base: str) -> None:
        for src in _SCRIPT_SRC.findall(text):
            self._enqueue(urljoin(base, src.replace("&amp;", "&")), "script")
        for link in _LINK_ATTR.findall(text):
            link = link.replace("&amp;", "&")
            if link.startswith(("mailto:", "tel:", "javascript:", "data:")):
                continue
            self._enqueue(urljoin(base, link), "page")
        for m in _META_REFRESH.findall(text):
            self._enqueue(urljoin(base, m), "page")
        # 인라인 스크립트(Next.js __NEXT_DATA__ 등)의 경로도 본다
        self._from_js(text, base, inline=True)

    def _from_js(self, text: str, base: str, inline: bool = False) -> None:
        host = (urlsplit(base).hostname or "").lower()
        targets = {host}
        for m in _ABS_URL.finditer(text):
            h = m.group(1).lower()
            if h in self.maps or h == self.domain or h.endswith("." + self.domain):
                if h in self.maps and (h.startswith("api.") or h.startswith("api-") or h in self.api_hosts):
                    targets.add(h)
                self._enqueue(f"https://{h}{m.group(2) or '/'}", "page")
        for m in _ROUTE_IN_JS.finditer(text):
            self._enqueue(f"https://{host}{m.group(1)}", "page")
        for m in _API_IN_JS.finditer(text):
            for h in targets:  # apiBase + "/api/v1/users" 처럼 다른 우리 서버를 부르는 코드
                self._enqueue(f"https://{h}{m.group(1)}", "page")
        if "_buildManifest" in base or "__BUILD_MANIFEST" in text[:200]:
            for route in _NEXT_MANIFEST_ROUTE.findall(text):
                self._enqueue(f"https://{host}{route}", "page")
        if inline:
            return
        for ref in _JS_CHUNK.findall(text):
            if ref.startswith(("http:", "https:", "//")):
                continue
            if ref.startswith("static/") and "/_next/" in base:
                url = base.split("/_next/", 1)[0] + "/_next/" + ref
            else:
                url = urljoin(base, ref)
            self._enqueue(url, "script")
