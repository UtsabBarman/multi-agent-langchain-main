"""Decide whether the user query needs a multi-step plan or can be answered with a simple reply (e.g. greetings)."""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

CLASSIFY_SYSTEM = """You are a classifier for a multi-agent assistant.

Given the user message, decide:
- If it is a GREETING, small talk, thanks, or a very simple message that does NOT need research or multi-step assistance: reply with a single short, friendly response (1-2 sentences only). Do not use markdown. Just the reply text.
- If the user is asking a real question, needs information, or needs research/analysis: reply with exactly the two words: NEEDS_PLAN (nothing else, no punctuation).

Examples:
User: "hi" -> "Hello! How can I help you today?"
User: "hello" -> "Hi there! What would you like to know?"
User: "thanks" -> "You're welcome! Let me know if you need anything else."
User: "What are the safety guidelines for product X?" -> NEEDS_PLAN
User: "Summarize the report" -> NEEDS_PLAN
"""


def classify_query(query: str) -> tuple[bool, str]:
    """
    Returns (needs_plan: bool, simple_reply: str).
    If needs_plan is True, simple_reply is empty (caller should run the planner).
    If needs_plan is False, simple_reply is the short response to show (no plan).
    """
    query = (query or "").strip()
    if not query:
        return False, "Hello! How can I help you today?"
    prompt = ChatPromptTemplate.from_messages([
        ("system", CLASSIFY_SYSTEM),
        ("human", "{query}"),
    ])
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    out = (prompt | llm).invoke({"query": query})
    text = (out.content if hasattr(out, "content") else str(out)).strip()
    if text.upper() == "NEEDS_PLAN":
        return True, ""
    return False, text or "Hello! How can I help you today?"
