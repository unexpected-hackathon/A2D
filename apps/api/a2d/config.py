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

    # 점검 DNS. 소유권 확인·자산 찾기·점검 HTTP·TLS 접속이 모두 이 DNS로 주소를 찾는다.
    # 비우면 시스템 DNS. 예: 10.253.53.53, 127.0.0.1:15353
    dns_servers: list[str] = field(default_factory=list)

    # 점검 엔진. "패키지.모듈:클래스"
    engine: str = "a2d.engine.live:LiveEngine"
    # #28이 인증서 발급 체인을 검증할 CA 묶음 경로. 넣으면 이 CA가 발급하지 않은 인증서를 #28 "invalid"로 본다.
    # 비우면 자체 서명·이름·만료만 본다. 점검 HTTP(내용 조회)는 이 값과 상관없이 검증하지 않는다
    # (자체 서명 대상도 내용을 읽어야 한다 — target/README "결함 상태의 TLS").
    ca_bundle: str = ""
    request_limit: int = 0  # 점검 1회의 요청 상한. 0이면 없다(호스트당 초당 2건은 그대로 지킨다)
    tool_call_limit: int = 20
    time_limit_sec: int = 1800

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
            dns_servers=_list("A2D_DNS_SERVER"),
            engine=os.environ.get("A2D_ENGINE", "a2d.engine.live:LiveEngine").strip(),
            ca_bundle=os.environ.get("A2D_CA_BUNDLE", "").strip(),
            request_limit=_int("A2D_REQUEST_LIMIT", 0),
            tool_call_limit=_int("A2D_TOOL_CALL_LIMIT", 20),
            time_limit_sec=_int("A2D_TIME_LIMIT_SEC", 1800),
            llm_base_url=os.environ.get("A2D_LLM_BASE_URL", "").rstrip("/"),
            llm_api_key=os.environ.get("A2D_LLM_API_KEY", ""),
            llm_model=os.environ.get("A2D_LLM_MODEL", "qwen3-8b"),
        )
