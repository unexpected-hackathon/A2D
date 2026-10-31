"""공개 자료 조회(intel)를 가짜 HTTP로 확인한다. 실제 네트워크는 쓰지 않는다.

고정 응답은 각 서비스의 실제 응답(2026-11-01 확인)에서 필요한 부분만 남긴 것이다.
"""

import asyncio
import datetime as dt
import json

import pytest

from a2d.engine import intel
from a2d.engine.base import ScanStopped
from a2d.engine.net import Fetched

# ---------------------------------------------------------------- 고정 응답(실제 응답을 줄인 것)

# NVD CVE API 2.0, virtualMatchString=cpe:2.3:a:apache:http_server:2.4.49
NVD_APACHE = {
    "resultsPerPage": 4, "startIndex": 0, "totalResults": 4, "format": "NVD_CVE", "version": "2.0",
    "timestamp": "2026-10-31T21:01:44.639",
    "vulnerabilities": [
        {"cve": {"id": "CVE-2021-41524", "vulnStatus": "Modified", "metrics": {
            "cvssMetricV31": [{"source": "nvd@nist.gov", "type": "Primary",
                               "cvssData": {"version": "3.1", "baseScore": 7.5}}],
            "cvssMetricV2": [{"source": "nvd@nist.gov", "type": "Primary",
                              "cvssData": {"version": "2.0", "baseScore": 5.0}}]}}},
        {"cve": {"id": "CVE-2021-41773", "vulnStatus": "Analyzed", "cisaExploitAdd": "2021-11-03", "metrics": {
            "cvssMetricV31": [
                {"source": "134c704f-9b21-4f2e-91b3-4a467353bcc0", "type": "Secondary",
                 "cvssData": {"version": "3.1", "baseScore": 7.5}},
                {"source": "nvd@nist.gov", "type": "Primary", "cvssData": {"version": "3.1", "baseScore": 9.8}}],
            "cvssMetricV2": [{"source": "nvd@nist.gov", "type": "Primary",
                              "cvssData": {"version": "2.0", "baseScore": 4.3}}]}}},
        {"cve": {"id": "CVE-2021-42013", "vulnStatus": "Analyzed", "cisaExploitAdd": "2021-11-03", "metrics": {
            "cvssMetricV31": [{"source": "nvd@nist.gov", "type": "Primary",
                               "cvssData": {"version": "3.1", "baseScore": 9.8}}]}}},
        {"cve": {"id": "CVE-2006-20001", "vulnStatus": "Awaiting Analysis", "metrics": {}}},
    ],
}
NVD_EMPTY = {"resultsPerPage": 0, "startIndex": 0, "totalResults": 0, "format": "NVD_CVE",
             "version": "2.0", "timestamp": "2026-10-31T21:05:00.000", "vulnerabilities": []}

# CISA KEV (known_exploited_vulnerabilities.json)
KEV = {
    "title": "CISA Catalog of Known Exploited Vulnerabilities", "catalogVersion": "2026.10.30",
    "dateReleased": "2026-10-30T17:02:45.3665Z", "count": 3,
    "vulnerabilities": [
        {"cveID": "CVE-2021-41773", "vendorProject": "Apache", "product": "HTTP Server",
         "dateAdded": "2021-11-03", "knownRansomwareCampaignUse": "Known"},
        {"cveID": "CVE-2021-42013", "vendorProject": "Apache", "product": "HTTP Server",
         "dateAdded": "2021-11-03", "knownRansomwareCampaignUse": "Known"},
        {"cveID": "CVE-2021-41524", "vendorProject": "Apache", "product": "HTTP Server",
         "dateAdded": "2026-10-30", "knownRansomwareCampaignUse": "Unknown"},  # 시험용: NVD 표시 없이 KEV에만 있음
    ],
}


