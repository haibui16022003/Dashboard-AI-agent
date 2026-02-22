"""Gemini (Vertex AI) client with function/tool calling for dashboard actions and data queries."""

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
from app.models.data import DataResult
from app.services.metrics_service import run_query

logger = logging.getLogger(__name__)

# ── Gemini function declarations ─────────────────────────────────────

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

EXECUTE_QUERY_DECL = types.FunctionDeclaration(
    name="execute_query",
    description=(
        "Execute a read-only SELECT SQL query against the dashboard's data backend "
        "(Evidence parquet files via DuckDB). Use this for any DATA_QUESTION or the "
        "data-retrieval step of a HYBRID intent. "
        "You MUST write a valid DuckDB SQL SELECT statement. "
        "Reference tables exactly as they appear in the page SQL queries context. "
        "You may use functions like date_part(), date_trunc(), sum(), avg(), count(), etc. "
        "Only SELECT is allowed — no INSERT, UPDATE, DELETE, DROP, or DDL."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "sql": types.Schema(
                type=types.Type.STRING,
                description=(
                    "A valid DuckDB SELECT statement. "
                    "Reference tables by their name as seen in the page SQL queries "
                    "(e.g. 'orders' or 'needful_things__orders'). "
                    "Example: SELECT category, SUM(sales) as total FROM orders GROUP BY category ORDER BY total DESC LIMIT 5"
                ),
            ),
        },
        required=["sql"],
    ),
)

DASHBOARD_TOOLS = types.Tool(
    function_declarations=[
        SET_FILTERS_DECL,
        CLEAR_FILTERS_DECL,
        NAVIGATE_DECL,
        EXPORT_DECL,
        EXECUTE_QUERY_DECL,
    ]
)

# ── System instruction ───────────────────────────────────────────────

_BASE_SYSTEM_INSTRUCTION = """\
You are a BI assistant embedded inside an Evidence.dev analytics dashboard.
You are NOT a chatbot. You are a controlled, deterministic analytics agent.

════════════════════════════════════════
INTENT DETECTION — READ THIS CAREFULLY
════════════════════════════════════════

Every request falls into exactly ONE category:

──────────────────────────────────────
A. DASHBOARD_ACTION ONLY
   Trigger: User wants to filter, navigate, clear, or export — NO data answer needed.
   Examples:
     "Filter for Clothing"           → call set_filters(category="Clothing")
     "Show only 2020 data"           → call set_filters(year="2020")
     "Clear all filters"             → call clear_filters(fields=["category","year"])
     "Export as CSV"                 → call export(format="csv")
   Response: call ONLY the dashboard action tool(s). Do NOT call execute_query.

──────────────────────────────────────
B. DATA_QUESTION ONLY
   Trigger: User asks "what is", "how much", "which", "show me the total/average/max/min",
            "top N", "rank", "compare" — WITHOUT specifying a filter that changes the view.
   Examples:
     "What is the total revenue?"         → call execute_query(sql="SELECT SUM(sales)...")
     "Which category has highest sales?"  → call execute_query(sql="SELECT category, SUM(sales)...")
     "Show top 5 months by revenue"       → call execute_query(sql="SELECT ... LIMIT 5")
   Response: call ONLY execute_query. Do NOT call any dashboard action tool.

──────────────────────────────────────
C. HYBRID (filter + answer)
   Trigger: User asks a DATA question AND specifies a filter dimension (year, category, etc.).
   Examples:
     "What is the total revenue in 2020?"
     "What is the highest revenue month in 2020?"
     "Which category sold the most in 2019?"
     "Show me total sales for Clothing"

   ⚠️ CRITICAL RULE FOR HYBRID:
   You MUST call BOTH tools in THE SAME SINGLE RESPONSE — simultaneously, not one at a time.
   In your response, emit TWO function calls:
     1. set_filters(...)       ← filters come FIRST in the response
     2. execute_query(sql=...) ← query comes SECOND in the same response

   Do NOT wait for confirmation. Do NOT split into two turns.
   Emit BOTH function calls in one response right now.

   For "What is the total revenue in 2020?":
     call 1 → set_filters(filters=[{"field":"year","value":"2020"}])
     call 2 → execute_query(sql="SELECT SUM(sales) as total_revenue FROM orders WHERE date_part('year', order_datetime)=2020")

   For "What is the highest revenue month in 2020?":
     call 1 → set_filters(filters=[{"field":"year","value":"2020"}])
     call 2 → execute_query(sql="SELECT date_trunc('month', order_datetime) as month, SUM(sales) as revenue FROM orders WHERE date_part('year', order_datetime)=2020 GROUP BY month ORDER BY revenue DESC LIMIT 1")

════════════════════════════════════════
SQL RULES (for execute_query)
════════════════════════════════════════

• Only SELECT — no INSERT, UPDATE, DELETE, DROP, CREATE, ALTER.
• Use DuckDB functions: date_part(), date_trunc(), SUM(), AVG(), MAX(), MIN(), COUNT().
• Reference tables by their name as shown in the page queries context (e.g. "orders").
• Keep queries aggregated — no raw row dumps.
• For year filters in SQL: use date_part('year', order_datetime) = {year} (integer, not string).

════════════════════════════════════════
PAGE CONTEXT (use as query guidance)
════════════════════════════════════════
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


# ── Function call parsers ────────────────────────────────────────────

def _parse_dashboard_action(part: Any) -> DashboardAction | None:
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

    return None


def _parse_execute_query(part: Any) -> DataResult | None:
    """Execute a query tool call and return the DataResult."""
    fc = part.function_call
    if fc is None or fc.name != "execute_query":
        return None

    args: dict = dict(fc.args) if fc.args else {}
    sql: str = args.get("sql", "").strip()

    if not sql:
        logger.warning("execute_query called with empty SQL")
        return None

    logger.info("Executing agent-generated SQL: %s", sql[:200])
    try:
        result = run_query(sql)
        return DataResult(
            sql=result["sql"],
            columns=result["columns"],
            rows=result["rows"],
            summary=result["summary"],
        )
    except (ValueError, RuntimeError) as e:
        logger.error("Query execution failed: %s", e)
        return DataResult(
            sql=sql,
            columns=[],
            rows=[],
            summary=f"⚠️ Query failed: {e}",
        )


# ── Public API ───────────────────────────────────────────────────────

async def process_prompt(
    prompt: str,
    page_context_text: str = "",
) -> tuple[list[DashboardAction], DataResult | None]:
    """
    Send a user prompt (with optional page context) to Gemini and extract:
      - A list of DashboardActions (set_filters, clear_filters, navigate, export)
      - An optional DataResult from execute_query

    Returns:
        (actions, data_result)
    """
    client = _get_client()

    system_instruction = _BASE_SYSTEM_INSTRUCTION
    if page_context_text:
        system_instruction += "\n" + page_context_text

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[DASHBOARD_TOOLS],
            temperature=0.0,
        ),
    )

    actions: list[DashboardAction] = []
    data_result: DataResult | None = None

    for candidate in response.candidates:
        for part in candidate.content.parts:
            if not part.function_call:
                continue

            fc_name = part.function_call.name

            if fc_name == "execute_query":
                dr = _parse_execute_query(part)
                if dr is not None:
                    data_result = dr
            else:
                action = _parse_dashboard_action(part)
                if action is not None:
                    actions.append(action)

    if not actions and data_result is None:
        logger.warning("Gemini returned no function calls for prompt: %s", prompt)

    return actions, data_result
