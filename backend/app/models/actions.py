"""Dashboard action Pydantic models.

Includes the primitive FilterItem, each action variant, and the
DashboardAction discriminated union used throughout the app.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class FilterItem(BaseModel):
    """A single field=value filter pair."""

    field: str
    value: str


class SetFiltersAction(BaseModel):
    """Apply one or more dashboard filters."""

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
    """Export visible dashboard data as a file download."""

    action: Literal["export"] = "export"
    format: Literal["csv", "xlsx"]


# Discriminated union — used as the canonical type for validated actions
DashboardAction = Annotated[
    Union[SetFiltersAction, ClearFiltersAction, NavigateAction, ExportAction],
    Field(discriminator="action"),
]
