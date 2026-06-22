"""
Reference evaluator: consume `asn_mortgage_rules.json` and check an application JSON
against it, emitting findings in the validator's contract
(rule_id, rule_name, status, evidence, remediation).

This is a deterministic helper an agent (or the rule_validator) can call for the
`auto_evaluable` rules; rules marked auto_evaluable=false are returned as `unknown`
for the agent/human to reason about with the rule text.

Usage (from project root):
    python examples/sample_data/check_application.py
    python examples/sample_data/check_application.py path/to/application.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RULES_PATH = HERE / "asn_mortgage_rules.json"

_MISSING = object()


def get_field(obj: Any, dotted: str) -> Any:
    """Resolve a dotted path against nested dicts. Returns _MISSING if absent."""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _as_list(value: Any) -> list[Any]:
    if value is _MISSING or value is None:
        return []
    return value if isinstance(value, list) else [value]


def apply_operator(left: Any, operator: str, right: Any) -> bool:
    if operator in ("exists",):
        return left is not _MISSING and left is not None
    if operator in ("not_exists",):
        return left is _MISSING or left is None
    if operator == "is_true":
        return left is True
    if operator == "is_false":
        return left is False

    # For value comparisons, a missing value cannot satisfy the check.
    if left is _MISSING:
        return False

    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator in ("<", "<=", ">", ">="):
        try:
            l, r = float(left), float(right)
        except (TypeError, ValueError):
            return False
        return {"<": l < r, "<=": l <= r, ">": l > r, ">=": l >= r}[operator]
    if operator == "in":
        return left in (right or [])
    if operator == "not_in":
        return left not in (right or [])
    if operator == "contains":
        return right in _as_list(left)
    if operator == "not_contains":
        return right not in _as_list(left)
    if operator == "contains_any":
        return any(v in _as_list(left) for v in (right or []))
    if operator == "contains_all":
        return all(v in _as_list(left) for v in (right or []))
    if operator == "not_contains_any":
        return not any(v in _as_list(left) for v in (right or []))
    raise ValueError(f"Unsupported operator: {operator}")


def _resolve_right(app: dict, check: dict) -> Any:
    if "value_field" in check:
        rv = get_field(app, check["value_field"])
        return None if rv is _MISSING else rv
    return check.get("value")


def eval_leaf(app: dict, cond: dict, item: dict | None = None) -> bool:
    """Evaluate a single {field, operator, value} condition.

    If `item` is given (for_each context) and scope is not 'root', the field is
    looked up inside the item first.
    """
    field = cond["field"]
    operator = cond["operator"]
    right = _resolve_right(app, cond)
    scope = cond.get("scope")
    if item is not None and scope != "root":
        left = item.get(field, _MISSING)
    else:
        left = get_field(app, field)
    return apply_operator(left, operator, right)


def eval_condition(app: dict, cond: dict, item: dict | None = None) -> bool:
    if "all_of" in cond:
        return all(eval_condition(app, c, item) for c in cond["all_of"])
    if "any_of" in cond:
        return any(eval_condition(app, c, item) for c in cond["any_of"])
    return eval_leaf(app, cond, item)


def eval_check(app: dict, check: dict) -> tuple[str, str]:
    """Return (status, evidence) for a rule's check block."""
    # Conditional gating: skip / only-when
    if "skip_when" in check and eval_condition(app, check["skip_when"]):
        return "pass", "Skipped (skip_when condition met)."
    if "only_when" in check and not eval_condition(app, check["only_when"]):
        return "pass", "Not applicable (only_when condition not met)."

    # manual review marker
    if check.get("type") == "manual_review":
        return "unknown", "Requires manual/agent review: " + check.get("expression", "")

    # for_each over an array of sub-items
    if "for_each" in check:
        items = get_field(app, check["for_each"])
        if items is _MISSING:
            return "unknown", f"Field '{check['for_each']}' missing."
        when = check.get("when")
        require = check["require"]
        failures = []
        applicable = 0
        for it in (items or []):
            if when is not None and not eval_condition(app, when, it):
                continue
            applicable += 1
            if not eval_condition(app, require, it):
                failures.append(it.get("name") or it)
        if applicable == 0:
            return "pass", "No matching sub-items; rule not triggered."
        if failures:
            return "fail", f"Failed for: {failures}"
        return "pass", f"Satisfied for all {applicable} matching sub-item(s)."

    # aggregate (e.g. max over an array)
    if check.get("aggregate") == "max":
        values = get_field(app, check["field"])
        if values is _MISSING:
            return "unknown", f"Field '{check['field']}' missing."
        try:
            agg = max(values)
        except (TypeError, ValueError):
            return "unknown", f"Cannot aggregate '{check['field']}'."
        ok = apply_operator(agg, check["operator"], _resolve_right(app, check))
        return ("pass" if ok else "fail"), f"max({check['field']})={agg}"

    # composite all_of / any_of at the top level
    if "all_of" in check or "any_of" in check:
        ok = eval_condition(app, check)
        ev = check.get("expression", "")
        return ("pass" if ok else "fail"), ev

    # simple leaf
    left = get_field(app, check["field"])
    if left is _MISSING:
        return "unknown", f"Field '{check['field']}' missing."
    ok = apply_operator(left, check["operator"], _resolve_right(app, check))
    return ("pass" if ok else "fail"), f"{check['field']}={left!r}"


