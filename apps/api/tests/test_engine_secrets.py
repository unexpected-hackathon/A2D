"""화면 코드 속 비밀키(#12)·소스맵(#13) 판정이 오탐·중복 없이 맞는지 본다.

비밀키 형태 문자열은 저장소에 그대로 남기지 않으려고 실행 중에 이어 붙인다(target/config.py와 같은 방식).
"""

import base64
import json

import pytest

from a2d.engine.live import _is_sourcemap, _secret_kinds, _sourcemap_url
from a2d.engine.net import Fetched
from tests.test_engine_live import found, run_engine

AWS_REAL = "AKIA" + "ZZ2QWERTY9ABCDEF"
AWS_DOC_EXAMPLE = "AKIA" + "IOSFODNN7EXAMPLE"  # AWS 문서에 나오는 예시 키
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEow...\n"


def jwt(payload: dict) -> str:
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64(payload)}.c2lnbmF0dXJlLXZhbHVl"


@pytest.mark.parametrize("text, kinds", [
    (f'accessKeyId: "{AWS_REAL}"', ["AWS 액세스 키"]),
    (f'// 예: accessKeyId "{AWS_DOC_EXAMPLE}"', []),                     # 문서용 예시 키
    ("// service_role 키는 서버에서만 쓴다", []),                          # 단어만 나옴
    (f'createClient(url, "{jwt({"iss": "supabase", "role": "anon"})}")', []),  # 공개용 anon 키
    (f'createClient(url, "{jwt({"iss": "supabase", "role": "service_role"})}")', ["Supabase service_role 키"]),
    (f"const key = `{PRIVATE_KEY}`", ["개인 키 파일"]),
    ('stripe("pk_live_51Habcdefghijklmn")', []),                          # Stripe 공개 키
])
def test_secret_kinds(text, kinds):
    assert _secret_kinds(text) == kinds


def test_real_key_next_to_example_key_still_found():
    assert _secret_kinds(f"{AWS_DOC_EXAMPLE} {AWS_REAL}") == ["AWS 액세스 키"]


def test_sourcemap_url_follows_comment():
    base = "https://www.shop.example/assets/index-3f2a.js"
    assert _sourcemap_url("x\n//# sourceMappingURL=index-3f2a.js.map\n", base) == \
        "https://www.shop.example/assets/index-3f2a.js.map"
    assert _sourcemap_url("x\n//# sourceMappingURL=/maps/app.map", base) == "https://www.shop.example/maps/app.map"
    assert _sourcemap_url("x\n//# sourceMappingURL=data:application/json;base64,eyJ9", base) is None
    assert _sourcemap_url("console.log(1)", base) is None


def test_is_sourcemap_rejects_spa_index():
    def r(text, ctype):
        return Fetched(url="https://x/app.js.map", status=200, headers={"content-type": ctype}, text=text,
                       scheme="https")

    assert _is_sourcemap(r(json.dumps({"version": 3, "sources": [], "mappings": "AAAA"}), "application/json"))
    assert not _is_sourcemap(r("<!doctype html><html><div id=root></div></html>", "text/html"))


def test_key_in_code_and_sourcemap_reported_once():
    _, findings, _, _ = run_engine(set())
    secrets = [f for f in findings if f.check_id == 12]
    assert len(secrets) == 1 and secrets[0].location.endswith("/static/js/app.js")
    # 소스맵이 열린 것 자체는 #13으로 따로 남는다. 안 그러면 #12를 고친 뒤 재점검에서 #13이 새 발견으로 튀어나온다
    maps = [f for f in findings if f.check_id == 13]
    assert len(maps) == 1 and maps[0].location.endswith("/static/js/app.js.map")
