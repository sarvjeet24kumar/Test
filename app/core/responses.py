"""
Unified Response Helpers

All success responses wrapped in {"success": true, "data": {...}}.
"""

from typing import Any
from fastapi.responses import JSONResponse


def success_response(data: Any = None) -> dict:
    """
    Wrap any data in the standard success envelope.
    Returns a dict to let FastAPI's response_model handle validation.

    Args:
        data: Response data (dict, list, or any serializable value)

    Returns:
        Dict with {"success": true, "data": ...}
    """
    return {
        "success": True,
        "data": data if data is not None else {},
    }
