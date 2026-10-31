"""API 명세대로 화면 4개의 호출 순서가 동작하는지 가짜 엔진으로 확인한다."""

import time

import pytest
from fastapi.testclient import TestClient

from a2d.config import Settings
from a2d.main import create_app

ORIGIN = "http://localhost:5173"
EMAIL = "admin@jobnest.test"
PASSWORD = "demo-password-only"


@pytest.fixture
def client(tmp_path):
    s = Settings(
        admin_email=EMAIL, admin_password=PASSWORD, db_path=str(tmp_path / "a2d.sqlite3"),
        web_origins=[ORIGIN], verify_mode="trust", fixture_step_sec=0,
    )
    with TestClient(create_app(s), base_url="http://testserver", headers={"Origin": ORIGIN}) as c:
        yield c


def login(c):
    r = c.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r


def wait_done(c, scan_id):
    for _ in range(200):
        body = c.get(f"/api/v1/scans/{scan_id}").json()
        if body["status"] in ("done", "stopped", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError("점검이 끝나지 않음")


def setup_domain(c):
    d = c.post("/api/v1/domains", json={"domain": "jobnest.test"}).json()
    assert c.post(f"/api/v1/domains/{d['domain_id']}/verify").json()["verify_status"] == "verified"
    return d["domain_id"]


def test_login_required_and_session(client):
    assert client.get("/api/v1/health").status_code == 200
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    r = login(client)
    assert "a2d_session" in r.headers["set-cookie"].lower()
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == EMAIL
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204  # 세션이 없어도 204


def test_login_lockout(client):
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong"})
        assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"


def test_origin_and_content_type_guard(client):
    r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN_ORIGIN"
    r = client.post("/api/v1/auth/login", content=b"email=a", headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


def test_domain_validation_and_idempotent_register(client):
    login(client)
    assert client.post("/api/v1/domains", json={"domain": "https://x.com/a"}).status_code == 400
    assert client.post("/api/v1/domains", json={"domain": "1.2.3.4"}).status_code == 400
    r1 = client.post("/api/v1/domains", json={"domain": "JobNest.test."})
    assert r1.status_code == 201
    body = r1.json()
    assert body["txt_record"]["name"] == "_a2d-verify.jobnest.test"
    assert body["txt_record"]["value"].startswith("a2d-verify=") and len(body["txt_record"]["value"]) == 27
    r2 = client.post("/api/v1/domains", json={"domain": "jobnest.test"})
    assert r2.status_code == 200 and r2.json()["domain_id"] == body["domain_id"]
    assert client.get("/api/v1/domains").json()["items"][0]["domain_id"] == body["domain_id"]


def test_scan_requires_verified_domain(client, tmp_path):
    login(client)
    d = client.post("/api/v1/domains", json={"domain": "jobnest.test"}).json()
    r = client.post(f"/api/v1/domains/{d['domain_id']}/scans")
    assert r.status_code == 409 and r.json()["error"]["code"] == "DOMAIN_NOT_VERIFIED"


def test_full_demo_flow(client):
    login(client)
    domain_id = setup_domain(client)

    # 대시보드: 점검 전
    s = client.get(f"/api/v1/domains/{domain_id}/summary").json()
    assert s["latest_scan"] is None and s["today_tasks"] == []

    # 1회차 점검
    r = client.post(f"/api/v1/domains/{domain_id}/scans")
    assert r.status_code == 202 and r.json()["previous_scan_id"] is None
    s1 = r.json()["scan_id"]
    assert client.get(f"/api/v1/scans/{s1}/report").status_code in (200, 409)
    scan = wait_done(client, s1)
    assert scan["status"] == "done" and scan["safety_score"] == 20 and scan["grade"] == "F"

    s = client.get(f"/api/v1/domains/{domain_id}/summary").json()
    assert s["safety_score"] == 20 and s["counts"]["critical"] == 2 and s["counts"]["high"] == 1
    assert [(t["check_id"], t["safety_score_after"], t["grade_after"]) for t in s["today_tasks"]] == [
        (16, 30, "F"), (8, 49, "D"), (18, 100, "A")]
    assert s["alerts"] == [] and s["asset_count"] == 7
    assert s["score_formula"] == "0.7 × 100 + 0.3 × (93 + 73) ÷ 5 = 80"

    assets = client.get(f"/api/v1/scans/{s1}/assets").json()["items"]
    api = next(a for a in assets if a["alias"] == "api")
    assert api["importance"] == {"value": 5, "source": "auto", "rule": "개인정보 형태 응답"}
    assert api["max_severity"] == "critical" and api["finding_count"] == 1

    fs = client.get(f"/api/v1/scans/{s1}/findings").json()["items"]
    assert [f["check_id"] for f in fs] == [16, 8, 18]
    assert client.get(f"/api/v1/scans/{s1}/findings?severity=high").json()["items"][0]["check_id"] == 18
    f16 = fs[0]["finding_id"]
    detail = client.get(f"/api/v1/findings/{f16}").json()
    assert detail["score"]["formula"] == "100 × ((5 × 5 × 5 × 5)^(1/4) − 1) ÷ 4 × 1.0 = 100"

    report = client.get(f"/api/v1/scans/{s1}/report").json()
    assert report["source"] == "template" and report["verification"] == {"passed": 3, "total": 3}
    assert report["items"][0]["finding_ids"] == [f16]

    audit = client.get(f"/api/v1/scans/{s1}/audit?actor=system").json()["items"]
    assert any(a["tool"] == "check_unauth_api" and a["result_summary"] == f"발견 {f16} 기록" for a in audit)
    assert client.get(f"/api/v1/scans/{s1}/audit?rejected=true").json()["items"] == []

    # 질의응답: LLM 없으면 503
    r = client.post(f"/api/v1/scans/{s1}/questions", json={"question": "백업 파일은 왜 위험해요?"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "LLM_UNAVAILABLE"

    # 자산 중요도 수정 → 점수 다시 계산
    r = client.patch(f"/api/v1/domains/{domain_id}/assets/{api['asset_id']}", json={"importance": 4})
    assert r.status_code == 200 and r.json()["asset"]["importance"]["source"] == "manual"
    assert r.json()["summary"]["safety_score"] != 20
    assert client.patch(f"/api/v1/domains/{domain_id}/assets/{api['asset_id']}",
                        json={"importance": 6}).status_code == 400
    client.patch(f"/api/v1/domains/{domain_id}/assets/{api['asset_id']}", json={"importance": 5})

    # 2회차: 세 가지를 고친 뒤 재점검
    s2 = client.post(f"/api/v1/domains/{domain_id}/scans").json()
    assert s2["previous_scan_id"] == s1
    scan2 = wait_done(client, s2["scan_id"])
    assert scan2["safety_score"] == 100 and scan2["grade"] == "A"
    ch = client.get(f"/api/v1/scans/{s2['scan_id']}/changes").json()
    assert ch["safety_score"] == {"before": 20, "after": 100}
    assert len(ch["resolved_findings"]) == 3 and ch["new_findings"] == []
    resolved = client.get(f"/api/v1/scans/{s2['scan_id']}/findings?status=resolved").json()["items"]
    assert {f["finding_id"] for f in resolved} == {f["finding_id"] for f in fs}

    # 3회차: 새 테스트 서버
    s3 = client.post(f"/api/v1/domains/{domain_id}/scans").json()["scan_id"]
    wait_done(client, s3)
    s = client.get(f"/api/v1/domains/{domain_id}/summary").json()
    assert [a["type"] for a in s["alerts"]] == ["new_asset", "new_finding"]
    assert s["today_tasks"][0]["check_id"] == 19

    hist = client.get(f"/api/v1/domains/{domain_id}/history").json()["items"]
    assert [(h["safety_score"], h["new_count"], h["resolved_count"]) for h in hist] == [
        (20, 3, 0), (100, 0, 3), (s["safety_score"], 1, 0)]


def test_first_scan_changes_and_in_progress(client):
    login(client)
    domain_id = setup_domain(client)
    s1 = client.post(f"/api/v1/domains/{domain_id}/scans").json()["scan_id"]
    r = client.post(f"/api/v1/domains/{domain_id}/scans")
    if r.status_code == 409:  # 아직 돌고 있으면
        assert r.json()["error"] == {"code": "SCAN_IN_PROGRESS", "message": r.json()["error"]["message"],
                                     "scan_id": s1}
    wait_done(client, s1)
    ch = client.get(f"/api/v1/scans/{s1}/changes").json()
    assert ch["previous_scan_id"] is None and len(ch["new_findings"]) == 3


def test_stop_scan(tmp_path):
    s = Settings(admin_email=EMAIL, admin_password=PASSWORD, db_path=str(tmp_path / "db.sqlite3"),
                 web_origins=[ORIGIN], verify_mode="trust", fixture_step_sec=0.05)
    with TestClient(create_app(s), headers={"Origin": ORIGIN}) as c:
        login(c)
        domain_id = setup_domain(c)
        scan_id = c.post(f"/api/v1/domains/{domain_id}/scans").json()["scan_id"]
        time.sleep(0.15)
        body = c.post(f"/api/v1/scans/{scan_id}/stop").json()
        assert body["status"] == "stopped" and body["safety_score"] is not None
        assert c.get(f"/api/v1/scans/{scan_id}/report").status_code == 200


def test_not_found(client):
    login(client)
    r = client.get("/api/v1/scans/S-9999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert client.get("/api/v1/findings/F-9999").status_code == 404
