"""
Exception Handlers
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.exceptions.base import MiniMartException


async def minimart_exception_handler(request: Request, exc: MiniMartException):
    """Handler for all MiniMart-specific exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers to the FastAPI app."""
    app.add_exception_handler(MiniMartException, minimart_exception_handler)
