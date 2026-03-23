from __future__ import annotations

import json

from core.crawlers.claude_text import (
    pick_dominant_cwd,
    text_from_claude_assistant_line,
    text_from_claude_user_line,
)


def test_pick_dominant_cwd() -> None:
    lines = [
        json.loads(s)
        for s in [
            '{"type":"user","cwd":"/a"}',
            '{"type":"user","cwd":"/b"}',
            '{"type":"user","cwd":"/a"}',
        ]
    ]
    assert pick_dominant_cwd(lines) == "/a"


def test_user_line_nested_message() -> None:
    raw = {
        "type": "user",
        "message": {"role": "user", "content": "hello nested"},
    }
    assert text_from_claude_user_line(raw) == "hello nested"


def test_assistant_line_content_blocks() -> None:
    raw = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Hi"},
                {"type": "tool_use", "name": "Bash", "input": {}},
            ],
        },
    }
    assert "Hi" in text_from_claude_assistant_line(raw)
    assert "[Bash]" in text_from_claude_assistant_line(raw)
