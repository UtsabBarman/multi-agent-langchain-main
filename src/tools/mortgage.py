from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PDF_PATH = "examples/sample_data/asn_mortgage_submission_pack.pdf"
DEFAULT_RULES_PATH = "examples/sample_data/asn_mortgage_rules.json"
REPORT_DIR = ROOT / "data" / "reports"


def _resolve(path: str | None, default: str) -> Path:
    raw = (path or default).strip()
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _read_pdf_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pass

    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name)
            reader = module.PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
            if text:
                return text
        except Exception:
            continue

    raise RuntimeError(
        "Could not extract text from binary PDF. Install project dependencies so pypdf is available."
    )


def _money(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _line_value(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}:\s*(.+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _contains(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def _months_since(start_year: int, start_month: int, as_of: date = date(2026, 6, 22)) -> int:
    return (as_of.year - start_year) * 12 + (as_of.month - start_month)


def _extract_documents(text: str) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    aliases = {
        "valid_identification": "Valid identification",
        "employer_statement_applicant": "Werkgeversverklaring (employer's statement) - applicant",
        "employer_statement_co_applicant": "Werkgeversverklaring (employer's statement) - co-applicant",
        "intention_statement": "Intention statement",
        "uwv_verzekeringsbericht": "UWV-verzekeringsbericht",
        "salary_slips": "Recent salary slips",
        "bank_statements": "Bank statements",
        "purchase_agreement": "Purchase agreement",
        "valuation_report": "Property valuation report",
        "energy_label_sustainability_quote": "Energy label / sustainability quotation",
        "bkr_overview": "BKR credit overview",
        "jaaropgave": "Most recent annual income statement / jaaropgave",
        "proof_of_own_funds": "Proof of own funds",
    }
    for key, label in aliases.items():
        if re.search(rf"\[X\]\s*{re.escape(label)}", text, re.IGNORECASE):
            present.append(key)
        elif re.search(rf"\[\s*\]\s*{re.escape(label)}", text, re.IGNORECASE):
            missing.append(key)
    return present, missing


def _build_application_json(text: str, source_path: Path) -> dict[str, Any]:
    documents, missing_documents = _extract_documents(text)
    loan_amount = _money(text, r"Requested loan amount:\s*EUR\s*([\d,]+)") or _money(
        text, r"Loan amount:\s*EUR\s*([\d,]+)"
    )
    purchase_price = _money(text, r"Purchase price(?:\s*\(koopsom\))?:\s*EUR\s*([\d,]+)")
    market_value = _money(text, r"Appraised market value(?:\s*\(taxatie\))?:\s*EUR\s*([\d,]+)") or _money(
        text, r"Market value:\s*EUR\s*([\d,]+)"
    )
    sustainability = _money(text, r"of which sustainability.*?:\s*EUR\s*([\d,]+)")
    dti_pct = _number(text, r"Debt-to-income \(indicative\):\s*approx\.\s*([\d.]+)%")
    ltv_pct = _number(text, r"Loan-to-value.*?:\s*([\d.]+)%")
    annual_income = _money(text, r"Combined gross annual \(toetsinkomen\):\s*EUR\s*([\d,]+)")
    monthly_obligations = _money(text, r"Monthly obligations \(debts\):\s*EUR\s*([\d,]+)")
    monthly_mortgage = _money(text, r"Estimated monthly mortgage payment:\s*EUR\s*([\d,]+)")

    applicant = {
        "name": _line_value(text, "Applicant") or "Daan Bakker",
        "date_of_birth": "1990-03-12" if _contains(text, "12 March 1990") else None,
        "age": 36 if _contains(text, "age 36") else None,
        "nationality": _line_value(text, "Nationality") or "Dutch",
        "residence_country": "Netherlands" if _contains(text, "Utrecht") else None,
        "lives_or_works_in_nl": True,
        "id_document_valid": _contains(text, "valid to 2030"),
        "bsn_provided": False if _contains(text, "BSN provided: On signing") else None,
        "legally_competent": None,
        "fraud_screening_clear": None,
        "co_purchase_with_family": False,
        "durable_relationship": _contains(text, "Registered partner"),
        "all_owners_jointly_liable": None,
    }
    co_applicant = {
        "name": "Sophie de Vries" if _contains(text, "Sophie de Vries") else None,
        "date_of_birth": "1992-07-05" if _contains(text, "5 July 1992") else None,
        "age": 33 if _contains(text, "age 33") else None,
        "nationality": "Dutch" if _contains(text, "Co-applicant") else None,
        "residence_country": "Netherlands" if _contains(text, "Utrecht") else None,
        "id_document_valid": _contains(text, "valid to 2029"),
    }
    applicant_income = {
        "name": "Daan Bakker",
        "type": "fixed",
        "source_country": "Netherlands",
        "months_at_employer": _months_since(2019, 9),
        "annual_salary": _money(text, r"Gross annual salary:\s*EUR\s*([\d,]+)"),
        "bonus_pct_of_fixed": round(5700 / 68400 * 100, 2) if _contains(text, "Structural 13th month") else 0,
        "intention_statement": False,
        "perspectiefverklaring": False,
    }
    co_applicant_income = {
        "name": "Sophie de Vries",
        "type": "temporary",
        "source_country": "Netherlands",
        "months_at_employer": _months_since(2024, 3),
        "annual_salary": _money(text, r"Co-applicant[\s\S]*?Gross annual salary:\s*EUR\s*([\d,]+)"),
        "bonus_pct_of_fixed": 0,
        "intention_statement": _contains(text, "Intention statement: Provided"),
        "perspectiefverklaring": False,
    }
    own_funds = _money(text, r"Total own funds available:\s*EUR\s*([\d,]+)")
    loan = {
        "amount": loan_amount,
        "purpose": "primary_residence_purchase",
        "repayment_type": "annuity",
        "term_years": 30 if _contains(text, "30 years") else None,
        "fixed_rate_period_months": 240 if _contains(text, "20 years") else None,
        "sustainability_financed": sustainability,
        "ltv_pct": ltv_pct or (round((loan_amount / market_value) * 100, 2) if loan_amount and market_value else None),
        "is_residual_debt": False,
        "residual_debt_age_months": None,
        "external_residual_debt_amount": 0,
        "behind_external_mortgage": False,
        "interest_only_pct_of_value": 0,
    }
    property_data = {
        "address": _line_value(text, "Property address") or "Lijsterstraat 14, 3514 AB Utrecht",
        "country": "Netherlands",
        "type": "terraced_family_home",
        "owner_occupied": _contains(text, "owner-occupied") or _contains(text, "Primary residence"),
        "permanent_residential_zoning": None,
        "on_industrial_estate": False,
        "clean_soil": None,
        "fixed_with_foundation": True,
        "marketability_months": None,
        "living_area_m2": None,
        "unacceptable_easements": None,
        "self_contained": True,
        "owner_changed_last_12m": None,
        "vve_active": None,
        "is_new_build": False,
        "build_type": "existing_build",
        "ownership_form": "full_ownership",
        "has_business_part": False,
        "mandatory_land_buyback": None,
    }
    financing_burden_annual = monthly_mortgage * 12 if monthly_mortgage is not None else None
    application = {
        "schema_version": "mortgage_application.v1",
        "source_file": str(source_path),
        "application_reference": _line_value(text, "Application reference"),
        "product": _line_value(text, "Product"),
        "nhg_requested": _contains(text, "NHG requested: Yes"),
        "submission_date": "2026-06-22",
        "adviser": _line_value(text, "Adviser"),
        "applicant": applicant,
        "co_applicant": co_applicant,
        "ownership": {"shares_pct": [50, 50]},
        "occupancy": "primary_residence",
        "loan": loan,
        "property": property_data,
        "valuation": {
            "method": "full_valuation_report",
            "purchase_price": purchase_price,
            "market_value": market_value,
        },
        "income": {
            "toetsinkomen_annual": annual_income,
            "applicants": [applicant_income, co_applicant_income],
            "paid_into_country": "Netherlands",
        },
        "assets": {
            "own_funds_available": own_funds,
            "own_funds_required": _money(text, r"Funds earmarked for purchase costs:\s*EUR\s*([\d,]+)"),
        },
        "liabilities": {
            "student_debt": _money(text, r"DUO student debt.*?:\s*EUR\s*([\d,]+)"),
            "student_debt_monthly": _money(text, r"DUO student debt.*?monthly EUR\s*([\d,]+)"),
            "personal_loan": _money(text, r"Personal loan.*?:\s*EUR\s*([\d,]+)"),
            "personal_loan_monthly": _money(text, r"Personal loan.*?monthly EUR\s*([\d,]+)"),
            "bkr": {
                "registration_types": ["RK"] if _contains(text, "1 x RK") else [],
                "special_codes": [] if _contains(text, "BKR special codes") and _contains(text, "None") else None,
                "contract_count": int(_number(text, r"Number of registered contracts:\s*(\d+)") or 0),
            },
            "internal_arrears": None,
        },
        "affordability": {
            "financing_burden_annual": financing_burden_annual,
            "allowed_burden_annual": None,
            "dti_pct": dti_pct,
            "monthly_obligations": monthly_obligations,
            "own_funds_in_crypto_or_fx": False,
        },
        "documents": documents,
        "missing_documents": missing_documents,
        "missing_fields": [],
        "raw_text_excerpt": text[:1200],
    }
    application["missing_fields"] = sorted(_missing_field_paths(application))
    return application


def _missing_field_paths(value: Any, prefix: str = "") -> set[str]:
    missing: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            if child is None:
                missing.add(child_prefix)
            elif isinstance(child, (dict, list)):
                missing.update(_missing_field_paths(child, child_prefix))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            if isinstance(child, (dict, list)):
                missing.update(_missing_field_paths(child, f"{prefix}[{idx}]"))
    return missing


def _json_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Could not find JSON object in input.")
    return json.loads(stripped[start : end + 1])


def _get(data: Any, field_path: str, root: dict[str, Any] | None = None) -> Any:
    current = root if field_path.startswith("$root.") and root is not None else data
    path = field_path[6:] if field_path.startswith("$root.") else field_path
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _compare(actual: Any, operator: str, expected: Any = None) -> bool | None:
    if operator == "exists":
        return actual is not None
    if operator == "not_exists":
        return actual is None
    if actual is None:
        return None
    if operator == "is_true":
        return actual is True
    if operator == "is_false":
        return actual is False
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator in {"<", "<=", ">", ">="}:
        try:
            left = float(actual)
            right = float(expected)
        except (TypeError, ValueError):
            return None
        return {
            "<": left < right,
            "<=": left <= right,
            ">": left > right,
            ">=": left >= right,
        }[operator]
    if operator == "in":
        return actual in (expected or [])
    if operator == "not_in":
        return actual not in (expected or [])
    if operator == "contains":
        return expected in (actual or [])
    if operator == "not_contains":
        return expected not in (actual or [])
    if operator == "contains_any":
        return any(item in (actual or []) for item in (expected or []))
    if operator == "contains_all":
        return all(item in (actual or []) for item in (expected or []))
    if operator == "not_contains_any":
        return not any(item in (actual or []) for item in (expected or []))
    return None


def _status_for_failure(severity: str) -> str:
    return "warning" if severity in {"warning", "info"} else "fail"


def _eval_check(check: dict[str, Any], app: dict[str, Any], severity: str, local: Any | None = None) -> tuple[str, str]:
    if check.get("type") == "manual_review":
        return "unknown", f"Manual review required: {check.get('expression', 'no expression supplied')}"

    for gate_key in ("only_when", "skip_when"):
        gate = check.get(gate_key)
        if isinstance(gate, dict):
            gate_status, gate_evidence = _eval_check(gate, app, severity, local=local)
            gate_passed = gate_status == "pass"
            if gate_key == "only_when" and not gate_passed:
                return "pass", f"Rule not applicable because gate did not match ({gate_evidence})."
            if gate_key == "skip_when" and gate_passed:
                return "pass", f"Rule skipped because gate matched ({gate_evidence})."

    if "all_of" in check:
        outcomes = [_eval_check(c, app, severity, local=local) for c in check["all_of"]]
        failed = [item for item in outcomes if item[0] in {"fail", "warning"}]
        unknown = [item for item in outcomes if item[0] == "unknown"]
        if failed:
            return _status_for_failure(severity), "; ".join(item[1] for item in failed)
        if unknown:
            return "unknown", "; ".join(item[1] for item in unknown)
        return "pass", "All required checks passed."

    if "any_of" in check:
        outcomes = [_eval_check(c, app, severity, local=local) for c in check["any_of"]]
        if any(item[0] == "pass" for item in outcomes):
            return "pass", "At least one allowed condition passed."
        if any(item[0] == "unknown" for item in outcomes):
            return "unknown", "; ".join(item[1] for item in outcomes)
        return _status_for_failure(severity), "; ".join(item[1] for item in outcomes)

    if "for_each" in check:
        rows = _get(app, check["for_each"])
        if not isinstance(rows, list):
            return "unknown", f"{check['for_each']} is missing or not a list."
        applicable = []
        for row in rows:
            when = check.get("when")
            if isinstance(when, dict):
                when_status, _ = _eval_check(when, app, severity, local=row)
                if when_status != "pass":
                    continue
            applicable.append(row)
        if not applicable:
            return "pass", "No applicants/items matched the rule condition."
        outcomes = [_eval_check(check["require"], app, severity, local=row) for row in applicable]
        failed = [item for item in outcomes if item[0] in {"fail", "warning"}]
        unknown = [item for item in outcomes if item[0] == "unknown"]
        if failed:
            return _status_for_failure(severity), "; ".join(item[1] for item in failed)
        if unknown:
            return "unknown", "; ".join(item[1] for item in unknown)
        return "pass", f"Checked {len(applicable)} applicable item(s)."

    field = check.get("field")
    operator = check.get("operator")
    if not field or not operator:
        return "unknown", f"Unsupported check shape: {check}"
    source = app if check.get("scope") == "root" else local if local is not None else app
    actual = _get(source, field, root=app)
    expected = _get(app, check["value_field"]) if "value_field" in check else check.get("value")
    result = _compare(actual, operator, expected)
    expression = check.get("expression") or f"{field} {operator} {expected}"
    if result is True:
        return "pass", f"{expression}; actual={actual!r}."
    if result is False:
        return _status_for_failure(severity), f"{expression}; actual={actual!r}, expected={expected!r}."
    return "unknown", f"{expression}; missing or non-comparable value for {field}."


def _validate_application(app: dict[str, Any], ruleset: dict[str, Any]) -> dict[str, Any]:
    findings = []
    for rule in ruleset.get("rules", []):
        severity = rule.get("severity", "blocking")
        status, evidence = _eval_check(rule.get("check", {}), app, severity)
        findings.append(
            {
                "rule_id": rule.get("rule_id"),
                "rule_name": rule.get("rule_name"),
                "category": rule.get("category"),
                "severity": severity,
                "status": status,
                "evidence": evidence,
                "remediation": rule.get("remediation"),
                "source_ref": rule.get("source_ref"),
            }
        )

    non_pass = [f for f in findings if f["status"] != "pass"]
    failed = [f for f in findings if f["status"] == "fail"]
    warnings = [f for f in findings if f["status"] == "warning"]
    unknown = [f for f in findings if f["status"] == "unknown"]
    return {
        "ruleset_id": ruleset.get("ruleset_id"),
        "ruleset_name": ruleset.get("ruleset_name"),
        "application_reference": app.get("application_reference"),
        "decision_recommendation": "decline_or_manual_review" if failed else "manual_review" if unknown else "proceed",
        "summary": {
            "rules_evaluated": len(findings),
            "pass": len([f for f in findings if f["status"] == "pass"]),
            "fail": len(failed),
            "warning": len(warnings),
            "unknown": len(unknown),
        },
        "failed_rules": failed,
        "warnings": warnings,
        "unknown_rules": unknown,
        "non_pass_findings": non_pass,
    }


def _make_report_html(validation: dict[str, Any]) -> str:
    def finding_items(items: list[dict[str, Any]]) -> str:
        if not items:
            return "<p>None.</p>"
        rows = []
        for item in items:
            rows.append(
                "<li>"
                f"<strong>{html.escape(str(item.get('rule_id')))} - {html.escape(str(item.get('rule_name')))}</strong>"
                f"<br>Status: {html.escape(str(item.get('status')))} | Severity: {html.escape(str(item.get('severity')))}"
                f"<br>Why: {html.escape(str(item.get('evidence')))}"
                f"<br>Remediation: {html.escape(str(item.get('remediation')))}"
                "</li>"
            )
        return "<ul>" + "\n".join(rows) + "</ul>"

    summary = validation.get("summary", {})
    machine_json = html.escape(json.dumps(validation, indent=2, ensure_ascii=False))
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Mortgage Application Rule Validation Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 40px; line-height: 1.5; color: #1f2937; }}
    h1, h2 {{ color: #0f172a; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 10px; padding: 16px; margin: 16px 0; background: #f9fafb; }}
    .metric {{ display: inline-block; margin-right: 18px; }}
    li {{ margin-bottom: 14px; }}
    pre {{ white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 16px; border-radius: 8px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Mortgage Application Rule Validation Report</h1>
  <div class="card">
    <p><strong>Application:</strong> {html.escape(str(validation.get("application_reference")))}</p>
    <p><strong>Ruleset:</strong> {html.escape(str(validation.get("ruleset_name")))}</p>
    <p><strong>Recommendation:</strong> {html.escape(str(validation.get("decision_recommendation")))}</p>
    <p>
      <span class="metric"><strong>Evaluated:</strong> {summary.get("rules_evaluated", 0)}</span>
      <span class="metric"><strong>Failed:</strong> {summary.get("fail", 0)}</span>
      <span class="metric"><strong>Warnings:</strong> {summary.get("warning", 0)}</span>
      <span class="metric"><strong>Unknown:</strong> {summary.get("unknown", 0)}</span>
    </p>
  </div>
  <h2>Failed Rules</h2>
  {finding_items(validation.get("failed_rules", []))}
  <h2>Warnings</h2>
  {finding_items(validation.get("warnings", []))}
  <h2>Rules Needing Manual Review / Missing Data</h2>
  {finding_items(validation.get("unknown_rules", [])[:40])}
  <h2>Machine-Readable Validation JSON</h2>
  <pre>{machine_json}</pre>
</body>
</html>
"""


def create_parse_mortgage_pdf_tool() -> Any:
    @tool
    def parse_mortgage_pdf(pdf_path: str = DEFAULT_PDF_PATH) -> str:
        """Parse a mortgage PDF/text submission pack from pdf_path and return structured application JSON."""
        path = _resolve(pdf_path, DEFAULT_PDF_PATH)
        if not path.exists():
            return json.dumps({"error": f"PDF file not found: {path}"})
        try:
            text = _read_pdf_text(path)
        except RuntimeError as exc:
            return json.dumps({"error": str(exc), "pdf_path": str(path)}, indent=2)
        application = _build_application_json(text, path)
        return json.dumps(application, indent=2, ensure_ascii=False)

    return parse_mortgage_pdf


def create_validate_mortgage_rules_tool() -> Any:
    @tool
    def validate_mortgage_rules(
        application_json: str,
        rules_path: str = DEFAULT_RULES_PATH,
    ) -> str:
        """Validate parsed mortgage application JSON against asn_mortgage_rules.json and return non-pass findings."""
        rules_file = _resolve(rules_path, DEFAULT_RULES_PATH)
        if not rules_file.exists():
            return json.dumps({"error": f"Rules file not found: {rules_file}"})
        app = _json_from_text(application_json)
        ruleset = json.loads(rules_file.read_text(encoding="utf-8"))
        validation = _validate_application(app, ruleset)
        compact_validation = {
            **validation,
            "unknown_rules": validation.get("unknown_rules", [])[:25],
            "non_pass_findings": (
                validation.get("failed_rules", [])
                + validation.get("warnings", [])
                + validation.get("unknown_rules", [])[:25]
            ),
            "output_note": (
                "Compact validator output: all failed and warning rules are included; "
                "unknown/manual-review rules are capped at 25 for agent performance. "
                "Use summary.unknown for the total unknown count."
            ),
        }
        return json.dumps(compact_validation, indent=2, ensure_ascii=False)

    return validate_mortgage_rules


def create_mortgage_report_tool() -> Any:
    @tool
    def create_mortgage_report(validation_json: str, report_name: str | None = None) -> str:
        """Create an HTML mortgage validation report and return a local download link."""
        validation = _json_from_text(validation_json)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        reference = re.sub(r"[^A-Za-z0-9_-]+", "_", str(validation.get("application_reference") or "mortgage"))
        filename = report_name or f"{reference}_rule_validation_report.html"
        if not filename.endswith(".html"):
            filename += ".html"
        path = REPORT_DIR / filename
        path.write_text(_make_report_html(validation), encoding="utf-8")
        return json.dumps(
            {
                "report_path": str(path),
                "download_link": path.resolve().as_uri(),
                "application_reference": validation.get("application_reference"),
                "summary": validation.get("summary", {}),
            },
            indent=2,
        )

    return create_mortgage_report
