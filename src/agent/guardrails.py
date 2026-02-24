"""Simple guardrails: truncate and filter output based on config rules."""


def apply_guardrails(text: str, guardrails: list[str]) -> str:
    """Apply guardrail rules to agent output. Currently enforces max length if specified."""
    if not text:
        return text
    for rule in guardrails or []:
        rule_lower = rule.lower()
        if "max" in rule_lower and "word" in rule_lower:
            try:
                parts = rule.split()
                for i, p in enumerate(parts):
                    if p.isdigit() and i > 0 and "word" in parts[i - 1].lower():
                        max_words = int(p)
                        words = text.split()
                        if len(words) > max_words:
                            text = " ".join(words[:max_words]) + "..."
                        break
            except (ValueError, IndexError):
                pass
    return text
