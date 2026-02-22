"""FastAPI application — AI Action Agent backend (V2).

Endpoints
---------
POST /agent/action   Accept a chat prompt + page context, return structured actions and/or data.
GET  /page-summary/{page}   Return the parsed page description JSON.
GET  /ws             WebSocket for broadcasting actions to the Evidence.dev frontend.
GET  /health         Health-check.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.llm import process_prompt
from app.models.api import AgentRequest, AgentResponse
from app.services.agent_service import (
    ActionValidationError,
    generate_confirmation,
    validate_actions,
)
from app.services.page_context_service import format_context_for_llm, get_page_context
from app.services.websocket_manager import ConnectionManager

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
)
logger = logging.getLogger(__name__)

# ── App & middleware ─────────────────────────────────────────────────

app = FastAPI(
    title="AI Action Agent",
    description="Converts natural-language prompts into structured Evidence.dev dashboard actions and backend data queries.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ws_manager = ConnectionManager()

# ── Routes ───────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health-check endpoint."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "websocket_connections": ws_manager.connection_count,
    }


@app.get("/page-summary/{page_name}")
async def page_summary(page_name: str):
    """Return the parsed page description JSON for a given Evidence page."""
    context = get_page_context(page_name)
    if context is None:
        return {"error": f"No page description found for '{page_name}'"}
    return context


@app.post("/agent/action", response_model=AgentResponse)
async def agent_action(request: AgentRequest):
    """Accept a natural-language prompt and return structured dashboard actions and/or data.

    Flow:
    1. Load page context (filters, SQL queries, charts) from the JSON description.
    2. Send the prompt + page context to Gemini with function-calling tools.
    3. Validate returned dashboard actions against the allow-list.
    4. Execute any data query (execute_query) via the metrics service.
    5. Broadcast validated actions to connected frontends via WebSocket.
    6. Return confirmation message + actions + data_result to the chat UI.
    """
    logger.info("Received prompt: %s  (page: %s)", request.prompt, request.page)

    # 1. Load page context
    page_ctx = get_page_context(request.page)
    page_context_text = format_context_for_llm(page_ctx) if page_ctx else ""

    try:
        # 2. LLM → structured actions + optional data result
        actions, data_result = await process_prompt(request.prompt, page_context_text)

        if not actions and data_result is None:
            return AgentResponse(
                result="🤔 I couldn't determine the right action. Could you rephrase?",
                actions=[],
            )

        # 3. Validate dashboard actions
        if actions:
            validate_actions(actions)

        # 4. Broadcast dashboard actions via WebSocket
        for action in actions:
            await ws_manager.broadcast(
                {
                    "type": "DASHBOARD_ACTION",
                    "payload": action.model_dump(),
                }
            )
            logger.info("Broadcast action: %s", action.model_dump())

        # 5. Build confirmation message
        confirmation = _build_response_message(actions, data_result)

        return AgentResponse(
            result=confirmation,
            actions=actions,
            data_result=data_result,
        )

    except ActionValidationError as e:
        logger.warning("Action validation failed: %s", e)
        return AgentResponse(
            result=f"⚠️ Action blocked: {e}",
            actions=[],
        )
    except Exception as e:
        logger.exception("Unexpected error processing prompt")
        return AgentResponse(
            result=f"⚠️ Internal error: {e}",
            actions=[],
        )


def _build_response_message(actions, data_result) -> str:
    """Compose the final chat message from actions and/or data results."""
    parts: list[str] = []

    if actions:
        from app.services.agent_service import generate_confirmation
        parts.append(generate_confirmation(actions))

    if data_result:
        parts.append(f"📊 {data_result.summary}")

    return "\n".join(parts) if parts else "✅ Done."


# ── WebSocket ────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for the Evidence.dev frontend to receive dashboard actions."""
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
