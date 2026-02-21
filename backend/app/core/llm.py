"""Gemini (Vertex AI) client with function/tool calling for dashboard actions."""

from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.models.actions import (
    ClearFiltersAction,
    DashboardAction,
    ExportAction,
    FilterItem,
    NavigateAction,
    SetFiltersAction,
)

logger = logging.getLogger(__name__)

# ── Gemini function declarations (tool schema) ──────────────────────

SET_FILTERS_DECL = types.FunctionDeclaration(
    name="set_filters",
    description=(
        "Apply one or more filters to the Evidence.dev dashboard. "
        "Each filter has a field name (matching a Dropdown component name, "
        "e.g. 'category', 'year') and a value to filter by."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "filters": types.Schema(
                type=types.Type.ARRAY,
                description="List of filter objects to apply",
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "field": types.Schema(
                            type=types.Type.STRING,
                            description="The filter field name (e.g. 'category', 'year')",
                        ),
                        "value": types.Schema(
                            type=types.Type.STRING,
                            description="The value to filter by (e.g. 'Clothing', '2020')",
                        ),
                    },
                    required=["field", "value"],
                ),
            ),
        },
        required=["filters"],
    ),
)

CLEAR_FILTERS_DECL = types.FunctionDeclaration(
    name="clear_filters",
    description=(
        "Remove / clear specific filters from the dashboard. "
        "Pass the field names to clear. Use '%' as the wildcard to show all values."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "fields": types.Schema(
                type=types.Type.ARRAY,
                description="List of field names to clear (e.g. ['category', 'year'])",
                items=types.Schema(type=types.Type.STRING),
            ),
        },
        required=["fields"],
    ),
)

NAVIGATE_DECL = types.FunctionDeclaration(
    name="navigate",
    description="Navigate the dashboard to a different page.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "page": types.Schema(
                type=types.Type.STRING,
                description="The page path to navigate to (e.g. '/', '/settings')",
            ),
        },
        required=["page"],
    ),
)

EXPORT_DECL = types.FunctionDeclaration(
    name="export",
    description="Export the visible dashboard data as a file download.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "format": types.Schema(
                type=types.Type.STRING,
                description="Export format: 'csv' or 'xlsx'",
                enum=["csv", "xlsx"],
            ),
        },
        required=["format"],
    ),
)

DASHBOARD_TOOLS = types.Tool(
    function_declarations=[
        SET_FILTERS_DECL,
        CLEAR_FILTERS_DECL,
        NAVIGATE_DECL,
        EXPORT_DECL,
    ]
)

# ── System instruction ───────────────────────────────────────────────

SYSTEM_INSTRUCTION = """\
You are a dashboard assistant that controls an Evidence.dev business intelligence dashboard.
You MUST respond ONLY by calling the provided functions — never produce free-text answers.

Available dashboard controls:
- category filter: accepts product categories (e.g. "Clothing", "Electronics", "Food", etc.)
- year filter: accepts years as strings (e.g. "2019", "2020", "2021")

Rules:
1. Always call exactly one function per user request.
2. When the user asks to "clear" or "reset" or "show all", use clear_filters.
3. When the user mentions a category or year, use set_filters.
4. When the user wants to go to a page, use navigate.
5. When the user wants to download or export data, use export.
6. If the user says "clear all filters", clear both "category" and "year".
"""

# ── Client initialisation ────────────────────────────────────────────

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazily initialise the Vertex AI Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_region,
        )
        logger.info(
            "Initialised Gemini client  project=%s  region=%s  model=%s",
            settings.gcp_project_id,
            settings.gcp_region,
            settings.gemini_model,
        )
    return _client


# ── Public API ───────────────────────────────────────────────────────


def _parse_function_call(part: Any) -> DashboardAction | None:
    """Convert a Gemini function-call part into a typed DashboardAction."""
    fc = part.function_call
    if fc is None:
        return None

    name: str = fc.name
    args: dict = dict(fc.args) if fc.args else {}

    logger.info("Gemini function call: %s(%s)", name, json.dumps(args))

    if name == "set_filters":
        filters_raw = args.get("filters", [])
        filters = [FilterItem(field=f["field"], value=f["value"]) for f in filters_raw]
        return SetFiltersAction(filters=filters)

    if name == "clear_filters":
        fields = args.get("fields", [])
        return ClearFiltersAction(fields=list(fields))

    if name == "navigate":
        return NavigateAction(page=args.get("page", "/"))

    if name == "export":
        return ExportAction(format=args.get("format", "csv"))

    logger.warning("Unknown function call: %s", name)
    return None


async def process_prompt(prompt: str) -> list[DashboardAction]:
    """Send a user prompt to Gemini and extract structured DashboardActions.

    Returns a list of validated actions (usually just one).
    """
    client = _get_client()

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[DASHBOARD_TOOLS],
            temperature=0.0,
        ),
    )

    actions: list[DashboardAction] = []

    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.function_call:
                action = _parse_function_call(part)
                if action is not None:
                    actions.append(action)

    if not actions:
        logger.warning("Gemini returned no function calls for prompt: %s", prompt)

    return actions
