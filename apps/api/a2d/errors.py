"""API 명세 1장 '오류 응답' 형식."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


def validation(message: str) -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message)


def not_found(what: str = "대상") -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what}을(를) 찾을 수 없습니다.")


def unauthenticated() -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", "다시 로그인해 주세요.")
