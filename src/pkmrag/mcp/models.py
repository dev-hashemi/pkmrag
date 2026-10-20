"""Pydantic models for the MCP server's public payloads."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class JobState(BaseModel):
    """State of the active background job exposed through the health endpoint."""

    type: str
    stage: Optional[str] = None
    unit: str = "items"
    phase: str
    cur: int = 0
    total: int = 100
    percent: int = 0
    message: str = ""
    started_at: float = 0.0
