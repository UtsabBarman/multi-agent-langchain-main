"""Unit tests for Agent Protocol v1 schemas and helpers."""
from src.core.contracts.protocol import artifacts_from_content_and_steps, tool_calls_from_steps


def test_artifacts_from_content_and_steps_empty():
    a = artifacts_from_content_and_steps("Hello", [])
    assert a.notes == "Hello"
    assert a.rendered_html == "Hello"
    assert a.facts == []
    assert a.tables == []


def test_artifacts_from_tool_steps():
    steps = [
        {"type": "tool_start", "name": "query_facts", "input": "{}"},
        {"type": "tool_end", "name": "query_facts", "output": {"rows": [{"a": 1}]}},
    ]
    a = artifacts_from_content_and_steps("Done", steps)
    assert len(a.tables) == 1
    assert a.tables[0].name == "query_result"
    assert a.tables[0].rows == [{"a": 1}]


def test_tool_calls_from_steps():
    steps = [
        {"type": "tool_start", "name": "search_docs", "input": '{"query": "x"}'},
        {"type": "tool_end", "name": "search_docs", "output": "..."},
    ]
    tc = tool_calls_from_steps(steps)
    assert len(tc) == 1
    assert tc[0].tool == "search_docs"
