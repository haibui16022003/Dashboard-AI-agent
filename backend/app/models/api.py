"""API envelope Pydantic models (request / response shapes for FastAPI endpoints)."""

from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel, Field

from app.models.actions import (
    ClearFiltersAction,
    ExportAction,
    NavigateAction,
    SetFiltersAction,
)
from app.models.data import DataResult


class AgentRequest(BaseModel):
    """Incoming chat request from the frontend."""

    prompt: str = Field(..., min_length=1, max_length=2000)
    page: str = Field(default="index", description="Current Evidence.dev page name")


class AgentResponse(BaseModel):
    """Response returned to the frontend chat UI."""

    result: str
    actions: list[
        Union[SetFiltersAction, ClearFiltersAction, NavigateAction, ExportAction]
    ] = Field(default_factory=list)
    data_result: Optional[DataResult] = None