def eol_v1(name: str, releases: list[tuple]) -> dict:
    """endoflife.date API v1 /products/<name> 응답 꼴."""
    return {"schema_version": "1.2.1", "generated_at": "2026-10-31T13:22:44+00:00",
            "result": {"name": name, "releases": [
                {"name": n, "isEol": is_eol, "eolFrom": eol_from, "isMaintained": not is_eol}
                for n, is_eol, eol_from in releases]}}


EOL_PHP = eol_v1("php", [("8.5", False, "2029-12-31"), ("8.4", False, "2028-12-31"),
                         ("8.1", True, "2025-12-31"), ("8.0", True, "2023-11-26")])
EOL_NGINX = eol_v1("nginx", [("1.31", False, None), ("1.30", False, None), ("1.18", True, "2021-04-20"),
                             ("1.1", True, "2012-05-15")])
EOL_OPENSSL = eol_v1("openssl", [("3.6", False, "2026-11-01"), ("3.5", False, "2030-04-08"),
                                 ("1.1.1", True, "2023-09-11"), ("1.1.0", True, "2019-09-11")])
EOL_APACHE = eol_v1("apache-http-server", [("2.4", False, None), ("2.2", True, "2017-07-11")])
EOL_WINDOWS = eol_v1("windows-server", [("2016", False, "2027-01-12"), ("2008-r2-sp1", True, "2020-01-14")])
# 예전 API(/api/<name>.json) 꼴: eol이 날짜이거나 참거짓
EOL_LEGACY = [{"cycle": "8.2", "eol": "2026-12-31"}, {"cycle": "7.4", "eol": True}, {"cycle": "8.3", "eol": False}]

# IANA RDAP 부트스트랩(data.iana.org/rdap/dns.json)
IANA = {"description": "RDAP bootstrap file for Domain Name System registrations",
        "publication": "2026-10-28T22:00:04Z", "version": "1.0",
        "services": [[["kg"], ["http://rdap.cctld.kg/"]],
                     [["kr", "xn--3e0b707e"], ["https://rdap.nic.or.kr/"]],
                     [["com"], ["https://rdap.verisign.com/com/v1/"]],
                     [["dev", "app"], ["http://pubapi.registry.google/rdap/", "https://pubapi.registry.google/rdap/"]]]}

RDAP_GOOGLE = {"objectClassName": "domain", "ldhName": "GOOGLE.COM",
               "status": ["client delete prohibited", "client transfer prohibited", "client update prohibited",
                          "server delete prohibited", "server transfer prohibited", "server update prohibited"],
               "events": [{"eventAction": "registration", "eventDate": "1997-09-15T04:00:00Z"},
                          {"eventAction": "expiration", "eventDate": "2028-09-14T04:00:00Z"},
                          {"eventAction": "last changed", "eventDate": "2019-09-09T15:39:04Z"}]}
RDAP_NAVER = {"objectClassName": "domain", "ldhName": "naver.co.kr", "status": ["active"],
              "events": [{"eventAction": "registration", "eventDate": "1998-05-25T15:00:00Z"},
                         {"eventAction": "expiration", "eventDate": "2027-10-14T15:00:00Z"}]}
RDAP_KISA = {"objectClassName": "domain", "ldhName": "kisa.or.kr",
             "status": ["server delete prohibited", "server transfer prohibited", "server update prohibited"],
             "events": [{"eventAction": "expiration", "eventDate": "9999-12-30T15:00:00Z"}]}
RDAP_NOT_FOUND = {"errorCode": 404, "title": "Not Found"}


# ---------------------------------------------------------------- 가짜 HTTP

def resp(url: str, body, status: int = 200, location: str | None = None) -> Fetched:
    text = body if isinstance(body, str) else json.dumps(body)
    return Fetched(url=url, status=status, headers={}, text=text, scheme="https", location=location)


