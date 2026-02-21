"""Pydantic models for DashboardAction types and API request/response."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# ── Filter primitives ────────────────────────────────────────────────

class FilterItem(BaseModel):
    """A single field=value filter pair."""
    field: str
    value: str


# ── Action variants ──────────────────────────────────────────────────

class SetFiltersAction(BaseModel):
    """Apply one or more filters to the dashboard."""
    action: Literal["set_filters"] = "set_filters"
    filters: list[FilterItem] = Field(..., min_length=1)


class ClearFiltersAction(BaseModel):
    """Remove specific filters from the dashboard."""
    action: Literal["clear_filters"] = "clear_filters"
    fields: list[str] = Field(..., min_length=1)


class NavigateAction(BaseModel):
    """Navigate the dashboard to a different page."""
    action: Literal["navigate"] = "navigate"
    page: str


class ExportAction(BaseModel):
    """Export visible dashboard data."""
    action: Literal["export"] = "export"
    format: Literal["csv", "xlsx"]


# ── Discriminated union ──────────────────────────────────────────────

DashboardAction = Annotated[
    Union[SetFiltersAction, ClearFiltersAction, NavigateAction, ExportAction],
    Field(discriminator="action"),
]


# ── API models ───────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    """Incoming request from the chat UI."""
    prompt: str = Field(..., min_length=1, max_length=1000)


class AgentResponse(BaseModel):
    """Response sent back to the chat UI."""
    result: str
    actions: list[
        Union[SetFiltersAction, ClearFiltersAction, NavigateAction, ExportAction]
    ] = Field(default_factory=list)
