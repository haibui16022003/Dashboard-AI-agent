"""Data query result Pydantic models.

Returned by the metrics service after executing an agent-generated SQL query.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DataResult(BaseModel):
    """Result from a backend data query (execute_query tool)."""

    sql: str                      # SQL that was executed
    columns: list[str]            # Column names in the result set
    rows: list[dict[str, Any]]    # Result rows as dicts
    summary: str                  # Plain-English summary for the chat UI
