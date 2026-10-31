"""공개 자료 조회: 알려진 취약점(#23), 지원 종료(#25), 도메인 등록 정보(#33).

내장 표 대신 공개 자료를 그때그때 묻는다. 대상이 아니라 아래 공개 서비스에 요청한다.
- 알려진 취약점: NVD CVE API 2.0 (제품·버전을 CPE로 바꿔 묻는다)
- 실제 악용된 취약점: CISA KEV 목록(JSON 한 파일). NVD 응답의 cisaExploitAdd도 함께 본다
- 지원 종료: endoflife.date API v1
- 도메인 등록 정보: RDAP. IANA 부트스트랩 파일에서 최상위 도메인의 RDAP 서버를 찾는다

요청은 점검의 HttpClient로 보낸다(요청 예산·속도 제한·User-Agent를 그대로 지킨다).
모든 함수는 실패해도 예외를 올리지 않고 None(모름)을 돌려준다. 단 ScanStopped는 그대로 올려 보낸다.
큰 목록(KEV·부트스트랩·제품별 지원 일정)은 모듈 안에 24시간 보관해 점검마다 다시 받지 않는다.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import time
from urllib.parse import urljoin

from .base import ScanStopped

log = logging.getLogger("a2d.engine.intel")

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EOL_URL = "https://endoflife.date/api/v1/products/{slug}"
RDAP_BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"

CACHE_TTL = 24 * 3600
LOOKUP_TIMEOUT = 30.0  # NVD는 1~2초, 느릴 때는 더 걸린다
BIG_BODY = 32 * 1024 * 1024  # KEV 목록은 약 2MB, 오래된 버전의 CVE 목록은 수 MB가 될 수 있다
NVD_PAGE_SIZE = 2000  # NVD 한 번에 최대 건수
NVD_MAX_PAGES = 3
RDAP_MAX_REDIRECTS = 2  # rdap.kr처럼 다른 서버로 넘기는 곳이 있다. HttpClient는 리다이렉트를 따르지 않는다

# 제품 → NVD CPE(공급자:제품). 여러 개면 모두 묻고 합친다.
# nginx는 예전 nginx:nginx에서 f5:nginx로 옮겨 갔다. 공급자를 *로 두면 한 번에 둘 다 찾는다.
# IIS는 internet_information_server와 internet_information_services 두 이름에 나뉘어 있다.
NVD_CPES: dict[str, tuple[str, ...]] = {
    "apache": ("apache:http_server",),
    "nginx": ("*:nginx",),
    "php": ("php:php",),
    "openssl": ("openssl:openssl",),
    "iis": ("microsoft:internet_information_services", "microsoft:internet_information_server"),
}

# 제품 → endoflife.date 제품 이름. IIS는 따로 없어 윈도 서버 일정으로 본다.
EOL_SLUGS = {
    "apache": "apache-http-server",
    "nginx": "nginx",
    "php": "php",
    "openssl": "openssl",
    "iis": "windows-server",
}
# IIS 버전 → 함께 나온 윈도 서버. IIS 10.0은 2016~2025에 모두 들어 있어 알 수 없다.
IIS_RELEASES = {
    "5.0": "2000",
    "6.0": "2003-sp2",
    "7.0": "2008-sp2",
    "7.5": "2008-r2-sp1",
    "8.0": "2012",
    "8.5": "2012-r2",
}

# 조회하지 않는 예약 최상위 도메인(RFC 2606·6761·9476 등). 시연 대상(.test)도 여기에 든다.
RESERVED_TLDS = {"test", "example", "invalid", "localhost", "local", "internal", "alt"}

_VERSION = re.compile(r"[0-9][0-9A-Za-z._-]{0,40}")
_TRANSFER_LOCKS = {"clienttransferprohibited", "servertransferprohibited"}
_REDIRECTS = (301, 302, 303, 307, 308)


# ==================================================================== 보관(24시간)

_clock = time.monotonic  # 테스트가 바꿔 끼운다
_kev: tuple[float, frozenset[str]] | None = None
_cve_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_eol_cache: dict[str, tuple[float, list[dict]]] = {}
_rdap_bootstrap: tuple[float, dict[str, str]] | None = None


def clear_caches() -> None:
    """보관한 조회 결과를 모두 지운다(테스트용)."""
    global _kev, _rdap_bootstrap
    _kev = None
    _rdap_bootstrap = None
    _cve_cache.clear()
    _eol_cache.clear()


def _fresh(saved_at: float) -> bool:
    return _clock() - saved_at < CACHE_TTL


def _today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


async def _get_json(http, url: str, headers: dict[str, str] | None = None, *,
                    timeout: float = LOOKUP_TIMEOUT, max_bytes: int = BIG_BODY, redirects: int = 0):
    """GET 후 200이면 JSON을 돌려준다. 그 밖에는 None.

    리다이렉트는 redirects번까지만, https 주소로만 따라간다. RDAP(rdap.kr → rdap.nic.or.kr)만 쓰고,
    NVD·KEV·endoflife.date는 따라가지 않는다(공개 자료 쪽의 열린 리다이렉트로 다른 곳에 나가지 않게).
    """
    for _ in range(redirects + 1):
        r = await http.get(url, headers, timeout=timeout, max_bytes=max_bytes)
        if r is None:
            return None
        if r.status in _REDIRECTS and getattr(r, "location", None):
            nxt = urljoin(url, r.location)
            if redirects == 0 or not nxt.startswith("https://"):
                log.info("공개 자료 리다이렉트를 따라가지 않음 %s → %s", url, nxt)
                return None
            url = nxt
            continue
        if r.status != 200:
            log.info("공개 자료 조회 실패 %s: HTTP %s", url, r.status)
            return None
        try:
            return json.loads(r.text)
        except ValueError:
            log.info("공개 자료 응답을 읽지 못함 %s", url)
            return None
    return None


# ==================================================================== #23 알려진 취약점

async def cves(http, product: str, version: str) -> list[dict] | None:
    """서버 제품 버전의 알려진 취약점. [{"id", "cvss", "kev"}]를 CVSS 높은 순으로 돌려준다.

    취약점이 없으면 [], 조회하지 못했거나 모르는 제품이면 None이다(모름과 없음을 구분한다).
    """
    try:
        return await _cves(http, product, version)
    except ScanStopped:
        raise
    except Exception:
        log.exception("CVE 조회 실패 %s %s", product, version)
        return None


async def _cves(http, product: str, version: str) -> list[dict] | None:
    product = (product or "").lower()
    cpes = NVD_CPES.get(product)
    if not cpes or not version or not _VERSION.fullmatch(version):
        return None
    key = (product, version)
    saved = _cve_cache.get(key)
    if saved and _fresh(saved[0]):
        return [dict(v) for v in saved[1]]

    found: dict[str, dict] = {}
    for cpe in cpes:
        items = await _nvd_query(http, f"cpe:2.3:a:{cpe}:{version}")
        if items is None:
            return None
        for item in items:
            v = _parse_nvd_item(item)
            if v and v["id"] not in found:
                found[v["id"]] = v

    kev_ids = await kev_catalog(http)  # 받지 못하면 NVD의 cisaExploitAdd만 본다
    out = []
    for v in found.values():
        kev = v.pop("_kev") or (kev_ids is not None and v["id"] in kev_ids)
        out.append({"id": v["id"], "cvss": v["cvss"], "kev": kev})
    out.sort(key=lambda v: (-(v["cvss"] if v["cvss"] is not None else -1.0), not v["kev"], v["id"]))
    _cve_cache[key] = (_clock(), [dict(v) for v in out])
    return out


async def _nvd_query(http, cpe: str) -> list[dict] | None:
    """virtualMatchString으로 그 버전에 해당하는 CVE를 모두 받는다. 실패하면 None."""
    api_key = os.environ.get("A2D_NVD_API_KEY", "").strip()
    items: list[dict] = []
    start = 0
    for _ in range(NVD_MAX_PAGES):
        url = (f"{NVD_URL}?virtualMatchString={cpe}&noRejected"
               f"&resultsPerPage={NVD_PAGE_SIZE}&startIndex={start}")
        data = await _get_json(http, url, {"apiKey": api_key} if api_key else None)
        if data is None and api_key:
            # NVD는 잘못된 인증키에 404를 준다. 키 없이 한 번 더 묻는다
            api_key = ""
            data = await _get_json(http, url)
        if not isinstance(data, dict) or not isinstance(data.get("vulnerabilities"), list):
            return None
        page = data["vulnerabilities"]
        items.extend(page)
        total = data.get("totalResults")
        start += len(page)
        if not page or not isinstance(total, int) or start >= total:
            return items
    log.info("NVD 결과가 너무 많아 앞쪽 %d건만 봄 %s", len(items), cpe)
    return items


def _parse_nvd_item(item: dict) -> dict | None:
    cve = item.get("cve") if isinstance(item, dict) else None
    if not isinstance(cve, dict):
        return None
    cve_id = cve.get("id")
    if not isinstance(cve_id, str) or not cve_id.startswith("CVE-"):
        return None
    if str(cve.get("vulnStatus", "")).lower() == "rejected":
        return None
    return {"id": cve_id, "cvss": _cvss(cve.get("metrics")), "_kev": bool(cve.get("cisaExploitAdd"))}


def _cvss(metrics) -> float | None:
    """CVSS 기본 점수. 3.1 → 3.0 → 4.0 → 2.0 순으로, 같은 판이면 NVD 자체 평가(Primary)를 먼저 쓴다."""
    if not isinstance(metrics, dict):
        return None
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV40", "cvssMetricV2"):
        entries = [e for e in metrics.get(key) or [] if isinstance(e, dict)]
        entries.sort(key=lambda e: e.get("type") != "Primary")
        for e in entries:
            score = (e.get("cvssData") or {}).get("baseScore")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                return float(score)
    return None


async def kev_catalog(http) -> frozenset[str] | None:
    """CISA KEV에 오른 CVE 번호 집합. 24시간 보관한다. 받지 못하면 지난 목록을, 그것도 없으면 None."""
    global _kev
    if _kev and _fresh(_kev[0]):
        return _kev[1]
    try:
        data = await _get_json(http, KEV_URL)
        vulns = data.get("vulnerabilities") if isinstance(data, dict) else None
        if isinstance(vulns, list):
            ids = frozenset(v["cveID"] for v in vulns if isinstance(v, dict) and isinstance(v.get("cveID"), str))
            if ids:
                _kev = (_clock(), ids)
                return ids
    except ScanStopped:
        raise
    except Exception:
        log.exception("KEV 목록 조회 실패")
    return _kev[1] if _kev else None


# ==================================================================== #25 지원 종료

async def end_of_life(http, product: str, version: str) -> bool | None:
    """그 버전의 지원이 끝났는지. 끝났으면 True, 지원 중이면 False, 알 수 없으면 None."""
    try:
        return await _end_of_life(http, product, version)
    except ScanStopped:
        raise
    except Exception:
        log.exception("지원 종료 조회 실패 %s %s", product, version)
        return None


async def _end_of_life(http, product: str, version: str) -> bool | None:
    product = (product or "").lower()
    slug = EOL_SLUGS.get(product)
    if not slug or not version:
        return None
    iis_release = None
    if product == "iis":
        iis_release = IIS_RELEASES.get(".".join(str(n) for n in _numbers(version)[:2]))
        if iis_release is None:
            return None  # IIS 10.0 등은 어느 윈도 서버인지 알 수 없어 묻지 않는다
    releases = await _eol_releases(http, slug)
    if releases is None:
        return None
    if iis_release is not None:
        release = next((r for r in releases if r["name"] == iis_release), None)
    else:
        release = _match_release(releases, version)
    return _release_eol(release) if release else None


async def _eol_releases(http, slug: str) -> list[dict] | None:
    saved = _eol_cache.get(slug)
    if saved and _fresh(saved[0]):
        return saved[1]
    data = await _get_json(http, EOL_URL.format(slug=slug), timeout=10.0, max_bytes=4 * 1024 * 1024)
    if isinstance(data, dict):  # v1: {"result": {"releases": [...]}}
        data = (data.get("result") or {}).get("releases")
    if not isinstance(data, list):  # 예전 API는 목록을 바로 준다
        return saved[1] if saved else None
    releases = []
    for r in data:
        if isinstance(r, dict):
            name = r.get("name", r.get("cycle"))
            if name is not None:
                releases.append({**r, "name": str(name)})
    _eol_cache[slug] = (_clock(), releases)
    return releases


def _numbers(version: str) -> list[int]:
    """'1.1.1k' → [1, 1, 1]. 각 마디의 앞쪽 숫자만 본다. 숫자가 없는 마디에서 멈춘다."""
    out = []
    for part in version.split("."):
        m = re.match(r"\d+", part)
        if not m:
            break
        out.append(int(m.group()))
    return out


def _match_release(releases: list[dict], version: str) -> dict | None:
    """버전 앞부분과 가장 길게 맞는 출시 주기. php 8.1.2 → 8.1, openssl 1.1.1k → 1.1.1, nginx 1.18.0 → 1.18."""
    nums = _numbers(version)
    best, best_len = None, 0
    for r in releases:
        parts = r["name"].split(".")
        if not all(p.isdigit() for p in parts):
            continue
        cycle = [int(p) for p in parts]
        if len(cycle) > best_len and nums[:len(cycle)] == cycle:
            best, best_len = r, len(cycle)
    return best


def _release_eol(r: dict) -> bool | None:
    """eolFrom(v1)·eol(예전 API)의 날짜가 오늘이거나 지났으면 True. 날짜가 없으면 참거짓 값을 쓴다."""
    for key in ("eolFrom", "eol"):
        value = r.get(key)
        if isinstance(value, str):
            try:
                return dt.date.fromisoformat(value[:10]) <= _today()
            except ValueError:
                pass
    for key in ("isEol", "eol"):
        value = r.get(key)
        if isinstance(value, bool):
            return value
    return None


# ==================================================================== #33 도메인 등록 정보

async def domain_registration(http, domain: str) -> dict | None:
    """등록 도메인의 만료일과 이전 잠금. {"expires": UTC datetime | None, "transfer_locked": bool | None}.

    예약 도메인(.test 등)은 묻지 않고 None이다. 조회하지 못해도 None이다.
    공공기관 도메인은 만료일이 9999년으로 온다. 판정은 부르는 쪽이 한다.
    """
    try:
        return await _domain_registration(http, domain)
    except ScanStopped:
        raise
    except Exception:
        log.exception("RDAP 조회 실패 %s", domain)
        return None


async def _domain_registration(http, domain: str) -> dict | None:
    name = (domain or "").strip().strip(".").lower()
    if "." not in name or name.rsplit(".", 1)[1] in RESERVED_TLDS:
        return None
    try:
        name = name.encode("idna").decode("ascii")  # 한글 도메인은 xn-- 꼴로 묻는다
    except UnicodeError:
        return None
    if name.rsplit(".", 1)[1] in RESERVED_TLDS:
        return None
    servers = await _rdap_servers(http)
    if not servers:
        return None
    labels = name.split(".")
    # 가장 긴 접미사부터 찾는다(co.kr은 부트스트랩에 없어 kr로 찾는다)
    base = next((servers[".".join(labels[i:])] for i in range(1, len(labels))
                 if ".".join(labels[i:]) in servers), None)
    if base is None:
        log.info("RDAP 서버를 모름 %s", name)
        return None
    data = await _get_json(http, f"{base.rstrip('/')}/domain/{name}",
                           {"Accept": "application/rdap+json"}, timeout=10.0, max_bytes=1024 * 1024,
                           redirects=RDAP_MAX_REDIRECTS)
    if not isinstance(data, dict):
        return None
    return {"expires": _rdap_expiry(data.get("events")), "transfer_locked": _rdap_locked(data.get("status"))}


async def _rdap_servers(http) -> dict[str, str] | None:
    """IANA 부트스트랩: 최상위 도메인 → RDAP 서버 주소. 24시간 보관한다."""
    global _rdap_bootstrap
    if _rdap_bootstrap and _fresh(_rdap_bootstrap[0]):
        return _rdap_bootstrap[1]
    data = await _get_json(http, RDAP_BOOTSTRAP_URL, timeout=10.0, max_bytes=4 * 1024 * 1024)
    servers: dict[str, str] = {}
    for entry in (data.get("services") if isinstance(data, dict) else None) or []:
        if not (isinstance(entry, list) and len(entry) >= 2):
            continue
        tlds, urls = entry[0], [u for u in entry[1] if isinstance(u, str)]
        if not urls:
            continue
        url = next((u for u in urls if u.startswith("https://")), urls[0])  # https를 먼저 쓴다
        for tld in tlds:
            if isinstance(tld, str):
                servers[tld.lower()] = url
    if not servers:
        return _rdap_bootstrap[1] if _rdap_bootstrap else None
    _rdap_bootstrap = (_clock(), servers)
    return servers


def _rdap_expiry(events) -> dt.datetime | None:
    for e in events if isinstance(events, list) else []:
        if isinstance(e, dict) and str(e.get("eventAction", "")).lower() == "expiration":
            return _parse_time(e.get("eventDate"))
    return None


def _parse_time(value) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        t = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return t.replace(tzinfo=dt.timezone.utc)
    try:
        return t.astimezone(dt.timezone.utc)
    except OverflowError:  # 9999-12-31T23:00-05:00처럼 UTC로 바꾸면 넘치는 값
        return dt.datetime.max.replace(tzinfo=dt.timezone.utc)


def _rdap_locked(status) -> bool | None:
    """client/server transfer prohibited 중 하나라도 있으면 잠김. status가 없으면 None."""
    if not isinstance(status, list):
        return None
    normalized = {re.sub(r"[\s_]", "", str(s)).lower() for s in status}
    return bool(normalized & _TRANSFER_LOCKS)