class FakeHttp:
    """주소 앞부분으로 응답을 고른다. 받은 요청(주소·헤더·max_bytes)을 기록한다."""

    def __init__(self, routes: dict):
        self.routes = routes  # 앞부분 → (body, status) | body | None(연결 실패) | Exception
        self.calls: list[tuple[str, dict | None, int]] = []

    async def get(self, url, extra_headers=None, *, timeout=10.0, max_bytes=262144):
        self.calls.append((url, extra_headers, max_bytes))
        for prefix in sorted(self.routes, key=len, reverse=True):
            if url.startswith(prefix):
                route = self.routes[prefix]
                if isinstance(route, Exception):
                    raise route
                if route is None:
                    return None
                if isinstance(route, Fetched):
                    return route
                body, status = route if isinstance(route, tuple) else (route, 200)
                return resp(url, body, status)
        return resp(url, "not found", 404)

    def urls(self, prefix: str = "") -> list[str]:
        return [u for u, _, _ in self.calls if u.startswith(prefix)]


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    intel.clear_caches()
    monkeypatch.delenv("A2D_NVD_API_KEY", raising=False)
    yield
    intel.clear_caches()


NVD = intel.NVD_URL
KEV_URL = intel.KEV_URL


# ---------------------------------------------------------------- #23 CVE

def test_cves_parse_cvss_kev_and_sort():
    http = FakeHttp({NVD: NVD_APACHE, KEV_URL: KEV})
    out = run(intel.cves(http, "apache", "2.4.49"))
    assert out == [
        {"id": "CVE-2021-41773", "cvss": 9.8, "kev": True},  # Primary(NVD) 점수를 쓴다
        {"id": "CVE-2021-42013", "cvss": 9.8, "kev": True},
        {"id": "CVE-2021-41524", "cvss": 7.5, "kev": True},  # NVD 표시는 없지만 KEV 목록에 있다
        {"id": "CVE-2006-20001", "cvss": None, "kev": False},  # 점수 없음은 맨 뒤
    ]
    nvd_url = http.urls(NVD)[0]
    assert "virtualMatchString=cpe:2.3:a:apache:http_server:2.4.49" in nvd_url
    assert "noRejected" in nvd_url
    # 큰 응답을 잘리지 않게 받는다
    assert all(mb >= 16 * 1024 * 1024 for _, _, mb in http.calls)


def test_cves_no_vulns_is_empty_list():
    http = FakeHttp({NVD: NVD_EMPTY, KEV_URL: KEV})
    assert run(intel.cves(http, "php", "8.4.27")) == []


@pytest.mark.parametrize("route", [None, ("Service Unavailable", 503), ("Forbidden", 403), "<html>not json",
                                   {"message": "no vulnerabilities key"}])
def test_cves_lookup_failure_is_none(route):
    http = FakeHttp({NVD: route, KEV_URL: KEV})
    assert run(intel.cves(http, "apache", "2.4.49")) is None


def test_cves_unknown_product_or_bad_version_makes_no_request():
    http = FakeHttp({})
    assert run(intel.cves(http, "express", "4.17.1")) is None
    assert run(intel.cves(http, "apache", "2.4.49&x=1")) is None
    assert run(intel.cves(http, "apache", "")) is None
    assert http.calls == []


def test_cves_kev_feed_down_uses_nvd_flag():
    http = FakeHttp({NVD: NVD_APACHE, KEV_URL: None})
    out = {v["id"]: v["kev"] for v in run(intel.cves(http, "apache", "2.4.49"))}
    assert out == {"CVE-2021-41773": True, "CVE-2021-42013": True,
                   "CVE-2021-41524": False, "CVE-2006-20001": False}


def test_cves_nginx_uses_any_vendor_and_iis_merges_two_names():
    http = FakeHttp({NVD: NVD_EMPTY, KEV_URL: KEV})
    run(intel.cves(http, "nginx", "1.18.0"))
    run(intel.cves(http, "IIS", "7.5"))
    urls = http.urls(NVD)
    assert "virtualMatchString=cpe:2.3:a:*:nginx:1.18.0&" in urls[0]
    assert any("microsoft:internet_information_services:7.5&" in u for u in urls)
    assert any("microsoft:internet_information_server:7.5&" in u for u in urls)


