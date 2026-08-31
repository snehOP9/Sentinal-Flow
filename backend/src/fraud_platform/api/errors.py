from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class Problem(HTTPException):
    """RFC-7807-inspired error with a stable application code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        title: str,
        detail: str,
        *,
        retryable: bool = False,
        fields: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.title = title
        self.retryable = retryable
        self.fields = fields or []
