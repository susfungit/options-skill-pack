"""Standalone caching verification.

Calls Anthropic API twice with the same cache-marked system prompt + tools
(loaded from our app config). Prints usage from both calls so you can see
cache_creation_input_tokens / cache_read_input_tokens directly.

Run: python3 scripts/verify_caching.py
Requires ANTHROPIC_API_KEY env var.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic

from app.tools import cached_tools, TOOLS
from app.prompts import build_system_prompt
from app.storage import read_profile
from app.config import DEFAULT_MODEL


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        print("ERROR: set ANTHROPIC_API_KEY")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    profile = read_profile()
    model = profile.get("model", DEFAULT_MODEL)
    system_prompt = build_system_prompt(profile)

    cached_system = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]
    cached_tool_list = cached_tools()

    print(f"SDK version: {anthropic.__version__}")
    print(f"Model: {model}")
    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"Tools count: {len(cached_tool_list)}")
    print(f"Last tool has cache_control: {'cache_control' in cached_tool_list[-1]}")
    print(f"System block has cache_control: {'cache_control' in cached_system[0]}")
    print()

    user_msg = "Say only 'ok' and nothing else."

    # Test with the user's configured model AND a known-current Sonnet
    test_models = [model]
    if model != "claude-sonnet-4-6":
        test_models.append("claude-sonnet-4-6")

    for test_model in test_models:
        print(f"=== Testing model: {test_model} ===")
        for i in (1, 2):
            print(f"--- Call {i} ---")
            try:
                resp = client.messages.create(
                    model=test_model,
                    max_tokens=20,
                    system=cached_system,
                    tools=cached_tool_list,
                    messages=[{"role": "user", "content": user_msg}],
                )
                u = resp.usage
                print(
                    f"resolved_model={resp.model} "
                    f"input={u.input_tokens} "
                    f"cache_create={getattr(u, 'cache_creation_input_tokens', None)} "
                    f"cache_read={getattr(u, 'cache_read_input_tokens', None)} "
                    f"output={u.output_tokens}"
                )
            except anthropic.BadRequestError as e:
                print(f"BadRequestError: {e.message}")
            except anthropic.NotFoundError as e:
                print(f"NotFoundError: {e.message}")
            print()


if __name__ == "__main__":
    main()
