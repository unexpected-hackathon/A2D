"""쿠키 보안 속성(#31)을 쿠키마다 따로 보는지 확인한다.

httpx는 여러 Set-Cookie를 headers에서 쉼표로 합친다. 합친 문자열로 보면 다른 쿠키의 Secure가
속성이 하나도 없는 로그인 쿠키를 가린다.
"""

import asyncio

import httpx
import pytest

from a2d.engine.base import Budget
from a2d.engine.live import _cookie_attrs
from a2d.engine.net import HttpClient
from tests.test_engine_live import found, run_engine


def fetch_with_cookies(cookies: list[str]):
    def handler(request):
        return httpx.Response(200, text="ok", headers=[("set-cookie", c) for c in cookies])

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await HttpClient(Budget(10, 1, 60), client, host_min_interval=0).get("https://www.x.test/")

    return asyncio.run(go())


def test_fetched_keeps_each_set_cookie():
    r = fetch_with_cookies(["sid=1", "pref=dark; Secure; HttpOnly; SameSite=Lax"])
    assert r.set_cookies == ["sid=1", "pref=dark; Secure; HttpOnly; SameSite=Lax"]


@pytest.mark.parametrize("cookie, name, attrs", [
    ("sid=1", "sid", set()),
    ("jn_session=x; HttpOnly; Secure; SameSite=lax", "jn_session", {"httponly", "secure", "samesite"}),
    ("secure_pref=1; Path=/", "secure_pref", {"path"}),  # 이름에 secure가 있어도 속성이 아니다
])
def test_cookie_attrs(cookie, name, attrs):
    assert _cookie_attrs(cookie) == (name, attrs)


def _check(cookies):
    from a2d.engine.live import Asset, LiveEngine
    from a2d.config import Settings

    r = fetch_with_cookies(cookies)
    added = []

    class Ctx:
        def add_finding(self, f):
            added.append(f)
            return "F", "A"

    class Http:
        async def get(self, url):
            return r

    a = Asset("www.x.test", "www", "web", 4, "대표 홈페이지")
    asyncio.run(LiveEngine(Settings(), dns=object(), tls=object())._check_cookie(Ctx(), Http(), a))
    return added


def test_weak_session_cookie_not_masked_by_other_cookie():
    added = _check(["sid=1", "pref=dark; Secure; HttpOnly; SameSite=Lax"])
    assert [(f.check_id, f.situation) for f in added] == [(31, "login")]
    assert "sid" in added[0].evidence


def test_all_cookies_safe_no_finding():
    assert _check(["sid=1; Secure; HttpOnly; SameSite=Lax", "pref=dark; Secure; HttpOnly; SameSite=Lax"]) == []


def test_non_session_cookie_is_other():
    added = _check(["sid=1; Secure; HttpOnly; SameSite=Lax", "pref=dark"])
    assert [(f.check_id, f.situation) for f in added] == [(31, "other")]


def test_target_cookie_still_reported():
    assert (31, "login") in found(run_engine(set())[1])
