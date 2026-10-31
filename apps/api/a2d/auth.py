"""시연용 단일 계정 로그인과 서버 세션(API 명세 3장).

세션은 메모리에 둔다. 서버를 다시 띄우면 다시 로그인한다.
"""

from __future__ import annotations

import datetime as dt
import secrets
import threading
import time
from dataclasses import dataclass

import bcrypt

from .config import Settings
from .errors import ApiError
from .timeutil import iso, now

COOKIE = "a2d_session"
IDLE_SEC = 2 * 3600  # 마지막 요청 후 2시간
ABSOLUTE_SEC = 8 * 3600  # 로그인 후 최대 8시간
MAX_FAILS = 5
LOCK_SEC = 5 * 60
USER_ID = "U-1"


@dataclass
class Session:
    sid: str
    created: float
    last: float

    def expires_at(self) -> float:
        return min(self.last + IDLE_SEC, self.created + ABSOLUTE_SEC)


class Auth:
    def __init__(self, settings: Settings):
        self.s = settings
        if not settings.admin_email or not settings.admin_password:
            raise RuntimeError("A2D_ADMIN_EMAIL, A2D_ADMIN_PASSWORD를 .env에 넣어 주세요.")
        self._hash = bcrypt.hashpw(settings.admin_password.encode(), bcrypt.gensalt())
        self._sessions: dict[str, Session] = {}
        self._fails: dict[str, tuple[int, float]] = {}  # ip → (연속 실패 수, 잠금 해제 시각)
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 사용자

    def user(self) -> dict:
        return {"user_id": USER_ID, "email": self.s.admin_email, "name": self.s.admin_name}

    def session_body(self, sess: Session) -> dict:
        exp = dt.datetime.fromtimestamp(sess.expires_at(), tz=now().tzinfo)
        return {"user": self.user(), "expires_at": iso(exp)}

    # ------------------------------------------------------------ 로그인

    def login(self, ip: str, email: str, password: str, old_sid: str | None) -> Session:
        t = time.time()
        with self._lock:
            fails, until = self._fails.get(ip, (0, 0.0))
            if until > t:
                raise ApiError(429, "TOO_MANY_ATTEMPTS", "로그인을 5회 연속 실패했습니다. 5분 뒤 다시 시도해 주세요.")
        ok_email = secrets.compare_digest(email.strip().lower().encode(), self.s.admin_email.encode())
        ok_pw = bcrypt.checkpw(password.encode(), self._hash)  # 이메일이 틀려도 같은 시간을 쓴다
        with self._lock:
            if not (ok_email and ok_pw):
                fails = 0 if until and until <= t else fails  # 잠금이 풀린 뒤에는 다시 센다
                fails += 1
                self._fails[ip] = (fails, t + LOCK_SEC if fails >= MAX_FAILS else 0.0)
                raise ApiError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 맞지 않습니다.")
            self._fails.pop(ip, None)
            if old_sid:
                self._sessions.pop(old_sid, None)
            sess = Session(sid=secrets.token_urlsafe(32), created=t, last=t)  # 256비트 난수
            self._sessions[sess.sid] = sess
            return sess

    def logout(self, sid: str | None) -> None:
        if sid:
            with self._lock:
                self._sessions.pop(sid, None)

    def touch(self, sid: str | None) -> Session | None:
        """유효한 세션이면 마지막 요청 시각을 갱신해 돌려준다."""
        if not sid:
            return None
        t = time.time()
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is None:
                return None
            if sess.expires_at() <= t:
                self._sessions.pop(sid, None)
                return None
            sess.last = t
            return sess
