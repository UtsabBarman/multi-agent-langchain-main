"""Plan validation and normalization: fail fast, dedupe, enforce max steps, assign depends_on."""
from __future__ import annotations

import re

from src.core.config.models import DomainConfig
from src.core.contracts.orchestrator import Plan, Step
from src.core.exceptions import ConfigError

MAX_STEPS = 20
_STEP_ID_RE = re.compile(r"^S(\d+)$")


def _step_id(step: Step) -> str:
    return f"S{step.step_index}"


def validate_and_normalize_plan(plan: Plan, domain_config: DomainConfig) -> Plan:
    """Validate plan (agent names, max steps) and normalize (dedupe by step_index, assign depends_on)."""
    if not plan.steps:
        return plan
    steps = list(plan.steps)
    # Dedupe by step_index (keep first)
    seen: set[int] = set()
    unique: list[Step] = []
    for s in steps:
        if s.step_index in seen:
            continue
        seen.add(s.step_index)
        unique.append(s)
    # Sort by step_index
    unique.sort(key=lambda s: s.step_index)
    if len(unique) > MAX_STEPS:
        raise ConfigError(f"Plan has {len(unique)} steps; maximum is {MAX_STEPS}.")
    valid_names = {a.name for a in domain_config.agents}
    for s in unique:
        if s.agent_name not in valid_names:
            raise ConfigError(f"Plan references unknown agent '{s.agent_name}'. Available: {sorted(valid_names)}.")
        if s.step_index < 1:
            raise ConfigError(f"Invalid step_index={s.step_index}. step_index must be >= 1.")
        if not (s.task_description or "").strip():
            raise ConfigError(f"Step S{s.step_index} has empty task_description.")
    # Assign default depends_on: S(i-1) for step_index > 1 when depends_on empty
    normalized: list[Step] = []
    for i, s in enumerate(unique):
        dep = [d.strip() for d in (s.depends_on or []) if isinstance(d, str) and d.strip()]
        if not dep and s.step_index > 1:
            prev = unique[i - 1]
            dep = [_step_id(prev)]
        normalized.append(Step(
            step_index=s.step_index,
            agent_name=s.agent_name,
            task_description=s.task_description,
            depends_on=dep,
            parallel_group=s.parallel_group,
        ))
    # Validate dependency ids and references.
    by_id = {_step_id(s): s for s in normalized}
    for s in normalized:
        for dep_id in s.depends_on:
            m = _STEP_ID_RE.match(dep_id)
            if not m:
                raise ConfigError(f"Step {_step_id(s)} has invalid depends_on entry '{dep_id}'. Expected format like 'S1'.")
            if dep_id not in by_id:
                raise ConfigError(f"Step {_step_id(s)} depends on missing step '{dep_id}'.")
            if dep_id == _step_id(s):
                raise ConfigError(f"Step {_step_id(s)} cannot depend on itself.")

    # Ensures cycle detection runs during validation (raises ConfigError on invalid graph).
    topological_order(normalized)
    return Plan(steps=normalized)


def topological_order(steps: list[Step]) -> list[Step]:
    """Return steps in dependency order (depends_on). Raises ConfigError on cycles."""
    if not steps:
        return []
    by_id = {_step_id(s): s for s in steps}
    order: list[Step] = []
    state: dict[str, str] = {}  # sid -> "visiting" | "done"

    def add(s: Step) -> None:
        sid = _step_id(s)
        st = state.get(sid)
        if st == "done":
            return
        if st == "visiting":
            raise ConfigError(f"Cyclic dependency detected at '{sid}'.")
        state[sid] = "visiting"
        for dep in s.depends_on:
            dep_step = by_id.get(dep)
            if dep_step is None:
                raise ConfigError(f"Step '{sid}' depends on missing step '{dep}'.")
            add(dep_step)
        order.append(s)
        state[sid] = "done"

    for s in steps:
        add(s)
    return order