def test_cves_iis_dedupes_across_names():
    http = FakeHttp({NVD: NVD_APACHE, KEV_URL: KEV})
    out = run(intel.cves(http, "iis", "7.5"))
    assert len(http.urls(NVD)) == 2
    assert len(out) == len({v["id"] for v in out}) == 4


def test_cves_pages_through_results():
    page1 = {**NVD_APACHE, "totalResults": 5, "vulnerabilities": NVD_APACHE["vulnerabilities"]}
    page2 = {**NVD_APACHE, "startIndex": 4, "totalResults": 5,
             "vulnerabilities": [{"cve": {"id": "CVE-2099-0001", "metrics": {}}}]}
    http = FakeHttp({f"{NVD}?": page1, KEV_URL: KEV})
    http.routes[f"{NVD}?virtualMatchString=cpe:2.3:a:apache:http_server:2.4.49&noRejected"
                f"&resultsPerPage=2000&startIndex=4"] = page2
    out = run(intel.cves(http, "apache", "2.4.49"))
    assert "CVE-2099-0001" in {v["id"] for v in out}
    assert len(http.urls(NVD)) == 2


def test_cves_and_kev_are_cached():
    http = FakeHttp({NVD: NVD_APACHE, KEV_URL: KEV})
    first = run(intel.cves(http, "apache", "2.4.49"))
    first[0]["cvss"] = 0  # 돌려준 값을 고쳐도 보관한 값은 그대로다
    second = run(intel.cves(http, "apache", "2.4.49"))
    run(intel.cves(http, "apache", "2.4.50"))
    assert second[0]["cvss"] == 9.8
    assert len(http.urls(NVD)) == 2  # 2.4.49 한 번, 2.4.50 한 번
    assert len(http.urls(KEV_URL)) == 1


