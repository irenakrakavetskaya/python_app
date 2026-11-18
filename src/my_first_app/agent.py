import asyncio
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def main():
    options = ClaudeAgentOptions(
        model="claude-sonnet-5-5",
        fallback_model="claude-haiku-5-5",
        allowed_tools=[
            "Read",
            "Edit",
            "Glob",
            "WebSearch",
            "Bash(uv run pytest:*)",  # only these commands, no free shell access
            "Bash(uv run ruff:*)",
        ],
        permission_mode="acceptEdits",  # Auto-approve file edits
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": "You are a senior Python developer. Always follow PEP 8.",
        },
        max_turns=8,
        cwd=str(PROJECT_ROOT),
    )

    # Agentic loop: streams messages as Claude works
    async for message in query(
        prompt="Review main.py for bugs that would cause crashes. Fix any issues you find.",
        options=options,
    ):
        # Print human-readable output
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print(block.text)  # Claude's reasoning
                elif hasattr(block, "name"):
                    print(f"Tool: {block.name}")  # Tool being called
        elif isinstance(message, ResultMessage) and not message.is_error:
            print(f"Done: {message.subtype}")  # Final result


asyncio.run(main())
