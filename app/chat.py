"""Claude API client and chat endpoint."""

import logging
import os
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import anthropic

from app.config import DEFAULT_MODEL, limiter
from app.storage import read_profile
from app.tools import TOOLS, SKILL_GUIDANCE, execute_tool
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger("options_skill_pack")
router = APIRouter()

# ── Claude API client ────────────────────────────────────────────────────────

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="CLAUDE_API_KEY or ANTHROPIC_API_KEY environment variable not set",
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


@router.get("/api/models")
async def list_models():
    try:
        client = get_client()
        models = client.models.list()
        cutoff = datetime.now(tz=models.data[0].created_at.tzinfo) if models.data else datetime.now()
        cutoff = cutoff.replace(year=cutoff.year - 1)
        result = [
            {"id": m.id, "display_name": m.display_name}
            for m in models.data
            if m.created_at >= cutoff
        ]
        result.sort(key=lambda m: m["id"])
        return {"models": result}
    except HTTPException:
        return {"models": [{"id": DEFAULT_MODEL, "display_name": "Claude Sonnet 4"}]}


# ── Chat models & endpoint ───────────────────────────────────────────────────

class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: MessageRole
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []


class ChatResponse(BaseModel):
    response: str


@router.post("/api/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(request: Request, req: ChatRequest):
    try:
        client = get_client()
    except HTTPException as e:
        return ChatResponse(response=f"**Configuration error:** {e.detail}")

    messages = [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.message})

    model = read_profile().get("model", DEFAULT_MODEL)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        max_tool_rounds = 5
        tool_round = 0
        while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
            tool_round += 1
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            tool_results = []

            for tool_use in tool_uses:
                result_json = execute_tool(tool_use.name, tool_use.input)
                guidance = SKILL_GUIDANCE.get(tool_use.name, "")
                if guidance:
                    tool_result_content = (
                        f"Tool output:\n{result_json}\n\n"
                        f"---\n{guidance}"
                    )
                else:
                    tool_result_content = result_json

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": tool_result_content,
                })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

        if tool_round >= max_tool_rounds and response.stop_reason == "tool_use":
            return ChatResponse(
                response="**Stopped:** Too many tool calls. Please simplify your request."
            )

        text_parts = [block.text for block in response.content if hasattr(block, "text")]
        return ChatResponse(response="\n".join(text_parts))

    except anthropic.BadRequestError as e:
        logger.error("Anthropic API error: %s", e.message)
        return ChatResponse(response="**API error:** The request could not be processed. Check server logs.")
    except anthropic.AuthenticationError:
        return ChatResponse(response="**Authentication failed.** Check your ANTHROPIC_API_KEY.")
    except Exception:
        return ChatResponse(response="**Error:** An unexpected error occurred. Check server logs.")