def test_kev_cache_expires_after_ttl(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(intel, "_clock", lambda: now[0])
    http = FakeHttp({KEV_URL: KEV})
    assert "CVE-2021-42013" in run(intel.kev_catalog(http))
    now[0] += intel.CACHE_TTL - 1
    run(intel.kev_catalog(http))
    assert len(http.calls) == 1
    now[0] += 2
    http.routes[KEV_URL] = None  # 다시 받지 못하면 지난 목록을 쓴다
    assert "CVE-2021-42013" in run(intel.kev_catalog(http))
    assert len(http.calls) == 2


def test_nvd_api_key_header_and_retry_without_bad_key(monkeypatch):
    monkeypatch.setenv("A2D_NVD_API_KEY", "k-123")
    seen = []

    class KeyedHttp(FakeHttp):
        async def get(self, url, extra_headers=None, *, timeout=10.0, max_bytes=262144):
            if url.startswith(NVD):
                seen.append(extra_headers)
                if extra_headers and extra_headers.get("apiKey") == "k-123":
                    return resp(url, "", 404)  # NVD는 잘못된 키에 404를 준다
            return await super().get(url, extra_headers, timeout=timeout, max_bytes=max_bytes)

    http = KeyedHttp({NVD: NVD_EMPTY, KEV_URL: KEV})
    assert run(intel.cves(http, "php", "8.1.2")) == []
    assert seen == [{"apiKey": "k-123"}, None]


def test_scan_stopped_propagates():
    http = FakeHttp({NVD: ScanStopped("중지 요청"), "https://endoflife.date/": ScanStopped("중지 요청"),
                     intel.RDAP_BOOTSTRAP_URL: ScanStopped("중지 요청")})
    with pytest.raises(ScanStopped):
        run(intel.cves(http, "apache", "2.4.49"))
    with pytest.raises(ScanStopped):
        run(intel.end_of_life(http, "php", "8.1.2"))
    with pytest.raises(ScanStopped):
        run(intel.domain_registration(http, "google.com"))


def test_unexpected_error_is_soft():
    http = FakeHttp({NVD: RuntimeError("boom"), "https://endoflife.date/": RuntimeError("boom"),
                     intel.RDAP_BOOTSTRAP_URL: RuntimeError("boom")})
    assert run(intel.cves(http, "apache", "2.4.49")) is None
    assert run(intel.end_of_life(http, "php", "8.1.2")) is None
    assert run(intel.domain_registration(http, "google.com")) is None


# ---------------------------------------------------------------- #25 지원 종료

EOL_ROUTES = {
    "https://endoflife.date/api/v1/products/php": EOL_PHP,
    "https://endoflife.date/api/v1/products/nginx": EOL_NGINX,
    "https://endoflife.date/api/v1/products/openssl": EOL_OPENSSL,
    "https://endoflife.date/api/v1/products/apache-http-server": EOL_APACHE,
    "https://endoflife.date/api/v1/products/windows-server": EOL_WINDOWS,
}


@pytest.mark.parametrize("product,version,expected", [
    ("php", "8.1.2", True),
    ("php", "8.4.1", False),
    ("php", "8.0", True),
    ("openssl", "1.1.1k", True),
    ("openssl", "1.1.1", True),
    ("openssl", "3.5.4", False),
    ("nginx", "1.18.0", True),   # 1.1이 아니라 1.18과 맞춘다
    ("nginx", "1.31.0", False),  # eolFrom 없음 → isEol
    ("apache", "2.4.49", False),
    ("apache", "2.2.34", True),
    ("iis", "7.5", True),        # 윈도 서버 2008 R2
    ("php", "5.6.40", None),     # 표에 없는 주기
    ("express", "4.17.1", None),
])
def test_end_of_life(product, version, expected, monkeypatch):
    monkeypatch.setattr(intel, "_today", lambda: dt.date(2026, 10, 31))
    assert run(intel.end_of_life(FakeHttp(EOL_ROUTES), product, version)) is expected


def test_end_of_life_date_on_today_counts(monkeypatch):
    monkeypatch.setattr(intel, "_today", lambda: dt.date(2026, 11, 1))
    assert run(intel.end_of_life(FakeHttp(EOL_ROUTES), "openssl", "3.6.0")) is True  # eolFrom == 오늘


def test_end_of_life_legacy_shape(monkeypatch):
    monkeypatch.setattr(intel, "_today", lambda: dt.date(2026, 11, 1))
    http = FakeHttp({"https://endoflife.date/api/v1/products/php": EOL_LEGACY})
    assert run(intel.end_of_life(http, "php", "7.4.33")) is True
    assert run(intel.end_of_life(http, "php", "8.3.1")) is False
    assert run(intel.end_of_life(http, "php", "8.2.0")) is False


def test_end_of_life_iis10_unknown_without_request():
    http = FakeHttp(EOL_ROUTES)
    assert run(intel.end_of_life(http, "iis", "10.0")) is None
    assert http.calls == []


@pytest.mark.parametrize("route", [None, ("Page not Found", 404), "<html>"])
def test_end_of_life_failure_is_none(route):
    http = FakeHttp({"https://endoflife.date/": route})
    assert run(intel.end_of_life(http, "php", "8.1.2")) is None


def test_end_of_life_cached_per_product():
    http = FakeHttp(EOL_ROUTES)
    run(intel.end_of_life(http, "php", "8.1.2"))
    run(intel.end_of_life(http, "php", "8.4.1"))
    run(intel.end_of_life(http, "nginx", "1.18.0"))
    assert http.urls() == ["https://endoflife.date/api/v1/products/php",
                           "https://endoflife.date/api/v1/products/nginx"]


# ---------------------------------------------------------------- #33 도메인 등록 정보

RDAP_ROUTES = {
    intel.RDAP_BOOTSTRAP_URL: IANA,
    "https://rdap.verisign.com/com/v1/domain/google.com": RDAP_GOOGLE,
    "https://rdap.nic.or.kr/domain/naver.co.kr": RDAP_NAVER,
    "https://rdap.nic.or.kr/domain/kisa.or.kr": RDAP_KISA,
    "https://rdap.nic.or.kr/domain/": (RDAP_NOT_FOUND, 404),
}


def test_rdap_com_expiry_and_lock():
    http = FakeHttp(RDAP_ROUTES)
    out = run(intel.domain_registration(http, "Google.com."))
    assert out == {"expires": dt.datetime(2028, 9, 14, 4, 0, tzinfo=dt.timezone.utc), "transfer_locked": True}
    assert http.urls()[-1] == "https://rdap.verisign.com/com/v1/domain/google.com"


def test_rdap_kr_multi_label_and_unlocked():
    http = FakeHttp(RDAP_ROUTES)
    out = run(intel.domain_registration(http, "naver.co.kr"))
    assert out == {"expires": dt.datetime(2027, 10, 14, 15, 0, tzinfo=dt.timezone.utc), "transfer_locked": False}
    assert http.urls()[-1] == "https://rdap.nic.or.kr/domain/naver.co.kr"


def test_rdap_public_domain_9999():
    out = run(intel.domain_registration(FakeHttp(RDAP_ROUTES), "kisa.or.kr"))
    assert out["expires"].year == 9999 and out["transfer_locked"] is True


def test_rdap_follows_redirect():
    http = FakeHttp({**RDAP_ROUTES,
                     "https://rdap.verisign.com/com/v1/domain/moved.com":
                         resp("https://rdap.verisign.com/com/v1/domain/moved.com", "", 307,
                              location="https://rdap.example.net/domain/moved.com"),
                     "https://rdap.example.net/domain/moved.com": RDAP_NAVER})
    out = run(intel.domain_registration(http, "moved.com"))
    assert out["transfer_locked"] is False


def test_rdap_missing_fields_are_none():
    http = FakeHttp({**RDAP_ROUTES, "https://rdap.verisign.com/com/v1/domain/bare.com": {"objectClassName": "domain"}})
    assert run(intel.domain_registration(http, "bare.com")) == {"expires": None, "transfer_locked": None}


@pytest.mark.parametrize("domain", ["jobnest.test", "a.example", "x.invalid", "localhost", "host.local",
                                    "svc.internal", "", "nodot"])
def test_rdap_reserved_makes_no_request(domain):
    http = FakeHttp(RDAP_ROUTES)
    assert run(intel.domain_registration(http, domain)) is None
    assert http.calls == []


def test_rdap_failures_are_none():
    assert run(intel.domain_registration(FakeHttp(RDAP_ROUTES), "nosuch.co.kr")) is None  # 404
    assert run(intel.domain_registration(FakeHttp(RDAP_ROUTES), "example.zz")) is None  # 부트스트랩에 없음
    assert run(intel.domain_registration(FakeHttp({intel.RDAP_BOOTSTRAP_URL: None}), "google.com")) is None


def test_rdap_bootstrap_cached_and_prefers_https():
    http = FakeHttp({**RDAP_ROUTES, "https://pubapi.registry.google/rdap/domain/web.dev": RDAP_NAVER})
    run(intel.domain_registration(http, "google.com"))
    run(intel.domain_registration(http, "naver.co.kr"))
    assert run(intel.domain_registration(http, "web.dev")) is not None
    assert len(http.urls(intel.RDAP_BOOTSTRAP_URL)) == 1


def test_rdap_idn_uses_punycode():
    http = FakeHttp({**RDAP_ROUTES, "https://rdap.nic.or.kr/domain/xn--": RDAP_NAVER})
    assert run(intel.domain_registration(http, "예시.한국")) is not None
    assert http.urls()[-1].startswith("https://rdap.nic.or.kr/domain/xn--")