def severity_to_fail_status(severity: str) -> str:
    """Map a failed evaluation to fail vs warning based on severity."""
    if severity == "warning":
        return "warning"
    return "fail"


def evaluate(app: dict, rules_doc: dict) -> list[dict]:
    findings = []
    nhg = bool(app.get("nhg_requested", False))
    for rule in rules_doc["rules"]:
        scope = rule.get("nhg_scope", "both")
        if scope == "with_nhg_only" and not nhg:
            continue
        if scope == "without_nhg_only" and nhg:
            continue

        if not rule.get("auto_evaluable", False):
            findings.append({
                "rule_id": rule["rule_id"],
                "rule_name": rule["rule_name"],
                "status": "unknown",
                "evidence": "Not auto-evaluable; agent/human judgment required.",
                "remediation": rule.get("remediation", ""),
            })
            continue

        status, evidence = eval_check(app, rule["check"])
        if status == "fail":
            status = severity_to_fail_status(rule["severity"])
            # Stage-gated rules (e.g. BSN required at signing) are only a warning
            # before that stage is reached.
            check_stage = rule["check"].get("stage")
            app_stage = app.get("stage", "application")
            if check_stage and app_stage != check_stage:
                status = "warning"
        findings.append({
            "rule_id": rule["rule_id"],
            "rule_name": rule["rule_name"],
            "status": status,
            "evidence": evidence,
            "remediation": rule.get("remediation", "") if status in ("fail", "warning") else "",
        })
    return findings


# Sample application matching examples/sample_data/asn_mortgage_submission_pack.pdf
SAMPLE_APPLICATION = {
    "nhg_requested": True,
    "stage": "application",
    "applicant": {
        "residence_country": "Netherlands",
        "nationality": "Dutch",
        "residence_permit_type": None,
        "lives_or_works_in_nl": True,
        "id_document_valid": True,
        "bsn_provided": False,
        "all_owners_jointly_liable": True,
        "legally_competent": True,
        "co_purchase_with_family": False,
        "durable_relationship": True,
        "fraud_screening_clear": True,
    },
    "occupancy": "primary residence",
    "property": {
        "owner_occupied": True, "type": "eengezinswoning", "market_value": 455000,
        "country": "Netherlands", "permanent_residential_zoning": True,
        "on_industrial_estate": False, "clean_soil": True, "fixed_with_foundation": True,
        "marketability_months": 6, "living_area_m2": 118, "unacceptable_easements": False,
        "self_contained": True, "owner_changed_last_12m": False, "is_new_build": False,
        "mandatory_land_buyback": False, "vve_active": None,
    },
    "ownership": {"shares_pct": [50, 50]},
    "loan": {
        "amount": 465000,
        "purpose": "primary residence purchase",
        "term_years": 30,
        "repayment_type": "annuity",
        "ltv_pct": 102.2,
        "sustainability_financed": True,
        "sustainability_amount": 18000,
        "interest_only_pct_of_value": 0,
        "is_residual_debt": False,
        "behind_external_mortgage": False,
        "refinances_business_loan": False,
        "consumer_purpose": False,
        "bridging": False,
        "maatwerk": False,
    },
    "income": {
        "toetsinkomen_annual": 110400,
        "fixed_stable_pct": 72,
        "applicants": [
            {"name": "Daan", "type": "fixed", "intention_statement": False,
             "perspectiefverklaring": False, "bonus_pct_of_fixed": 8,
             "source_country": "Netherlands", "months_at_employer": 81},
            {"name": "Sophie", "type": "temporary", "intention_statement": True,
             "perspectiefverklaring": False, "bonus_pct_of_fixed": 0,
             "source_country": "Netherlands", "months_at_employer": 27},
        ],
    },
    "self_employed": {"years_active": None, "full_book_years": None, "business_country": None},
    "affordability": {
        "financing_burden_annual": 24600, "allowed_burden_annual": 31000, "dti_pct": 30,
        "own_funds_in_crypto_or_fx": False,
    },
    "liabilities": {
        "bkr": {"special_codes": [], "registration_types": ["RK"], "contract_count": 2},
        "internal_arrears": False,
    },
    "credit_score": 690,
    "documents": [
        "werkgeversverklaring", "loonstrook", "intentieverklaring", "bank_statements",
        "koopovereenkomst", "taxatierapport", "energy_label", "bkr_overview",
    ],
    "missing_fields": ["documents.uwv_verzekeringsbericht", "documents.jaaropgave"],
}


def main() -> None:
    rules_doc = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    if len(sys.argv) > 1:
        app = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        app = SAMPLE_APPLICATION
        print("No application file given; using built-in SAMPLE_APPLICATION.\n")

    findings = evaluate(app, rules_doc)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["status"]] = counts.get(f["status"], 0) + 1

    print(f"Ruleset: {rules_doc['ruleset_name']} ({len(rules_doc['rules'])} rules)\n")
    width = max(len(f["rule_id"]) for f in findings)
    for f in findings:
        line = f"  [{f['status'].upper():7}] {f['rule_id']:<{width}}  {f['rule_name']}"
        print(line)
        if f["status"] in ("fail", "warning"):
            print(f"            evidence: {f['evidence']}")
            if f["remediation"]:
                print(f"            fix:      {f['remediation']}")
    print("\nSummary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
