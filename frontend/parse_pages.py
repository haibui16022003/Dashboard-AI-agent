"""
parse_pages.py — Evidence.dev page parser

Parses each page in /pages/*.md and extracts:
  - Filters       (Dropdown / DateInput)
  - BigValue KPIs
  - Charts        (BarChart, LineChart, AreaChart, ScatterPlot, PieChart)
  - DataTables
  - SQL queries   (```sql <name> ... ``` blocks)

Output is written to static/page_json_descriptions/<page_name>.json
and also returned by /page-summary/{page} on the FastAPI backend.

Run from the frontend/ directory:
    python parse_pages.py
"""

import re
import json
import textwrap
from pathlib import Path

EVIDENCE_PAGES_DIR = Path("pages")
STATIC_DIR = Path("static/page_json_descriptions")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_quote(s: str) -> str:
    """Strip surrounding single / double quotes."""
    return s.strip("'\"") if s else ""


def _parse_attrs(raw: str) -> dict:
    """Parse a tag attribute string into a dict, handling both
    key=value and key={value} Evidence.dev patterns."""
    result = {}
    # Match: key="val", key='val', key={...}, key=plain
    for m in re.finditer(r'(\w+)=(?:\{([^}]*)\}|"([^"]*)"|\'([^\']*)\'|(\S+))', raw):
        key = m.group(1)
        val = next((v for v in m.groups()[1:] if v is not None), "")
        result[key] = val
    return result


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL single-line (--) comments for cleanliness."""
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    ).strip()


# ── SQL query extraction ─────────────────────────────────────────────────────

def _extract_sql_queries(md: str) -> list[dict]:
    """
    Extract every ```sql <name> ... ``` block from an Evidence.dev markdown page.

    Returns a list of dicts:
        {
            "name":        str,   # query variable name (e.g. "orders_by_category")
            "sql":         str,   # cleaned SQL text
            "columns":     list,  # column aliases detected in SELECT clause
            "references":  list,  # table/source references (source.table or plain table)
        }
    """
    queries = []

    # Match opening fence ``` sql <name> (optional whitespace around 'sql')
    pattern = re.compile(
        r"```\s*sql\s+(\w+)\s*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )

    for m in pattern.finditer(md):
        name = m.group(1)
        raw_sql = m.group(2)
        sql = _strip_sql_comments(textwrap.dedent(raw_sql))

        # ── Detect SELECT columns ──────────────────────────────────────────
        # Grab everything between SELECT and FROM, extract aliases or bare names
        columns: list[str] = []
        select_match = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql, re.DOTALL | re.IGNORECASE)
        if select_match:
            select_clause = select_match.group(1)
            # Split on commas (ignoring commas inside parentheses)
            depth = 0
            buf = []
            parts = []
            for ch in select_clause:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if ch == "," and depth == 0:
                    parts.append("".join(buf).strip())
                    buf = []
                else:
                    buf.append(ch)
            if buf:
                parts.append("".join(buf).strip())

            for part in parts:
                part = part.strip()
                # AS alias
                alias_m = re.search(r"\bAS\s+(\w+)\s*$", part, re.IGNORECASE)
                if alias_m:
                    columns.append(alias_m.group(1))
                    continue
                # date_trunc / function result referenced by last word
                func_m = re.search(r"\b(\w+)\s*$", part)
                if func_m:
                    columns.append(func_m.group(1))

        # ── Detect source references (source.table or plain table in FROM/JOIN) ─
        refs: list[str] = []
        for ref_m in re.finditer(
            r"\b(?:FROM|JOIN)\s+([\w.]+)", sql, re.IGNORECASE
        ):
            ref = ref_m.group(1).strip()
            if ref not in refs:
                refs.append(ref)

        # ── Detect Evidence template variables used as filters ─────────────
        # e.g. ${inputs.category.value}
        template_vars = re.findall(r"\$\{inputs\.(\w+)\.\w+\}", sql)

        queries.append({
            "name": name,
            "sql": sql,
            "columns": columns,
            "references": refs,
            "filter_inputs": list(dict.fromkeys(template_vars)),  # deduplicated
        })

    return queries


# ── Component extractors ─────────────────────────────────────────────────────

def _extract_filters(md: str) -> list[dict]:
    filters: list[dict] = []

    for raw in re.findall(r"<Dropdown\b([^>]*)>", md):
        attrs = _parse_attrs(raw)
        filters.append({
            "type": "Dropdown",
            "label": _clean_quote(attrs.get("title", attrs.get("name", ""))),
            "input_name": attrs.get("name"),
            "data_query": attrs.get("data"),
            "value_col": attrs.get("value"),
            "multiple": attrs.get("multiple") == "true",
        })

    for raw in re.findall(r"<DateInput\b([^>]*)>", md):
        attrs = _parse_attrs(raw)
        filters.append({
            "type": "DateInput",
            "label": _clean_quote(attrs.get("title", attrs.get("name", ""))),
            "input_name": attrs.get("name"),
            "range": "range" in raw.lower(),
        })

    return filters


def _extract_big_values(md: str) -> list[dict]:
    big_values: list[dict] = []
    for raw in re.findall(r"<BigValue\b([^>]*)/>", md):
        attrs = _parse_attrs(raw)
        big_values.append({
            "type": "BigValue",
            "title": _clean_quote(attrs.get("title", "")),
            "value": attrs.get("value"),
            "format": _clean_quote(attrs.get("fmt", "")),
        })
    return big_values


def _extract_charts(md: str) -> list[dict]:
    charts: list[dict] = []
    chart_types = "BarChart|LineChart|AreaChart|ScatterPlot|PieChart|FunnelChart"
    for chart_type, raw in re.findall(rf"<({chart_types})\b([^>]*)>", md):
        attrs = _parse_attrs(raw)
        entry: dict = {
            "type": chart_type,
            "title": _clean_quote(attrs.get("title", "Unnamed chart")),
            "data_query": attrs.get("data"),
            "x": attrs.get("x"),
            "y": attrs.get("y"),
        }
        for opt in ("series", "y2", "yFmt", "xFmt", "colorPalette"):
            if opt in attrs:
                entry[opt] = attrs[opt]
        charts.append(entry)
    return charts


def _extract_tables(md: str) -> list[dict]:
    tables: list[dict] = []
    # Self-closing or opening DataTable tags
    for raw in re.findall(r"<DataTable\b([^>]*)/?>\s*(?:(.*?)</DataTable>)?", md, re.DOTALL):
        tag_attrs, inner = raw
        attrs = _parse_attrs(tag_attrs)
        columns = re.findall(r"<Column\s+id=(\w+)", inner or "")
        tables.append({
            "type": "DataTable",
            "data_query": attrs.get("data"),
            "columns": columns or [],
            "search": "search=true" in tag_attrs,
            "rows": attrs.get("rows"),
        })
    return tables


# ── Main parser ──────────────────────────────────────────────────────────────

def load_dashboard_interface(page_name: str) -> dict | None:
    md_file = EVIDENCE_PAGES_DIR / f"{page_name}.md"
    if not md_file.exists():
        print(f"Warning: {md_file} not found")
        return None

    md = md_file.read_text(encoding="utf-8")

    # Page title (first # heading)
    title_match = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    page_title = title_match.group(1).strip() if title_match else page_name

    # Short description — text between the title line and the first ## / code block
    desc_match = re.search(
        r"^#\s+.+\n\n(.+?)(?:\n##|\n```|$)", md, re.MULTILINE | re.DOTALL
    )
    page_description = desc_match.group(1).strip() if desc_match else ""

    return {
        "page": page_name,
        "title": page_title,
        "description": page_description,
        "filters": _extract_filters(md),
        "big_values": _extract_big_values(md),
        "charts": _extract_charts(md),
        "tables": _extract_tables(md),
        "queries": _extract_sql_queries(md),
    }


# ── CLI entry-point ──────────────────────────────────────────────────────────

def main():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    md_files = [f for f in EVIDENCE_PAGES_DIR.glob("*.md") if not f.name.startswith("+")]
    if not md_files:
        print("No page files found in", EVIDENCE_PAGES_DIR)
        return

    print(f"Found {len(md_files)} page(s) to parse…")

    for md_file in md_files:
        page_name = md_file.stem
        print(f"  Parsing  {page_name}…")
        page_data = load_dashboard_interface(page_name)
        if page_data:
            out = STATIC_DIR / f"{page_name}.json"
            out.write_text(json.dumps(page_data, indent=2), encoding="utf-8")
            print(f"    ✓ {out}  ({len(page_data['queries'])} queries, "
                  f"{len(page_data['filters'])} filters, "
                  f"{len(page_data['charts'])} charts)")

    print("\nDone!")


if __name__ == "__main__":
    main()