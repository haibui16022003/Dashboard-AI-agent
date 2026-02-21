"""FastAPI application — AI Action Agent backend.

Endpoints
---------
POST /agent/action   Accept a chat prompt, return structured dashboard actions.
GET  /ws             WebSocket for broadcasting actions to the Evidence.dev frontend.
GET  /health         Health-check.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.llm import process_prompt
from app.models.actions import AgentRequest, AgentResponse
from app.services.agent_service import (
    ActionValidationError,
    generate_confirmation,
    validate_actions,
)
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
    description="Converts natural-language prompts into structured Evidence.dev dashboard actions.",
    version="1.0.0",
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
        "websocket_connections": ws_manager.connection_count,
    }


@app.post("/agent/action", response_model=AgentResponse)
async def agent_action(request: AgentRequest):
    """Accept a natural-language prompt and return structured dashboard actions.

    1. Send the prompt to Gemini with function-calling tools.
    2. Validate the returned actions against the allow-list.
    3. Broadcast validated actions to connected frontends via WebSocket.
    4. Return a confirmation message + the action list to the chat UI.
    """
    logger.info("Received prompt: %s", request.prompt)

    try:
        # 1. LLM → structured actions
        actions = await process_prompt(request.prompt)

        if not actions:
            return AgentResponse(
                result="🤔 I couldn't determine the right action. Could you rephrase?",
                actions=[],
            )

        # 2. Validate
        validate_actions(actions)

        # 3. Broadcast to frontend(s) via WebSocket
        for action in actions:
            await ws_manager.broadcast(
                {
                    "type": "DASHBOARD_ACTION",
                    "payload": action.model_dump(),
                }
            )
            logger.info("Broadcast action: %s", action.model_dump())

        # 4. Confirmation
        confirmation = generate_confirmation(actions)
        return AgentResponse(result=confirmation, actions=actions)

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


# ── WebSocket ────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for the Evidence.dev frontend to receive dashboard actions."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; we don't expect client messages,
            # but we need to await to detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
