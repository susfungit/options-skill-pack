"""Claude API client and chat endpoint (sync + SSE streaming)."""

import asyncio
import json
import logging
import os
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
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


_async_client = None


def get_async_client() -> anthropic.AsyncAnthropic:
    global _async_client
    if _async_client is None:
        api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="CLAUDE_API_KEY or ANTHROPIC_API_KEY environment variable not set",
            )
        _async_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _async_client


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
        return {"models": [{"id": DEFAULT_MODEL, "display_name": "Claude Sonnet 4.6"}]}


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
            max_tokens=16384,
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
                max_tokens=16384,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

        if tool_round >= max_tool_rounds and response.stop_reason == "tool_use":
            return ChatResponse(
                response="**Stopped:** Too many tool calls. Please simplify your request."
            )

        text_parts = [block.text for block in response.content if hasattr(block, "text")]
        text = "\n".join(text_parts)
        if response.stop_reason == "max_tokens":
            text += "\n\n*[Response truncated — hit token limit]*"
        return ChatResponse(response=text)

    except anthropic.BadRequestError as e:
        logger.error("Anthropic API error: %s", e.message)
        return ChatResponse(response="**API error:** The request could not be processed. Check server logs.")
    except anthropic.AuthenticationError:
        return ChatResponse(response="**Authentication failed.** Check your ANTHROPIC_API_KEY.")
    except Exception:
        return ChatResponse(response="**Error:** An unexpected error occurred. Check server logs.")


# ── Streaming chat endpoint ─────────────────────────────────────────────────

async def _stream_chat(messages: list, model: str):
    """Async generator that yields SSE events for streaming chat."""
    aclient = get_async_client()
    tool_round = 0
    max_tool_rounds = 5

    def _sse(event: str, data: dict) -> ServerSentEvent:
        return ServerSentEvent(data=json.dumps(data), event=event)

    try:
        while True:
            async with aclient.messages.stream(
                model=model,
                max_tokens=16384,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                        yield _sse("token", {"text": event.delta.text})

                response = await stream.get_final_message()

            if response.stop_reason != "tool_use" or tool_round >= max_tool_rounds:
                break

            tool_round += 1
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            tool_results = []

            for tool_use in tool_uses:
                yield _sse("tool_start", {"tool": tool_use.name})
                result_json = await asyncio.to_thread(execute_tool, tool_use.name, tool_use.input)
                guidance = SKILL_GUIDANCE.get(tool_use.name, "")
                content = (
                    f"Tool output:\n{result_json}\n\n---\n{guidance}" if guidance else result_json
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": content,
                })
                yield _sse("tool_end", {"tool": tool_use.name})

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        stop = "max_rounds" if (tool_round >= max_tool_rounds and response.stop_reason == "tool_use") else response.stop_reason
        yield _sse("done", {"stop_reason": stop})

    except anthropic.BadRequestError as e:
        logger.error("Anthropic API error: %s", e.message)
        yield _sse("error", {"message": "API error: The request could not be processed."})
    except anthropic.AuthenticationError:
        yield _sse("error", {"message": "Authentication failed. Check your ANTHROPIC_API_KEY."})
    except Exception as e:
        logger.error("Streaming chat error: %s", e)
        yield _sse("error", {"message": "An unexpected error occurred."})


@router.post("/api/chat/stream")
@limiter.limit("10/minute")
async def chat_stream(request: Request, req: ChatRequest):
    try:
        get_async_client()
    except HTTPException as e:
        async def _error():
            yield ServerSentEvent(data=json.dumps({"message": f"Configuration error: {e.detail}"}), event="error")
        return EventSourceResponse(_error())

    messages = [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.message})
    model = read_profile().get("model", DEFAULT_MODEL)

    return EventSourceResponse(_stream_chat(messages, model))
