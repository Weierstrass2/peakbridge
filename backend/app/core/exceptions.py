"""애플리케이션 커스텀 예외 — 일관된 JSON 에러 포맷."""

from fastapi import status


class AppException(Exception):
    """모든 비즈니스 예외의 기본 클래스."""

    def __init__(
        self,
        error: str,
        detail: str,
        code: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.error = error
        self.detail = detail
        self.code = code
        self.status_code = status_code
        super().__init__(detail)


class NotFoundError(AppException):
    """리소스를 찾을 수 없을 때."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            error="Not Found",
            detail=f"{resource} '{identifier}' not found",
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class UnauthorizedError(AppException):
    """인증 실패."""

    def __init__(self, detail: str = "Invalid or expired token") -> None:
        super().__init__(
            error="Unauthorized",
            detail=detail,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(AppException):
    """권한 부족."""

    def __init__(self, detail: str = "Insufficient permissions") -> None:
        super().__init__(
            error="Forbidden",
            detail=detail,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ConflictError(AppException):
    """중복 또는 멱등성 충돌."""

    def __init__(self, detail: str, code: str = "CONFLICT") -> None:
        super().__init__(
            error="Conflict",
            detail=detail,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
        )


class ValidationAppError(AppException):
    """비즈니스 규칙 검증 실패."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            error="Validation Error",
            detail=detail,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
