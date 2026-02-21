"""Agent service — validates actions and generates human-readable confirmations."""

from __future__ import annotations

import logging

from app.core.constants import (
    ALLOWED_EXPORT_FORMATS,
    ALLOWED_FILTER_FIELDS,
    ALLOWED_PAGES,
)
from app.models.actions import (
    ClearFiltersAction,
    DashboardAction,
    ExportAction,
    NavigateAction,
    SetFiltersAction,
)

logger = logging.getLogger(__name__)


class ActionValidationError(Exception):
    """Raised when an action fails allow-list validation."""


def validate_actions(
    actions: list[DashboardAction],
) -> list[DashboardAction]:
    """Validate every action against the allow-list constants.

    Returns the list unchanged if valid, raises ``ActionValidationError`` otherwise.
    """
    for action in actions:
        if isinstance(action, SetFiltersAction):
            for f in action.filters:
                if f.field not in ALLOWED_FILTER_FIELDS:
                    raise ActionValidationError(
                        f"Filter field '{f.field}' is not allowed. "
                        f"Allowed fields: {sorted(ALLOWED_FILTER_FIELDS)}"
                    )

        elif isinstance(action, ClearFiltersAction):
            for field in action.fields:
                if field not in ALLOWED_FILTER_FIELDS:
                    raise ActionValidationError(
                        f"Cannot clear unknown field '{field}'. "
                        f"Allowed fields: {sorted(ALLOWED_FILTER_FIELDS)}"
                    )

        elif isinstance(action, NavigateAction):
            if action.page not in ALLOWED_PAGES:
                raise ActionValidationError(
                    f"Page '{action.page}' is not allowed. "
                    f"Allowed pages: {sorted(ALLOWED_PAGES)}"
                )

        elif isinstance(action, ExportAction):
            if action.format not in ALLOWED_EXPORT_FORMATS:
                raise ActionValidationError(
                    f"Export format '{action.format}' is not allowed. "
                    f"Allowed formats: {sorted(ALLOWED_EXPORT_FORMATS)}"
                )

    return actions


def generate_confirmation(actions: list[DashboardAction]) -> str:
    """Create a short, human-readable confirmation string for a list of actions."""
    if not actions:
        return "🤔 I couldn't determine the right action for your request. Could you rephrase?"

    parts: list[str] = []
    for action in actions:
        if isinstance(action, SetFiltersAction):
            filter_strs = [f"**{f.field}** → *{f.value}*" for f in action.filters]
            parts.append(f"🔽 Filtered {', '.join(filter_strs)}")

        elif isinstance(action, ClearFiltersAction):
            parts.append(f"🧹 Cleared filters: {', '.join(action.fields)}")

        elif isinstance(action, NavigateAction):
            parts.append(f"📄 Navigated to **{action.page}**")

        elif isinstance(action, ExportAction):
            parts.append(f"📥 Exporting data as **{action.format.upper()}**")

    return " | ".join(parts)
