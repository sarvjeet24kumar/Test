"""
Exception Handlers

Unified error response format for all exceptions.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.exceptions.base import MiniMartException


async def minimart_exception_handler(request: Request, exc: MiniMartException):
    """Handler for all MiniMart-specific exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.detail.get("message", str(exc.detail)) if isinstance(exc.detail, dict) else str(exc.detail),
                "details": exc.detail.get("details", {}) if isinstance(exc.detail, dict) else {},
            },
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handler for Pydantic validation errors."""
    formatted_errors = {}
    for error in exc.errors():
        field = error["loc"][-1] if error["loc"] else "general"
        formatted_errors.setdefault(str(field), []).append(error["msg"])

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid input",
                "details": formatted_errors,
            },
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handler for generic HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            },
        },
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers to the FastAPI app."""
    app.add_exception_handler(MiniMartException, minimart_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
