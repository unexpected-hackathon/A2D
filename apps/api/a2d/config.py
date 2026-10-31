"""환경 변수 설정. 값은 apps/api/.env에 두고 커밋하지 않는다(.env.example 참고)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """의존성을 늘리지 않으려고 KEY=VALUE 형식만 읽는다. 이미 있는 환경 변수는 덮지 않는다."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


def _bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # 시연용 단일 계정(API 명세 3장)
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "IT 담당자"
    db_path: str = str(API_ROOT / "data" / "a2d.sqlite3")
    # A2D 화면 주소. POST·PATCH의 Origin이 이 목록에 없으면 403 FORBIDDEN_ORIGIN
    web_origins: list[str] = field(default_factory=list)
    secure_cookie: bool = False
    # 1이면 /api/v1/openapi.json·/api/v1/docs를 연다. A2D 자신이 #17에 걸리므로 시연 환경 밖에서는 끈다
    expose_openapi: bool = False

    # 소유권 확인(FR-01). dns = TXT 레코드 조회, trust = 조회 없이 통과(화면 개발용, 시연 금지)
    verify_mode: str = "dns"
    dns_servers: list[str] = field(default_factory=list)  # 비우면 시스템 DNS. 예: 10.253.53.53, 127.0.0.1:15353

    # 점검 엔진. fixture = 시연 시나리오를 돌려주는 가짜 엔진, 또는 "패키지.모듈:클래스"
    engine: str = "fixture"
    fixture_step_sec: float = 0.4
    # 점검 HTTP의 TLS 검증. 비우면 검증을 끈다(시연 대상은 자체 서명 인증서를 쓸 수 있고, 인증서
    # 유효성은 #28이 따로 본다 — target/README "결함 상태의 TLS"). CA 묶음 경로를 넣으면 그 CA로 검증한다.
    ca_bundle: str = ""
    request_limit: int = 300
    tool_call_limit: int = 20
    time_limit_sec: int = 300

    # LLM(강현 님 GPU 서버의 vLLM, OpenAI 호환). 비어 있으면 llm=down, 기본 가이드로 동작한다
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen3-8b"  # model/의 SERVED_MODEL_NAME과 같게 둔다

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(API_ROOT / ".env")
        return cls(
            admin_email=os.environ.get("A2D_ADMIN_EMAIL", "").strip().lower(),
            admin_password=os.environ.get("A2D_ADMIN_PASSWORD", ""),
            admin_name=os.environ.get("A2D_ADMIN_NAME", "IT 담당자"),
            db_path=os.environ.get("A2D_DB_PATH", str(API_ROOT / "data" / "a2d.sqlite3")),
            web_origins=_list("A2D_WEB_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"),
            secure_cookie=_bool("A2D_SECURE_COOKIE"),
            expose_openapi=_bool("A2D_EXPOSE_OPENAPI"),
            verify_mode=os.environ.get("A2D_VERIFY_MODE", "dns").strip().lower(),
            dns_servers=_list("A2D_DNS_SERVER"),
            engine=os.environ.get("A2D_ENGINE", "fixture").strip(),
            fixture_step_sec=_float("A2D_FIXTURE_STEP_SEC", 0.4),
            ca_bundle=os.environ.get("A2D_CA_BUNDLE", "").strip(),
            request_limit=_int("A2D_REQUEST_LIMIT", 300),
            tool_call_limit=_int("A2D_TOOL_CALL_LIMIT", 20),
            time_limit_sec=_int("A2D_TIME_LIMIT_SEC", 300),
            llm_base_url=os.environ.get("A2D_LLM_BASE_URL", "").rstrip("/"),
            llm_api_key=os.environ.get("A2D_LLM_API_KEY", ""),
            llm_model=os.environ.get("A2D_LLM_MODEL", "qwen3-8b"),
        )
