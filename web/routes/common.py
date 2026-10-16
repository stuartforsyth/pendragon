"""Helpers shared by the route modules."""

from fastapi import HTTPException, Request


def st(request: Request):
    """The AppState for this app instance."""
    return request.app.state.pd


def bad(message, code=400):
    raise HTTPException(status_code=code, detail=message)


def to_int(v, name="value"):
    try:
        return int(str(v).strip().lstrip("+"))
    except (TypeError, ValueError):
        bad(f"{name} must be a whole number")
