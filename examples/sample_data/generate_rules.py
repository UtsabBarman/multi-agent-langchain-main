"""
Generate the machine-readable ASN mortgage acceptance ruleset.

This defines 160+ rules (compactly, via helpers) derived from the public ASN
document "Regels voor het accepteren, verstrekken en wijzigen van een hypotheek"
(v. 1 July 2025), and writes them to `asn_mortgage_rules.json` in the schema the
`check_application.py` evaluator consumes.

Usage (from project root):
    python examples/sample_data/generate_rules.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "asn_mortgage_rules.json"

EUROZONE = [
    "Netherlands", "NL", "Belgium", "BE", "Germany", "DE", "France", "FR",
    "Austria", "AT", "Spain", "ES", "Italy", "IT", "Ireland", "IE", "Portugal",
    "PT", "Luxembourg", "LU", "Finland", "FI", "Greece", "GR", "Slovakia", "SK",
    "Slovenia", "SI", "Estonia", "EE", "Latvia", "LV", "Lithuania", "LT",
    "Cyprus", "CY", "Malta", "MT", "Croatia", "HR",
]

rules: list[dict] = []


def ex(desc, excerpt, status, evidence):
    return {
        "description": desc,
        "application_excerpt": excerpt,
        "expected_status": status,
        "expected_evidence": evidence,
    }


def R(rid, name, cat, sev, src, desc, check, fix, examples, nhg="both", auto=True):
    rules.append({
        "rule_id": rid,
        "rule_name": name,
        "category": cat,
        "severity": sev,
        "nhg_scope": nhg,
        "source_ref": src,
        "description": desc,
        "auto_evaluable": auto,
        "check": check,
        "remediation": fix,
        "examples": examples,
    })


def cmp(field, op, value=None, **extra):
    c = {"field": field, "operator": op}
    if value is not None:
        c["value"] = value
    c.update(extra)
    return c


def manual(expr, **extra):
    return {"type": "manual_review", "expression": expr, **extra}


# Severity shortcuts
NEVER = "blocking_never_deviate"
BLOCK = "blocking"
WARN = "warning"
INFO = "info"

# ============================================================ 2. Applicant
R("APPL-001", "Applicant resides in the Eurozone", "applicant", NEVER, "Ch.2",
  "At application time the applicant must live in a Eurozone country.",
  cmp("applicant.residence_country", "in", EUROZONE,
      expression="applicant.residence_country IN eurozone"),
  "Confirm the applicant lives in a Eurozone country; otherwise ASN cannot lend.",
  [ex("Lives in Utrecht", {"applicant.residence_country": "Netherlands"}, "pass", "NL is Eurozone."),
   ex("Lives in the UK", {"applicant.residence_country": "United Kingdom"}, "fail", "UK is outside the Eurozone.")])

R("APPL-002", "Right to live and work in the Netherlands", "applicant", NEVER, "Ch.2.2",
  "Applicant must be allowed to live and work in NL for the mortgage term when income is needed: Dutch/EU/EEA/Swiss nationality or a qualifying IND permit.",
  {"any_of": [cmp("applicant.nationality", "in", ["Dutch", "NL", "EU", "EEA", "Swiss"]),
              cmp("applicant.residence_permit_type", "in",
                  ["permanent", "EU long-term resident", "duurzaam verblijf", "non-temporary purpose (art 3.5)"])],
   "expression": "EU/EEA/Swiss nationality OR qualifying IND permit"},
  "Provide proof of EU/EEA/Swiss nationality or a qualifying IND residence document.",
  [ex("Dutch national", {"applicant.nationality": "Dutch"}, "pass", "Dutch nationality."),
   ex("Non-EU, temporary permit", {"applicant.nationality": "Indian", "applicant.residence_permit_type": "temporary - study"}, "fail", "Only a temporary permit; not a qualifying document.")])

R("APPL-003", "Binding with the Netherlands", "applicant", BLOCK, "Ch.2.3",
  "Applicant must have binding with NL (lives/works in NL or Dutch nationality). Not required if this income is not needed or for NHG.",
  {"any_of": [cmp("applicant.nationality", "==", "Dutch"),
              cmp("applicant.lives_or_works_in_nl", "is_true")],
   "expression": "Dutch nationality OR lives/works in NL"},
  "Demonstrate binding via residence/employment in NL.",
  [ex("Cross-border worker", {"applicant.lives_or_works_in_nl": True, "applicant.nationality": "German"}, "pass", "Works in NL."),
   ex("No NL ties", {"applicant.lives_or_works_in_nl": False, "applicant.nationality": "French", "nhg_requested": False}, "fail", "No binding with NL.")],
  nhg="without_nhg_only")

R("APPL-004", "Owner-occupied primary residence", "applicant", BLOCK, "Ch.2",
  "The home must be used primarily for own occupancy, not purely business or investment.",
  {"all_of": [cmp("property.owner_occupied", "is_true"),
              cmp("occupancy", "in", ["primary residence", "owner-occupied", "own occupancy"])],
   "expression": "owner_occupied AND occupancy = primary residence"},
  "Confirm owner-occupancy; buy-to-let is not eligible.",
  [ex("Primary residence", {"property.owner_occupied": True, "occupancy": "primary residence"}, "pass", "Owner-occupied."),
   ex("Buy-to-let", {"property.owner_occupied": False, "occupancy": "investment"}, "fail", "Investment occupancy.")])

R("APPL-005", "Co-owner ownership split max 60/40", "applicant", WARN, "Ch.2.1",
  "With two applicants ownership is 50/50, or up to 60/40 if set in notarial conditions before the deed.",
  cmp("ownership.shares_pct", "<=", 60, aggregate="max", expression="max(ownership.shares_pct) <= 60"),
  "Adjust split to within 60/40 (notarial conditions) or use 50/50.",
  [ex("50/50", {"ownership.shares_pct": [50, 50]}, "pass", "Equal ownership."),
   ex("70/30", {"ownership.shares_pct": [70, 30]}, "warning", "70/30 exceeds 60/40.")])

R("APPL-006", "All owners jointly and severally liable", "applicant", NEVER, "Ch.2",
  "All owners must become jointly and severally liable (hoofdelijk schuldenaar) for the whole mortgage.",
  cmp("applicant.all_owners_jointly_liable", "is_true", expression="all owners hoofdelijk schuldenaar"),
  "Ensure every owner signs as joint and several debtor.",
  [ex("Both owners liable", {"applicant.all_owners_jointly_liable": True}, "pass", "All owners jointly liable."),
   ex("One owner not liable", {"applicant.all_owners_jointly_liable": False}, "fail", "Not all owners are jointly liable.")])

R("APPL-007", "Applicant legally competent", "applicant", BLOCK, "Ch.2",
  "Applicant must be legally competent (handelingsbekwaam).",
  cmp("applicant.legally_competent", "is_true", expression="applicant.legally_competent == true"),
  "Confirm legal competence; otherwise representation/guardianship rules apply.",
  [ex("Competent adult", {"applicant.legally_competent": True}, "pass", "Legally competent."),
   ex("Under guardianship", {"applicant.legally_competent": False}, "fail", "Not legally competent.")])

R("APPL-008", "No co-purchase with family", "applicant", BLOCK, "Ch.2",
  "ASN does not provide a mortgage to an applicant who buys together with family (parents may co-sign as debtor only).",
  cmp("applicant.co_purchase_with_family", "is_false", expression="co_purchase_with_family == false"),
  "Restructure so the home is not co-purchased with family.",
  [ex("Couple buying", {"applicant.co_purchase_with_family": False}, "pass", "Not a family co-purchase."),
   ex("Buying with sibling", {"applicant.co_purchase_with_family": True}, "fail", "Co-purchase with family not allowed.")])

R("APPL-009", "Parent co-signer is debtor, not owner", "applicant", INFO, "Ch.2 (exception)",
  "Parents who co-sign do not become owner/occupant but are jointly liable for the whole mortgage.",
  manual("If parent_cosigner: parent is hoofdelijk schuldenaar but not owner/occupant."),
  "Document parent co-signer as debtor only.",
  [ex("Parent co-signer", {"applicant.parent_cosigner": True}, "unknown", "Manual check of co-signer structure.")], auto=False)

R("APPL-010", "Durable relationship and intent to occupy (joint applicants)", "applicant", WARN, "Ch.2.1",
  "Joint applicants must have a durable relationship and intent to keep living in the home for the mortgage term.",
  cmp("applicant.durable_relationship", "is_true", expression="durable_relationship == true (when 2 applicants)"),
  "Confirm durable relationship for joint applicants.",
  [ex("Registered partners", {"applicant.durable_relationship": True}, "pass", "Durable relationship."),
   ex("No durable relationship", {"applicant.durable_relationship": False}, "warning", "Joint applicants without durable relationship.")])

R("APPL-011", "Identity verification (Wwft)", "applicant", NEVER, "Ch.2.6",
  "A valid identity document is required and verified for every applicant.",
  cmp("applicant.id_document_valid", "is_true", expression="applicant.id_document_valid == true"),
  "Provide a valid passport/ID card for every applicant.",
  [ex("Valid passport", {"applicant.id_document_valid": True}, "pass", "Valid ID on file."),
   ex("No valid ID", {"applicant.id_document_valid": False}, "fail", "No valid identity document.")])

R("APPL-012", "BSN available at signing", "applicant", NEVER, "Ch.2.6",
  "A BSN must be available for every applicant when the signed offer is returned (may be supplied at signing for privacy).",
  cmp("applicant.bsn_provided", "is_true", stage="at_signing", expression="bsn_provided == true at signing"),
  "Collect the BSN for every applicant before/at offer signing.",
  [ex("BSN to follow", {"applicant.bsn_provided": False}, "warning", "BSN not yet provided (acceptable before signing).")])

R("APPL-013", "Integrity and fraud screening", "applicant", NEVER, "Ch.2.5",
  "The application is screened against internal/external fraud registers (IVR, CHF, VIS, BKR, SFH/EVA).",
  cmp("applicant.fraud_screening_clear", "is_true", expression="fraud_screening_clear == true"),
  "Resolve any hit in fraud/integrity registers before proceeding.",
  [ex("No hits", {"applicant.fraud_screening_clear": True}, "pass", "Clear screening."),
   ex("Fraud register hit", {"applicant.fraud_screening_clear": False}, "fail", "Hit in fraud/integrity register.")])

# ============================================================ 2.4 BKR
R("BKR-001", "No prohibited BKR special codes", "credit", NEVER, "Ch.2.4",
  "Special codes A and H, and codes 1-5, are not allowed for financing.",
  cmp("liabilities.bkr.special_codes", "not_contains_any", ["A", "H", "1", "2", "3", "4", "5"],
      expression="no special_codes in {A,H,1-5}"),
  "Prohibited BKR special coding; only a previously accepted coding of an existing customer can be reviewed.",
  [ex("Clean", {"liabilities.bkr.special_codes": []}, "pass", "No special codes."),
   ex("Code 2", {"liabilities.bkr.special_codes": ["2"]}, "fail", "Code '2' not allowed.")])

R("BKR-002", "No prohibited BKR registration types", "credit", BLOCK, "Ch.2.4",
  "Registration types RO/ZO, HY, and SR/SK/SH are not allowed (limited NHG-discharge exceptions for HY/RN).",
  cmp("liabilities.bkr.registration_types", "not_contains_any", ["RO", "ZO", "HY", "SR", "SK", "SH"],
      expression="no registration_types in {RO,ZO,HY,SR,SK,SH}"),
  "Check for the documented NHG-discharge exception; otherwise reject.",
  [ex("RK + OA", {"liabilities.bkr.registration_types": ["RK", "OA"]}, "pass", "Allowed types."),
   ex("HY", {"liabilities.bkr.registration_types": ["HY"]}, "fail", "HY not allowed (unless NHG exception).")])

R("BKR-003", "Eight or more BKR contracts triggers individual review", "credit", WARN, "Ch.2.4.1",
  "If 8 or more contracts are registered, assess individually and request an explanation of the credit need.",
  cmp("liabilities.bkr.contract_count", "<", 8, expression="bkr.contract_count < 8"),
  "Request adviser statement on credit need; individual assessment.",
  [ex("2 contracts", {"liabilities.bkr.contract_count": 2}, "pass", "2 contracts."),
   ex("9 contracts", {"liabilities.bkr.contract_count": 9}, "warning", ">=8 contracts need review.")])

R("BKR-004", "Foreign credit check for relevant nationals/residents", "credit", WARN, "Ch.2.4.2",
  "A foreign credit check (CRIF/KSV/SCHUFA/NBB) is required when an applicant is a national of, or lives/works in, IT/AT/DE/BE.",
  manual("If nationality or residence in {IT,AT,DE,BE}: foreign BKR check required."),
  "Order the relevant foreign credit check.",
  [ex("German national", {"applicant.nationality": "German"}, "unknown", "Order SCHUFA check.")], auto=False)

R("BKR-005", "Payment problems at our bank reviewed by Special Servicing", "credit", WARN, "Ch.2.4",
  "Past payment problems / arrears codings at our bank are reviewed by Bijzonder Beheer before acceptance.",
  cmp("liabilities.internal_arrears", "is_false", expression="internal_arrears == false (else Bijzonder Beheer review)"),
  "Route to Bijzonder Beheer for individual assessment.",
  [ex("No internal arrears", {"liabilities.internal_arrears": False}, "pass", "No internal payment problems."),
   ex("Internal arrears", {"liabilities.internal_arrears": True}, "warning", "Requires Bijzonder Beheer review.")])

R("BKR-006", "Disclose foreign credits and obligations", "credit", WARN, "Ch.2.4.2",
  "Credits or financial obligations held abroad must be disclosed and are taken into account.",
  manual("All foreign credits/obligations disclosed and assessed."),
  "Request disclosure of any foreign credits.",
  [ex("Foreign credit disclosed", {"liabilities.foreign_credits_disclosed": True}, "unknown", "Manual verification of disclosure.")], auto=False)

# ============================================================ 3. Income (employed)
R("INC-001", "Stable, freely disposable income required", "income", BLOCK, "Ch.3",
  "Applicant needs stable, freely disposable income to afford the mortgage, paid to an account in NL, Belgium, or Germany.",
  cmp("income.toetsinkomen_annual", ">", 0, expression="toetsinkomen_annual > 0 and stable"),
  "Document stable income via employer's statement / income determination.",
  [ex("EUR 110,400", {"income.toetsinkomen_annual": 110400}, "pass", "Stable test income."),
   ex("No income", {"income.toetsinkomen_annual": 0}, "fail", "No stable test income.")])

R("INC-002", "Temporary contract needs intention statement or perspectiefverklaring", "income", BLOCK, "Ch.3.1/3.2",
  "Temporary-contract income counts only with an intention statement (post-probation, NHG model) or a Perspectiefverklaring/Arbeidsmarktscan.",
  {"for_each": "income.applicants",
   "when": cmp("type", "==", "temporary"),
   "require": {"any_of": [cmp("intention_statement", "is_true"), cmp("perspectiefverklaring", "is_true")]},
   "expression": "each temporary applicant: intention_statement OR perspectiefverklaring"},
  "Obtain an intention statement or Perspectiefverklaring.",
  [ex("Temp + intention", {"income.applicants": [{"name": "S", "type": "temporary", "intention_statement": True, "perspectiefverklaring": False}]}, "pass", "Supported by intention statement."),
   ex("Temp, none", {"income.applicants": [{"name": "S", "type": "temporary", "intention_statement": False, "perspectiefverklaring": False}]}, "fail", "No supporting statement.")])

R("INC-003", "Bonus/overtime capped at 30% of fixed income", "income", WARN, "Ch.3.1",
  "Structural overtime/bonus/commission over the last 12 months count up to 30% of fixed income, if customary and expected.",
  {"for_each": "income.applicants", "require": cmp("bonus_pct_of_fixed", "<=", 30),
   "expression": "each applicant: bonus_pct_of_fixed <= 30"},
  "Cap variable income at 30% of fixed income.",
  [ex("10%", {"income.applicants": [{"name": "D", "bonus_pct_of_fixed": 10}]}, "pass", "Within cap."),
   ex("45%", {"income.applicants": [{"name": "D", "bonus_pct_of_fixed": 45}]}, "warning", "Exceeds 30% cap.")])

R("INC-004", "Foreign income: only fixed income counts", "income", WARN, "Ch.3.1",
  "When income is earned abroad, only fixed income qualifies as test income.",
  {"for_each": "income.applicants",
   "when": cmp("source_country", "not_in", ["Netherlands", "NL"]),
   "require": cmp("type", "==", "fixed"),
   "expression": "each foreign-income applicant: type == fixed"},
  "Count only fixed foreign income.",
  [ex("Fixed DE income", {"income.applicants": [{"name": "X", "type": "fixed", "source_country": "Germany"}]}, "pass", "Fixed foreign income."),
   ex("Temp BE income", {"income.applicants": [{"name": "X", "type": "temporary", "source_country": "Belgium"}]}, "warning", "Foreign income not fixed.")])

R("INC-005", "Perspectiefverklaring: minimum work history", "income", INFO, "Ch.3.2.1",
  "An agency worker's Perspectiefverklaring requires a minimum recent work history (about 14 months) and a certified agency.",
  manual("Perspectiefverklaring valid: certified agency + >=14 months history."),
  "Verify the agency certification and work history.",
  [ex("Agency worker", {"income.applicants": [{"type": "temporary", "perspectiefverklaring": True}]}, "unknown", "Verify perspectiefverklaring validity.")], auto=False)

R("INC-006", "Doctor/PhD in training on temporary contract", "income", INFO, "Ch.3.3",
  "Income of a doctor-in-training (AIOS/ANIOS) or PhD candidate on a temporary contract may count as stable under specific rules.",
  manual("AIOS/ANIOS/PhD temporary income assessed as stable per Ch.3.3."),
  "Apply the dedicated assessment for trainees.",
  [ex("AIOS contract", {"income.applicants": [{"type": "temporary", "role": "AIOS"}]}, "unknown", "Manual trainee assessment.")], auto=False)

R("INC-007", "Salary increase within 6 months counts", "income", INFO, "Ch.3.1",
  "A fixed, unconditional salary increase starting within 6 months may be included.",
  manual("Unconditional increase starting <=6 months may be added to fixed income."),
  "Include only if documented and unconditional.",
  [ex("Raise in 3 months", {"income.applicants": [{"salary_increase_months": 3}]}, "unknown", "Verify unconditional increase.")], auto=False)

R("INC-008", "Pension/AOW/lifelong annuity counts as fixed", "income", INFO, "Ch.3.1",
  "Income from pension, AOW, or a guaranteed lifelong annuity counts as fixed income.",
  manual("Pension/AOW/guaranteed lifelong annuity counts as fixed income."),
  "Provide pension overview / decision letters.",
  [ex("Pension income", {"income.applicants": [{"type": "benefit", "source": "pension"}]}, "unknown", "Verify pension documentation.")], auto=False)

R("INC-009", "Disability benefits (WAO/WAZ/IVA/Wajong) count", "income", INFO, "Ch.3.1",
  "Income from WAO, WAZ, IVA, and Wajong counts as fixed income.",
  manual("WAO/WAZ/IVA/Wajong counted as fixed income."),
  "Provide benefit decision letters.",
  [ex("IVA benefit", {"income.applicants": [{"type": "benefit", "source": "IVA"}]}, "unknown", "Verify benefit documentation.")], auto=False)

R("INC-010", "Income with an end date", "income", INFO, "Ch.3.6",
  "Income with an end date is treated under specific rules and may need robust income elsewhere.",
  manual("Income with end date assessed per Ch.3.6."),
  "Identify the end date and assess continuation.",
  [ex("Fixed-term subsidy", {"income.applicants": [{"income_end_date": "2028-01-01"}]}, "unknown", "Assess income end date.")], auto=False)

R("INC-011", "Employed under 3 months needs UWV + contract", "income", WARN, "Ch.3.7",
  "If an applicant is employed < 3 months (or has a second job), the UWV-verzekeringsbericht and employment contract are required.",
  {"for_each": "income.applicants",
   "when": cmp("months_at_employer", "<", 3),
   "require": cmp("documents", "contains", "uwv_verzekeringsbericht", scope="root"),
   "expression": "each <3-month applicant: 'uwv_verzekeringsbericht' in documents"},
  "Request the UWV-verzekeringsbericht and contract.",
  [ex("2 months + UWV", {"income.applicants": [{"months_at_employer": 2}], "documents": ["uwv_verzekeringsbericht"]}, "pass", "UWV report present."),
   ex("2 months, no UWV", {"income.applicants": [{"months_at_employer": 2}], "documents": []}, "warning", "UWV report missing.")])

R("INC-012", "Rental income is not standard test income", "income", INFO, "Ch.3.9",
  "Income from rent is only counted under specific conditions.",
  manual("Rental income only counted per Ch.3.9 conditions."),
  "Assess rental income against the specific rules.",
  [ex("Room rental", {"income.applicants": [{"source": "rent"}]}, "unknown", "Assess rental income eligibility.")], auto=False)

R("INC-013", "Expense allowances excluded from test income", "income", INFO, "Ch.3.10",
  "Components meant for expenses/training are not freely disposable and are excluded from test income.",
  manual("Exclude expense/training allowances from test income."),
  "Strip non-disposable components from income.",
  [ex("Travel allowance", {"income.applicants": [{"includes_expense_allowance": True}]}, "unknown", "Verify excluded components.")], auto=False)

# ============================================================ 4. Self-employed
R("SE-001", "Self-employed income averaged over 3 years", "income", INFO, "Ch.4.2/4.3",
  "Self-employed test income = average over last 3 book years, capped at the most recent year.",
  manual("test_income = min(avg(last_3_years), last_year)",
         only_when=cmp("self_employed.years_active", "exists")),
  "Provide 3 full book years of figures.",
  [ex("3 book years", {"self_employed.full_book_years": 3, "self_employed.years_active": 5}, "unknown", "Compute average; manual.")])

R("SE-002", "Starting entrepreneur haircut", "income", BLOCK, "Ch.4.5",
  "Active < 36 months: >=24 months -> 90% of average; >=12 months -> 75%. At least 1 full book year required.",
  cmp("self_employed.full_book_years", ">=", 1,
      only_when=cmp("self_employed.years_active", "exists"),
      expression="self_employed.full_book_years >= 1"),
  "Provide >=1 full book year + accountant prognosis; apply 75%/90% haircut.",
  [ex("1 book year", {"self_employed.years_active": 1.5, "self_employed.full_book_years": 1}, "pass", "Apply 75%."),
   ex("No book year", {"self_employed.years_active": 0.3, "self_employed.full_book_years": 0}, "fail", "No full book year.")])

R("SE-003", "No income from a foreign-based business", "income", NEVER, "Ch.4.1/4.4",
  "ASN never establishes income from a business based abroad.",
  cmp("self_employed.business_country", "in", ["Netherlands", "NL", None],
      expression="business_country is NL or n/a"),
  "Foreign-based business income cannot be used.",
  [ex("Dutch BV", {"self_employed.business_country": "Netherlands"}, "pass", "NL business."),
   ex("Spanish business", {"self_employed.business_country": "Spain"}, "fail", "Foreign business income.")])

R("SE-004", "Business liquidity (current ratio) >= 1", "income", BLOCK, "Ch.4.3",
  "For a business with legal personality the current ratio must be >= 1.",
  cmp("self_employed.current_ratio", ">=", 1,
      only_when=cmp("self_employed.current_ratio", "exists"),
      expression="current_ratio >= 1"),
  "Improve liquidity or supply evidence supporting the ratio.",
  [ex("Ratio 1.4", {"self_employed.current_ratio": 1.4}, "pass", "Liquidity OK."),
   ex("Ratio 0.7", {"self_employed.current_ratio": 0.7}, "fail", "Current ratio below 1.")])

R("SE-005", "Business solvency >= 20%", "income", BLOCK, "Ch.4.3",
  "For a business with legal personality the solvency must be >= 20%.",
  cmp("self_employed.solvency_pct", ">=", 20,
      only_when=cmp("self_employed.solvency_pct", "exists"),
      expression="solvency_pct >= 20"),
  "Improve solvency or supply supporting evidence.",
  [ex("Solvency 35%", {"self_employed.solvency_pct": 35}, "pass", "Solvency OK."),
   ex("Solvency 12%", {"self_employed.solvency_pct": 12}, "fail", "Solvency below 20%.")])

R("SE-006", "Simple legal structure (max 3 entities)", "income", BLOCK, "Ch.4.4",
  "The business must have a simple legal structure of at most 3 entities.",
  cmp("self_employed.entity_count", "<=", 3,
      only_when=cmp("self_employed.entity_count", "exists"),
      expression="entity_count <= 3"),
  "Provide consolidated reports; complex structures may be rejected.",
  [ex("2 entities", {"self_employed.entity_count": 2}, "pass", "Simple structure."),
   ex("5 entities", {"self_employed.entity_count": 5}, "fail", "Too many entities.")])

R("SE-007", "More than 2 minority participations = complex", "income", BLOCK, "Ch.4.4.1",
  "With more than 2 minority participations the structure is complex and no business income is established.",
  cmp("self_employed.minority_participations", "<=", 2,
      only_when=cmp("self_employed.minority_participations", "exists"),
      expression="minority_participations <= 2"),
  "No business income with >2 minority participations.",
  [ex("1 participation", {"self_employed.minority_participations": 1}, "pass", "Acceptable."),
   ex("3 participations", {"self_employed.minority_participations": 3}, "fail", "Complex structure.")])

R("SE-008", "Dividend not above profit after tax", "income", INFO, "Ch.4.3.1",
  "Distributed dividend counted may not exceed profit after corporate tax in the same year, with accountant confirmation.",
  manual("counted dividend <= profit after corporate tax; accountant confirms no harm to operations."),
  "Provide accountant confirmation for dividend.",
  [ex("Dividend within profit", {"self_employed.dividend_within_profit": True}, "unknown", "Verify accountant confirmation.")], auto=False)

R("SE-009", "Business income vs salaried (>=32h) cap 30%", "income", WARN, "Ch.4.6",
  "If the applicant also has a salaried job of >=32h, business test income may not exceed 30% of the salaried annual income.",
  manual("if salaried_hours >= 32: business_income <= 30% of salaried annual income."),
  "Cap business income at 30% of salaried income.",
  [ex("32h job + business", {"self_employed.also_salaried_hours": 36}, "unknown", "Apply 30% cap.")], auto=False)

R("SE-010", "Assessment statement when business income not needed", "income", INFO, "Ch.4.7",
  "If business income is not needed, a beoordelingsverklaring must confirm the business can be left out (losses may correct income).",
  manual("beoordelingsverklaring required when KvK registration income not used."),
  "Obtain a beoordelingsverklaring.",
  [ex("KvK reg not needed", {"self_employed.income_used": False}, "unknown", "Obtain assessment statement.")], auto=False)

# ============================================================ 5. Affordability
R("AFF-001", "Financing burden within allowed burden", "affordability", NEVER, "Ch.5",
  "Financing burden may not exceed the allowed burden (NIBUD/Trhk).",
  cmp("affordability.financing_burden_annual", "<=", None,
      value_field="affordability.allowed_burden_annual",
      expression="financing_burden_annual <= allowed_burden_annual"),
  "Reduce loan/obligations so burden is within the allowed burden.",
  [ex("Within", {"affordability.financing_burden_annual": 24600, "affordability.allowed_burden_annual": 31000}, "pass", "Within allowance."),
   ex("Exceeds", {"affordability.financing_burden_annual": 33000, "affordability.allowed_burden_annual": 31000}, "fail", "Exceeds allowance.")])

R("AFF-002", "Annuity-over-30-years test method", "affordability", NEVER, "Ch.5.2.1",
  "The financing burden is always determined on an annuity basis over max 30 years, regardless of repayment type.",
  manual("Burden computed as annuity over <=30 years using the test rate."),
  "Apply the annuity test method.",
  [ex("Interest-only loan", {"loan.repayment_type": "interest_only"}, "unknown", "Annuity test still applies.")], auto=False)

R("AFF-003", "Test rate by fixed-rate period", "affordability", NEVER, "Ch.5.2.1",
  "Test rate = offer rate if fixed-rate period >= 120 months; otherwise the higher of the offer rate or the AFM test rate.",
  manual("RVP>=120m: test rate = offer rate; RVP<120m: max(offer rate, AFM test rate)."),
  "Use the correct test rate for the fixed-rate period.",
  [ex("20-year fixed", {"loan.fixed_rate_period_months": 240}, "unknown", "Test rate = offer rate.")], auto=False)

R("AFF-004", "NIBUD financing-burden percentages", "affordability", NEVER, "Ch.5.2.2",
  "Allowed burden uses the annual NIBUD financing-burden percentages from the Trhk, based on the highest test income and weighted test rate.",
  manual("Use NIBUD percentages from the Trhk for the relevant year."),
  "Apply current NIBUD percentages.",
  [ex("Two incomes", {"income.toetsinkomen_annual": 110400}, "unknown", "Apply NIBUD table.")], auto=False)

R("AFF-005", "Revolving credit test charge 2% of limit", "affordability", NEVER, "Ch.5.3",
  "A revolving credit (doorlopend krediet) is tested at 2% of the limit per month.",
  manual("revolving credit test charge = 2% of limit/month."),
  "Apply 2% of the limit as the monthly test charge.",
  [ex("Revolving 10k", {"liabilities.revolving_limit": 10000}, "unknown", "Test charge = 200/month.")], auto=False)

R("AFF-006", "Reducing-balance BKR credit test charge", "affordability", NEVER, "Ch.5.3",
  "A reducing-balance BKR credit is tested at the registered amount divided by the term (actual charge).",
  manual("aflopend krediet test charge = BKR amount / term."),
  "Apply registered amount divided by term.",
  [ex("Personal loan", {"liabilities.personal_loan": 6500}, "unknown", "Apply BKR amount/term.")], auto=False)

R("AFF-007", "Operational lease pre-2022 correction factor", "affordability", NEVER, "Ch.5.3",
  "Operational car lease is the BKR amount / term; BKR registrations before 1-4-2022 are corrected by dividing by 0.65.",
  manual("operational lease: BKR amount/term; pre-2022 registrations / 0.65."),
  "Apply the 0.65 correction for pre-2022 lease registrations.",
  [ex("Lease 2021", {"liabilities.lease_registration_year": 2021}, "unknown", "Apply 0.65 correction.")], auto=False)

R("AFF-008", "Partner alimony reduces test income", "affordability", NEVER, "Ch.5.3",
  "Partner alimony payable is deducted from the applicant's test income before applying the percentage.",
  manual("partner alimony payable reduces test income."),
  "Deduct partner alimony from test income.",
  [ex("Pays partner alimony", {"liabilities.partner_alimony_monthly": 400}, "unknown", "Deduct from test income.")], auto=False)

R("AFF-009", "Child alimony not deducted from income", "affordability", INFO, "Ch.5.3",
  "Child alimony payable is not deducted from test income.",
  manual("child alimony NOT deducted from test income."),
  "Do not deduct child alimony from income.",
  [ex("Pays child alimony", {"liabilities.child_alimony_monthly": 300}, "unknown", "No income deduction.")], auto=False)

R("AFF-010", "Leasehold canon as annual obligation", "affordability", NEVER, "Ch.5.3",
  "An annual leasehold canon (erfpachtcanon) is taken into account as an obligation at its annual amount.",
  manual("erfpachtcanon counted as annual obligation."),
  "Include the annual canon as an obligation.",
  [ex("Canon 1200/yr", {"property.erfpacht_canon_annual": 1200}, "unknown", "Include canon obligation.")], auto=False)

R("AFF-011", "Student debt tested at the term amount (DUO)", "affordability", NEVER, "Ch.5.7",
  "A DUO student debt is tested at the term amount (grossed up under the Trhk where interest is deductible).",
  manual("student debt test charge = DUO term amount (grossed per Trhk)."),
  "Apply the DUO term amount as the test charge.",
  [ex("DUO debt", {"liabilities.student_debt": 9800}, "unknown", "Apply DUO term amount.")], auto=False)

R("AFF-012", "Student debt: no payment-relief reduction", "affordability", NEVER, "Ch.5.7.2",
  "No account is taken of an interest-only period or income-based reduction; the annuity term amount on the current debt/rate/term is used.",
  manual("ignore aflosvrije periode / draagkracht reduction; use annuity on current debt."),
  "Compute the annuity term amount on current debt/rate/term.",
  [ex("Reduced DUO payment", {"liabilities.student_debt_relief": True}, "unknown", "Use full annuity term amount.")], auto=False)

R("AFF-013", "Family loan/gift construction conditions", "affordability", NEVER, "Ch.5.4",
  "A family loan may be left out of the allowed burden only if it meets all leen-/schenk conditions (parents in private, written, market rate fixed >=10y, annuity/linear <=30y, within annual gift exemption, not callable).",
  manual("family loan excluded only if all leen-/schenk conditions are met."),
  "Verify each leen-/schenk condition.",
  [ex("Parental loan", {"liabilities.family_loan": True}, "unknown", "Verify all conditions.")], auto=False)

R("AFF-014", "Double charges affordability (bridging)", "affordability", BLOCK, "Ch.5.5",
  "Double housing charges must be affordable within the allowed burden; otherwise own funds must cover them (existing build 6 months; new build 12-24 months).",
  manual("double charges within allowed burden or covered by own funds."),
  "Demonstrate affordability or sufficient own funds for double charges.",
  [ex("Old home unsold", {"affordability.double_charges": True}, "unknown", "Assess double-charge affordability.")], auto=False)

R("AFF-015", "Own funds above EUR 15,000 must be proven", "affordability", BLOCK, "Ch.5.6",
  "Own funds above EUR 15,000 (and always for NHG) must be evidenced.",
  manual("own funds > 15,000 (or any for NHG) must be proven."),
  "Provide evidence of own funds.",
  [ex("Needs 22k own funds", {"affordability.own_funds_required": 22000}, "unknown", "Provide proof of own funds.")], auto=False)

R("AFF-016", "Foreign currency and crypto excluded as own funds", "affordability", NEVER, "Ch.5.6",
  "Foreign currency and cryptocurrency are never counted as own funds.",
  cmp("affordability.own_funds_in_crypto_or_fx", "is_false",
      expression="own funds not in crypto/foreign currency"),
  "Convert/replace with eligible own funds.",
  [ex("EUR savings", {"affordability.own_funds_in_crypto_or_fx": False}, "pass", "Eligible own funds."),
   ex("Crypto down payment", {"affordability.own_funds_in_crypto_or_fx": True}, "fail", "Crypto not counted as own funds.")])

R("AFF-017", "Other mortgages test charge", "affordability", NEVER, "Ch.5.3.1",
  "Other (non-own-home) mortgages are tested at their annuity charge, or 2% of the original principal per month if data is insufficient.",
  manual("other mortgage test charge = annuity charge or 2% of original principal."),
  "Provide details of other mortgages.",
  [ex("Second mortgage", {"liabilities.other_mortgage": True}, "unknown", "Apply annuity/2% test charge.")], auto=False)

R("AFF-018", "DTI indicative threshold (proxy)", "affordability", INFO, "Pipeline proxy",
  "Optional debt-to-income proxy for pipelines supplying a DTI; ASN uses NIBUD burden, not a flat DTI.",
  cmp("affordability.dti_pct", "<=", 43,
      skip_when=cmp("affordability.dti_pct", "not_exists"),
      expression="dti_pct <= 43 (if supplied)"),
  "If DTI is high, rely on the NIBUD burden test (AFF-001).",
  [ex("DTI 30%", {"affordability.dti_pct": 30}, "pass", "Within proxy."),
   ex("DTI 50%", {"affordability.dti_pct": 50}, "info", "Above proxy; check NIBUD burden.")])

# ============================================================ 5.8 Residual debt
R("RES-001", "Residual debt arose within 1 year", "loan", BLOCK, "Ch.5.8.1",
  "A residual debt can be financed only if it arose less than 1 year before the new application (transfer date).",
  cmp("loan.residual_debt_age_months", "<=", 12,
      only_when=cmp("loan.is_residual_debt", "is_true"),
      expression="residual_debt_age_months <= 12"),
  "Residual debt older than 1 year cannot be co-financed.",
  [ex("8 months old", {"loan.is_residual_debt": True, "loan.residual_debt_age_months": 8}, "pass", "Within 1 year."),
   ex("18 months old", {"loan.is_residual_debt": True, "loan.residual_debt_age_months": 18}, "fail", "Older than 1 year.")])

R("RES-002", "Residual debt term max 15 years, linear", "loan", BLOCK, "Ch.5.8.1",
  "Residual-debt financing has a max term of 15 years and must be repaid linearly, fully using the available burden.",
  cmp("loan.residual_debt_term_years", "<=", 15,
      only_when=cmp("loan.is_residual_debt", "is_true"),
      expression="residual_debt_term_years <= 15"),
  "Set the residual-debt term to <=15 years, linear repayment.",
  [ex("12-year linear", {"loan.is_residual_debt": True, "loan.residual_debt_term_years": 12}, "pass", "Within 15 years."),
   ex("20-year term", {"loan.is_residual_debt": True, "loan.residual_debt_term_years": 20}, "fail", "Exceeds 15 years.")])

R("RES-003", "External residual debt capped at EUR 30,000", "loan", BLOCK, "Ch.5.8.1",
  "Financing a residual debt that did not arise at an ASN brand is capped at EUR 30,000.",
  cmp("loan.external_residual_debt_amount", "<=", 30000,
      only_when=cmp("loan.external_residual_debt_amount", "exists"),
      expression="external_residual_debt_amount <= 30000"),
  "Cap external residual-debt financing at EUR 30,000.",
  [ex("External 25k", {"loan.external_residual_debt_amount": 25000}, "pass", "Within cap."),
   ex("External 40k", {"loan.external_residual_debt_amount": 40000}, "fail", "Exceeds EUR 30,000.")])

R("RES-004", "WOZ valuation not allowed with bridging", "loan", NEVER, "Ch.5.8.4",
  "A WOZ valuation is never allowed to value the home to be sold when a bridging loan is requested.",
  manual("WOZ valuation forbidden for sold-home value when bridging."),
  "Use a validated valuation or sale price instead.",
  [ex("Bridging + WOZ", {"loan.bridging": True, "valuation.method": "WOZ"}, "unknown", "WOZ not allowed with bridging.")], auto=False)

# ============================================================ 6. The house
R("HOUSE-001", "House located in the Netherlands", "property", NEVER, "Ch.6.1",
  "ASN finances only a home located in the Netherlands.",
  cmp("property.country", "in", ["Netherlands", "NL"], expression="property.country == NL"),
  "Property must be in NL.",
  [ex("Utrecht", {"property.country": "Netherlands"}, "pass", "In NL."),
   ex("Antwerp", {"property.country": "Belgium"}, "fail", "Not in NL.")])

R("HOUSE-002", "Permanent residential zoning", "property", BLOCK, "Ch.6.1",
  "The home must be zoned by the municipality for permanent habitation.",
  cmp("property.permanent_residential_zoning", "is_true", expression="permanent_residential_zoning == true"),
  "Confirm permanent residential zoning.",
  [ex("Residential", {"property.permanent_residential_zoning": True}, "pass", "Residential zoning."),
   ex("Recreational zoning", {"property.permanent_residential_zoning": False}, "fail", "Not zoned for permanent habitation.")])

R("HOUSE-003", "Not on a commercial/industrial estate", "property", BLOCK, "Ch.6.1",
  "The home must not be located on a commercial or industrial estate.",
  cmp("property.on_industrial_estate", "is_false", expression="on_industrial_estate == false"),
  "Property cannot be on a commercial/industrial estate.",
  [ex("Residential street", {"property.on_industrial_estate": False}, "pass", "Not industrial."),
   ex("Industrial estate", {"property.on_industrial_estate": True}, "fail", "On industrial estate.")])

R("HOUSE-004", "Clean soil", "property", BLOCK, "Ch.6.1",
  "The home must stand on clean (non-contaminated) ground.",
  cmp("property.clean_soil", "is_true", expression="clean_soil == true"),
  "Provide evidence of clean soil.",
  [ex("Clean soil", {"property.clean_soil": True}, "pass", "Clean soil."),
   ex("Contaminated", {"property.clean_soil": False}, "fail", "Soil not clean.")])

R("HOUSE-005", "Fixed structure with own foundation", "property", NEVER, "Ch.6.1",
  "The home must be permanently fixed with its own foundation (cannot roll or float).",
  cmp("property.fixed_with_foundation", "is_true", expression="fixed_with_foundation == true"),
  "Only fixed homes with own foundation are eligible.",
  [ex("Brick house", {"property.fixed_with_foundation": True}, "pass", "Fixed with foundation."),
   ex("Houseboat", {"property.fixed_with_foundation": False}, "fail", "Not fixed / no foundation.")])

R("HOUSE-006", "Marketability max 12 months", "property", BLOCK, "Ch.6.1",
  "The home must have a marketability (courantheid) of at most 12 months.",
  cmp("property.marketability_months", "<=", 12,
      only_when=cmp("property.marketability_months", "exists"),
      expression="marketability_months <= 12"),
  "Property must be sellable within 12 months.",
  [ex("8 months", {"property.marketability_months": 8}, "pass", "Marketable."),
   ex("18 months", {"property.marketability_months": 18}, "fail", "Marketability over 12 months.")])

R("HOUSE-007", "Minimum living area 30 m2", "property", NEVER, "Ch.6.1",
  "The home must have a minimum living area of 30 m2.",
  cmp("property.living_area_m2", ">=", 30,
      only_when=cmp("property.living_area_m2", "exists"),
      expression="living_area_m2 >= 30"),
  "Homes under 30 m2 are not eligible.",
  [ex("85 m2", {"property.living_area_m2": 85}, "pass", "Above minimum."),
   ex("24 m2 studio", {"property.living_area_m2": 24}, "fail", "Below 30 m2.")])

R("HOUSE-008", "No unacceptable easements/leasehold conditions", "property", NEVER, "Ch.6.1",
  "The land must not carry unacceptable easements or leasehold conditions.",
  cmp("property.unacceptable_easements", "is_false", expression="unacceptable_easements == false"),
  "Resolve or clarify any unacceptable easements.",
  [ex("No issues", {"property.unacceptable_easements": False}, "pass", "Clean title."),
   ex("Mandatory rental clause", {"property.unacceptable_easements": True}, "fail", "Unacceptable easement.")])

R("HOUSE-009", "Fully self-contained dwelling", "property", NEVER, "Ch.6.1",
  "The home must be fully self-contained: own front door, kitchen, toilet, and bathroom.",
  cmp("property.self_contained", "is_true", expression="self_contained == true"),
  "Only fully self-contained dwellings are eligible.",
  [ex("Self-contained", {"property.self_contained": True}, "pass", "Own door/kitchen/wc/bath."),
   ex("Shared kitchen", {"property.self_contained": False}, "fail", "Not self-contained.")])

R("HOUSE-010", "Owner changed within 12 months -> extra investigation", "property", WARN, "Ch.6.1",
  "If the home changed owner in the 12 months before transfer, extra investigation is required (except inheritance/foundation buy-back).",
  cmp("property.owner_changed_last_12m", "is_false",
      expression="owner_changed_last_12m == false (else extra investigation)"),
  "Perform extra investigation into the recent ownership change.",
  [ex("Stable ownership", {"property.owner_changed_last_12m": False}, "pass", "No recent flip."),
   ex("Recently flipped", {"property.owner_changed_last_12m": True}, "warning", "Recent ownership change; investigate.")])

R("HOUSE-011", "Building condition at least reasonable", "property", BLOCK, "Ch.6.1.1",
  "The whole home's building condition must be at least reasonable per the valuation; otherwise a structural report and bouwdepot are required.",
  manual("building condition >= reasonable, else bouwkundig rapport + bouwdepot."),
  "Provide a structural report and reserve maintenance in a bouwdepot.",
  [ex("Reasonable condition", {"property.building_condition": "reasonable"}, "unknown", "Verify valuation condition.")], auto=False)

R("HOUSE-012", "Poor element threshold EUR 2,500 to bouwdepot", "property", INFO, "Ch.6.1.1",
  "If a single element is poor/moderate, the estimated direct cost is reserved in a bouwdepot above a EUR 2,500 threshold.",
  manual("poor element cost reserved in bouwdepot above EUR 2,500."),
  "Reserve the estimated repair cost in a bouwdepot.",
  [ex("Roof moderate", {"property.element_repair_cost": 4000}, "unknown", "Reserve in bouwdepot.")], auto=False)

R("HOUSE-013", "Apartment requires active VVE and reserves", "property", BLOCK, "Ch.6.2",
  "For an apartment there must be an active VVE with a long-term maintenance plan and an annual reservation of at least 0.5% of rebuild value.",
  cmp("property.vve_active", "is_true",
      only_when=cmp("property.type", "in", ["apartment", "appartement"]),
      expression="apartment -> vve_active == true (+ MJOP + >=0.5% reserve)"),
  "Provide proof of an active VVE, MJOP, and reserves.",
  [ex("Active VVE", {"property.type": "apartment", "property.vve_active": True}, "pass", "Active VVE."),
   ex("No VVE", {"property.type": "apartment", "property.vve_active": False}, "fail", "No active VVE.")])

R("HOUSE-014", "New build needs definitive permit", "property", NEVER, "Ch.6.3",
  "New build requires a definitive environmental permit (omgevingsvergunning).",
  cmp("property.definitive_permit", "is_true",
      only_when=cmp("property.is_new_build", "is_true"),
      expression="new build -> definitive_permit == true"),
  "Obtain the definitive omgevingsvergunning.",
  [ex("Permit granted", {"property.is_new_build": True, "property.definitive_permit": True}, "pass", "Permit in place."),
   ex("No permit", {"property.is_new_build": True, "property.definitive_permit": False}, "fail", "No definitive permit.")])

R("HOUSE-015", "Project build needs completion guarantee", "property", NEVER, "Ch.6.3",
  "Project-built new homes require a completion guarantee / warranty certificate (afbouwgarantie/waarborgcertificaat).",
  cmp("property.completion_guarantee", "is_true",
      only_when=cmp("property.build_type", "==", "projectbouw"),
      expression="projectbouw -> completion_guarantee == true"),
  "Provide afbouwgarantie/waarborgcertificaat for project build.",
  [ex("Warranty present", {"property.build_type": "projectbouw", "property.completion_guarantee": True}, "pass", "Guarantee present."),
   ex("No warranty", {"property.build_type": "projectbouw", "property.completion_guarantee": False}, "fail", "No completion guarantee.")])

R("HOUSE-016", "CPO max 80% LTV + CAR insurance", "property", BLOCK, "Ch.6.3.1",
  "CPO without warranty: max 80% LTV (and 80% income-based) with CAR insurance for the whole build.",
  cmp("loan.ltv_pct", "<=", 80,
      only_when=cmp("property.build_type", "==", "CPO"),
      expression="CPO -> ltv_pct <= 80"),
  "Cap CPO LTV at 80% and arrange CAR insurance.",
  [ex("CPO 78%", {"property.build_type": "CPO", "loan.ltv_pct": 78}, "pass", "Within 80%."),
   ex("CPO 95%", {"property.build_type": "CPO", "loan.ltv_pct": 95}, "fail", "Exceeds 80%.")])

R("HOUSE-017", "Prefab without warranty conditions", "property", BLOCK, "Ch.6.3.2",
  "Prefab without warranty: max 90% income-based, builder affiliated to Bouwgarant/Woningborg, payment afterward, CAR insurance.",
  manual("prefab: <=90% income norm, Bouwgarant/Woningborg, pay after delivery, CAR."),
  "Verify prefab conditions.",
  [ex("Prefab build", {"property.build_type": "prefab"}, "unknown", "Verify prefab conditions.")], auto=False)

R("HOUSE-018", "Self-managed/self-build max 80% LTV", "property", BLOCK, "Ch.6.3.3/6.3.4",
  "Bouw in eigen beheer / zelfbouw without warranty: max 80% LTV with a building budget and CAR insurance.",
  cmp("loan.ltv_pct", "<=", 80,
      only_when=cmp("property.build_type", "in", ["eigen_beheer", "zelfbouw"]),
      expression="eigen_beheer/zelfbouw -> ltv_pct <= 80"),
  "Cap LTV at 80% with building budget and CAR insurance.",
  [ex("Zelfbouw 75%", {"property.build_type": "zelfbouw", "loan.ltv_pct": 75}, "pass", "Within 80%."),
   ex("Zelfbouw 88%", {"property.build_type": "zelfbouw", "loan.ltv_pct": 88}, "fail", "Exceeds 80%.")])

R("HOUSE-019", "Cooperative ownership conditions", "property", BLOCK, "Ch.6.4",
  "Cooperative ownership requires an own membership right pledged by notarial deed, an association of >=25 apartments, and professional management.",
  cmp("property.cooperative_min_25_units", "is_true",
      only_when=cmp("property.ownership_form", "==", "cooperative"),
      expression="cooperative -> >=25 units (+ pledge + professional mgmt)"),
  "Verify cooperative association size and governance.",
  [ex("30-unit coop", {"property.ownership_form": "cooperative", "property.cooperative_min_25_units": True}, "pass", "Qualifying coop."),
   ex("12-unit coop", {"property.ownership_form": "cooperative", "property.cooperative_min_25_units": False}, "fail", "Coop under 25 units.")])

R("HOUSE-020", "No additional/bridge loan on cooperative ownership", "property", NEVER, "Ch.6.4",
  "A higher inschrijving, follow-up, or bridging mortgage is never possible with cooperative ownership.",
  manual("no higher inschrijving/vervolg/overbrugging for cooperative ownership."),
  "These products are not available for cooperative ownership.",
  [ex("Coop + bridge", {"property.ownership_form": "cooperative", "loan.bridging": True}, "unknown", "Not allowed for coop.")], auto=False)

R("HOUSE-021", "Kangaroo/care home single ownership", "property", BLOCK, "Ch.6.5",
  "Kangaroo/care homes are financed only as 2 self-contained units on 1 cadastral whole owned by 1 owner (or 2 with a durable relationship).",
  manual("kangaroo/care home: 2 units, 1 cadastral whole, single owner who can pay."),
  "Verify single ownership of the combined property.",
  [ex("Care annex", {"property.type": "mantelzorgwoning"}, "unknown", "Verify ownership structure.")], auto=False)

R("HOUSE-022", "Partial residential zoning >= 60% residential", "property", BLOCK, "Ch.6.6",
  "With partial business/agricultural zoning the residential part must be >=60% of total market value (split NWWI valuation); business part financed max 70%.",
  cmp("property.residential_value_pct", ">=", 60,
      only_when=cmp("property.has_business_part", "is_true"),
      expression="business part -> residential_value_pct >= 60"),
  "Provide a split NWWI valuation; finance the business part at <=70%.",
  [ex("70% residential", {"property.has_business_part": True, "property.residential_value_pct": 70}, "pass", "Residential majority."),
   ex("40% residential", {"property.has_business_part": True, "property.residential_value_pct": 40}, "fail", "Residential below 60%.")])

R("HOUSE-023", "No mandatory land buy-back (erfpacht)", "property", NEVER, "Ch.6.7",
  "ASN does not lend when there is a pre-agreed mandatory/minimum buy-back price for the land.",
  cmp("property.mandatory_land_buyback", "is_false", expression="mandatory_land_buyback == false"),
  "Mandatory land buy-back constructions are not eligible.",
  [ex("No buy-back", {"property.mandatory_land_buyback": False}, "pass", "No mandatory buy-back."),
   ex("Buy-back clause", {"property.mandatory_land_buyback": True}, "fail", "Mandatory land buy-back.")])

R("HOUSE-024", "Government leasehold canon fixed >= 10 years", "property", BLOCK, "Ch.6.7.1",
  "For government-issued leasehold, the canon must be fixed for at least 10 more years, or the new canon must be known.",
  manual("government erfpacht: canon fixed >=10y or new canon known."),
  "Confirm canon fixity or the future canon level.",
  [ex("Municipal leasehold", {"property.erfpacht_issuer": "municipality"}, "unknown", "Verify canon fixity.")], auto=False)

R("HOUSE-025", "Private leasehold conditions (pre/post 2013)", "property", BLOCK, "Ch.6.7.2",
  "Private leasehold needs a green erfpacht opinion (pre-2013) or KNB-model perpetual conditions (post-2013), with future canon known.",
  manual("private erfpacht: green opinion (pre-2013) or KNB model perpetual (post-2013)."),
  "Provide the erfpacht opinion / KNB-conform conditions.",
  [ex("Private leasehold", {"property.erfpacht_issuer": "private"}, "unknown", "Verify leasehold conditions.")], auto=False)

R("HOUSE-026", "Groninger akte conditions", "property", INFO, "Ch.6.8",
  "A Groninger akte is accepted only if no other dissolving/suspensive conditions are attached to the purchase (notary verifies).",
  manual("Groninger akte accepted if no other conditions remain at transfer."),
  "Confirm no other purchase conditions remain.",
  [ex("Groninger akte", {"property.groninger_akte": True}, "unknown", "Notary verifies conditions.")], auto=False)

R("HOUSE-027", "Buyer-support (koperssteun) needs NHG approval", "property", BLOCK, "Ch.6.9",
  "Buyer-support constructions are accepted only with NHG and NHG approval of the construction at the binding offer.",
  manual("koperssteun: NHG requested and construction NHG-approved."),
  "Confirm NHG approval of the construction.",
  [ex("Koperssteun", {"property.buyer_support": True, "nhg_requested": True}, "unknown", "Verify NHG approval.")], auto=False)

# ============================================================ 7. Recreational
R("REC-001", "Recreational home valuation required", "property", NEVER, "Ch.7.1",
  "A valuation report is mandatory for a recreational home.",
  cmp("documents", "contains", "taxatierapport",
      only_when=cmp("property.type", "in", ["recreational", "recreatiewoning"]),
      expression="recreational -> taxatierapport in documents"),
  "Provide a valuation report for the recreational home.",
  [ex("Recreational + taxatie", {"property.type": "recreatiewoning", "documents": ["taxatierapport"]}, "pass", "Valuation present."),
   ex("Recreational, no taxatie", {"property.type": "recreatiewoning", "documents": []}, "fail", "Valuation missing.")])

R("REC-002", "Recreational home LTV max 70%", "property", BLOCK, "Ch.7.1",
  "A recreational home may be financed up to 70% of market value.",
  cmp("loan.ltv_pct", "<=", 70,
      only_when=cmp("property.type", "in", ["recreational", "recreatiewoning"]),
      expression="recreational -> ltv_pct <= 70"),
  "Cap recreational LTV at 70%.",
  [ex("65%", {"property.type": "recreatiewoning", "loan.ltv_pct": 65}, "pass", "Within 70%."),
   ex("80%", {"property.type": "recreatiewoning", "loan.ltv_pct": 80}, "fail", "Exceeds 70%.")])

R("REC-003", "Recreational home fully amortising", "property", BLOCK, "Ch.7.1",
  "A recreational-home mortgage must be repaid fully on an annuity or linear basis.",
  cmp("loan.repayment_type", "in", ["annuity", "linear"],
      only_when=cmp("property.type", "in", ["recreational", "recreatiewoning"]),
      expression="recreational -> repayment_type in {annuity, linear}"),
  "Use annuity/linear repayment for recreational homes.",
  [ex("Annuity", {"property.type": "recreatiewoning", "loan.repayment_type": "annuity"}, "pass", "Amortising."),
   ex("Interest-only", {"property.type": "recreatiewoning", "loan.repayment_type": "interest_only"}, "fail", "Interest-only not allowed.")])

R("REC-004", "No bridging on a recreational home", "property", NEVER, "Ch.7.1",
  "A bridging loan on a recreational home is not possible.",
  manual("no bridging loan secured on a recreational home."),
  "Bridging is not available for recreational homes.",
  [ex("Recreational + bridge", {"property.type": "recreatiewoning", "loan.bridging": True}, "unknown", "Bridging not allowed.")], auto=False)

R("REC-005", "Recreational construction and connection", "property", BLOCK, "Ch.7.2",
  "A recreational home must be of stone (or wood if built >=2020), non-movable, and connected to water and electricity, with recreational zoning.",
  manual("recreational home: stone (or wood >=2020), fixed, utilities connected, recreational zoning."),
  "Verify construction, connections, and zoning.",
  [ex("Stone chalet", {"property.type": "recreatiewoning"}, "unknown", "Verify construction/zoning.")], auto=False)

# ============================================================ 8. Valuation
R("VAL-001", "NWWI taxatie required above EUR 1,000,000", "valuation", NEVER, "Ch.8.1",
  "A validated NWWI valuation report is required when the total mortgage on the home exceeds EUR 1,000,000.",
  cmp("documents", "contains", "taxatierapport",
      only_when=cmp("loan.amount", ">", 1000000),
      expression="loan.amount > 1,000,000 -> taxatierapport in documents"),
  "Provide a validated NWWI valuation report.",
  [ex("1.2M + taxatie", {"loan.amount": 1200000, "documents": ["taxatierapport"]}, "pass", "Valuation present."),
   ex("1.2M, no taxatie", {"loan.amount": 1200000, "documents": []}, "fail", "Valuation required above 1M.")])

R("VAL-002", "Validation mandatory when possible", "valuation", NEVER, "Ch.8.1",
  "If validation of the valuation report is possible, it is mandatory.",
  manual("if validation possible -> validated report required."),
  "Use a validated valuation report.",
  [ex("Standard purchase", {"valuation.method": "taxatierapport"}, "unknown", "Ensure validation.")], auto=False)

R("VAL-003", "Calcasa desktop valuation conditions", "valuation", BLOCK, "Ch.8.2",
  "Calcasa desktop valuation is allowed only if the total mortgage is <= EUR 1,000,000, the home is >= 2 years old, there is no leasehold/opstal, and the application fits the standard norm.",
  manual("Calcasa allowed: <=1,000,000, home >=2y, no erfpacht/opstal, standaardnorm."),
  "Use a full valuation if Calcasa conditions are not met.",
  [ex("Calcasa used", {"valuation.method": "calcasa"}, "unknown", "Verify Calcasa conditions.")], auto=False)

R("VAL-004", "Calcasa max 90% of value", "valuation", BLOCK, "Ch.8.2",
  "With a Calcasa desktop valuation the total mortgage may not exceed 90% of the assessed market value.",
  cmp("loan.ltv_pct", "<=", 90,
      only_when=cmp("valuation.method", "==", "calcasa"),
      expression="calcasa -> ltv_pct <= 90"),
  "Cap LTV at 90% when using Calcasa, or get a full valuation.",
  [ex("Calcasa 85%", {"valuation.method": "calcasa", "loan.ltv_pct": 85}, "pass", "Within 90%."),
   ex("Calcasa 100%", {"valuation.method": "calcasa", "loan.ltv_pct": 100}, "fail", "Exceeds 90% with Calcasa.")])

R("VAL-005", "Purchase price below market -> price is basis", "valuation", INFO, "Ch.8.4",
  "If the purchase price is below the appraised market value, the purchase price is the basis (value after renovation if applicable); tariff group uses appraised value.",
  manual("if koopsom < market value: use koopsom as basis."),
  "Use the purchase price as the financing basis.",
  [ex("Price below value", {"loan.purchase_price": 450000, "property.market_value": 470000}, "unknown", "Use purchase price.")], auto=False)

R("VAL-006", "Auction purchase uses appraised value", "valuation", INFO, "Ch.8.5",
  "For an auction purchase the appraised market value is the basis; surplus is held in a bouwdepot for quality improvement.",
  manual("auction: appraised value basis; surplus to bouwdepot."),
  "Hold surplus in a bouwdepot for improvements.",
  [ex("Auction buy", {"loan.auction_purchase": True}, "unknown", "Use appraised value.")], auto=False)

R("VAL-007", "Renovation value only from valuation", "valuation", INFO, "Ch.8.1.1",
  "Value after renovation is used only if it follows from a valuation report; otherwise the pre-renovation value applies, with funds held in a bouwdepot.",
  manual("post-renovation value only from valuation; else pre-renovation value."),
  "Provide a valuation stating the after-renovation value.",
  [ex("Renovation planned", {"loan.renovation": True}, "unknown", "Verify after-renovation value.")], auto=False)

# ============================================================ 9. Building deposit
R("DEP-001", "Bouwdepot pays only on proof of payment", "bouwdepot", NEVER, "Ch.9.2",
  "Funds are paid from the bouwdepot only against a valid proof of payment, never against quotes.",
  manual("bouwdepot payments only against invoices/receipts, not quotes."),
  "Submit invoices/receipts for bouwdepot payments.",
  [ex("Quote submitted", {"bouwdepot.proof_type": "quote"}, "unknown", "Quotes are not paid out.")], auto=False)

R("DEP-002", "Invoice not older than 6 months", "bouwdepot", BLOCK, "Ch.9.2",
  "An invoice/receipt may not be older than 6 months when submitted; for NHG it must be dated after the application date.",
  manual("invoice <=6 months old (NHG: after application date)."),
  "Submit invoices within 6 months.",
  [ex("4-month invoice", {"bouwdepot.invoice_age_months": 4}, "unknown", "Within 6 months.")], auto=False)

R("DEP-003", "Prepayments capped at EUR 5,000", "bouwdepot", BLOCK, "Ch.9.3",
  "Prepayments from a bouwdepot are capped at EUR 5,000 (kitchens/bathrooms: 15% of purchase, max EUR 5,000).",
  manual("prepayment <= EUR 5,000 (kitchens/bathrooms 15% max 5,000)."),
  "Cap prepayments at EUR 5,000.",
  [ex("Kitchen deposit", {"bouwdepot.prepayment": 4500}, "unknown", "Within cap.")], auto=False)

R("DEP-004", "Bouwdepot duration", "bouwdepot", INFO, "Ch.9.4",
  "Bouwdepot duration: 1 year for existing build (auto +1y), 2 years for new build (extendable by 1y).",
  manual("bouwdepot duration: existing 1y(+1), new build 2y(+1)."),
  "Track the bouwdepot term and remaining balance.",
  [ex("New build depot", {"property.is_new_build": True}, "unknown", "2-year duration.")], auto=False)

R("DEP-005", "No interest-rate change during bouwdepot", "bouwdepot", NEVER, "Ch.9.4.2",
  "The interest rate is not adjusted during the bouwdepot term.",
  manual("no rate change during bouwdepot term."),
  "Rate is fixed for the bouwdepot term.",
  [ex("Depot active", {"bouwdepot.active": True}, "unknown", "No rate change.")], auto=False)

R("DEP-006", "Leftover energy reservation must be repaid", "bouwdepot", INFO, "Ch.9.5",
  "Any remaining reserved energy-saving funds may not be reused and must be repaid on the mortgage.",
  manual("remaining energy reservation repaid, not reused."),
  "Repay leftover energy funds on the mortgage.",
  [ex("Energy funds left", {"bouwdepot.energy_remaining": 2000}, "unknown", "Repay on mortgage.")], auto=False)

R("DEP-007", "Interest-financing account max 2 years, separate part", "bouwdepot", NEVER, "Ch.9.6",
  "A rentefinancieringsrekening (new build only) lasts max 2 years and is always a separate loan part.",
  manual("rentefinancieringsrekening: <=2y, always separate loan part."),
  "Set up the interest-financing account as a separate loan part.",
  [ex("New build interest acct", {"bouwdepot.interest_account": True}, "unknown", "Separate loan part.")], auto=False)

# ============================================================ 10. The mortgage
R("LOAN-001", "Maximum total mortgage EUR 3,000,000", "loan", NEVER, "Ch.10.2",
  "The total mortgage may never exceed EUR 3,000,000 (bridging excluded).",
  cmp("loan.amount", "<=", 3000000, expression="loan.amount <= 3,000,000"),
  "Reduce the loan to at most EUR 3,000,000.",
  [ex("1.5M loan", {"loan.amount": 1500000}, "pass", "Within max."),
   ex("3.4M loan", {"loan.amount": 3400000}, "fail", "Exceeds EUR 3,000,000.")])

R("LOAN-002", "Term between 5 and 30 years", "loan", BLOCK, "Ch.10.3",
  "The mortgage term is minimum 5 and maximum 30 years (individual parts may be shorter).",
  {"all_of": [cmp("loan.term_years", ">=", 5), cmp("loan.term_years", "<=", 30)],
   "expression": "5 <= loan.term_years <= 30"},
  "Set the term within 5-30 years.",
  [ex("30 years", {"loan.term_years": 30}, "pass", "Within range."),
   ex("35 years", {"loan.term_years": 35}, "fail", "Exceeds 30 years.")])

R("LOAN-003", "Follow-up only behind own mortgage", "loan", NEVER, "Ch.10.4",
  "ASN never lends behind a mortgage that is not held at one of its brands.",
  cmp("loan.behind_external_mortgage", "is_false", expression="behind_external_mortgage == false"),
  "A follow-up requires an existing ASN-brand first mortgage.",
  [ex("First mortgage at ASN", {"loan.behind_external_mortgage": False}, "pass", "No external first mortgage."),
   ex("Behind external", {"loan.behind_external_mortgage": True}, "fail", "Cannot lend behind external mortgage.")])

R("LTV-001", "Maximum LTV 100% (regular)", "loan_to_value", BLOCK, "Ch.10.5",
  "A regular mortgage may not exceed 100% of market value unless the sustainability uplift applies.",
  cmp("loan.ltv_pct", "<=", 100,
      skip_when=cmp("loan.sustainability_financed", "is_true"),
      expression="ltv_pct <= 100 unless sustainability"),
  "Reduce to <=100% or qualify for the 106% uplift.",
  [ex("96%", {"loan.ltv_pct": 96, "loan.sustainability_financed": False}, "pass", "Within 100%."),
   ex("103% no sustainability", {"loan.ltv_pct": 103, "loan.sustainability_financed": False}, "fail", "Exceeds 100%.")])

R("LTV-002", "Maximum LTV 106% with sustainability", "loan_to_value", BLOCK, "Ch.10.5",
  "With sustainability measures the LTV may go up to 106% of market value.",
  cmp("loan.ltv_pct", "<=", 106,
      only_when=cmp("loan.sustainability_financed", "is_true"),
      expression="if sustainability: ltv_pct <= 106"),
  "Confirm the sustainability quotation; cap at 106%.",
  [ex("102.2% w/ measures", {"loan.ltv_pct": 102.2, "loan.sustainability_financed": True}, "pass", "Within 106%."),
   ex("109% w/ measures", {"loan.ltv_pct": 109, "loan.sustainability_financed": True}, "fail", "Exceeds 106%.")])

R("LTV-003", "Residual debt LTV up to 110%", "loan_to_value", INFO, "Ch.10.5",
  "When financing a residual debt the LTV may go up to 110%.",
  cmp("loan.ltv_pct", "<=", 110,
      only_when=cmp("loan.is_residual_debt", "is_true"),
      expression="if residual debt: ltv_pct <= 110"),
  "Residual-debt LTV is capped at 110%.",
  [ex("Residual 108%", {"loan.is_residual_debt": True, "loan.ltv_pct": 108}, "pass", "Within 110%.")])

R("LTV-004", "Loans over EUR 2,000,000 capped at 90% LTV", "loan_to_value", BLOCK, "Ch.10.5",
  "Mortgages above EUR 2,000,000 have a maximum LTV of 90%.",
  cmp("loan.ltv_pct", "<=", 90,
      only_when=cmp("loan.amount", ">", 2000000),
      expression="if amount > 2M: ltv_pct <= 90"),
  "Reduce LTV to <=90% for loans above EUR 2M.",
  [ex("2.5M at 85%", {"loan.amount": 2500000, "loan.ltv_pct": 85}, "pass", "Within 90%."),
   ex("2.5M at 95%", {"loan.amount": 2500000, "loan.ltv_pct": 95}, "fail", "Exceeds 90%.")],
  nhg="without_nhg_only")

R("LTV-005", "Interest-only portion max 50% of value", "loan_to_value", BLOCK, "Ch.10.5",
  "Interest-only loan parts are limited to 50% of market value (40% under maatwerk).",
  cmp("loan.interest_only_pct_of_value", "<=", 50, expression="interest_only_pct_of_value <= 50"),
  "Reduce the interest-only portion to <=50%.",
  [ex("40%", {"loan.interest_only_pct_of_value": 40}, "pass", "Within 50%."),
   ex("60%", {"loan.interest_only_pct_of_value": 60}, "fail", "Exceeds 50%.")])

R("LTV-006", "Consumer-purpose draw max 90% LTV", "loan_to_value", BLOCK, "Ch.10.8",
  "A consumer-purpose (consumptief) draw has a maximum LTV of 90% and must fit the standard norm.",
  cmp("loan.ltv_pct", "<=", 90,
      only_when=cmp("loan.consumer_purpose", "is_true"),
      expression="if consumer purpose: ltv_pct <= 90"),
  "Cap consumer-purpose draws at 90% LTV.",
  [ex("Consumer 85%", {"loan.consumer_purpose": True, "loan.ltv_pct": 85}, "pass", "Within 90%."),
   ex("Consumer 95%", {"loan.consumer_purpose": True, "loan.ltv_pct": 95}, "fail", "Exceeds 90%.")])

R("LOAN-004", "Bridging requires a first mortgage >= EUR 50,000", "loan", BLOCK, "Ch.10.6",
  "A bridging loan is offered only with a first mortgage of at least EUR 50,000.",
  cmp("loan.amount", ">=", 50000,
      only_when=cmp("loan.bridging", "is_true"),
      expression="if bridging: first mortgage >= 50,000"),
  "Ensure a qualifying first mortgage accompanies the bridge.",
  [ex("Bridge + 200k", {"loan.bridging": True, "loan.amount": 200000}, "pass", "Qualifying first mortgage."),
   ex("Bridge + 30k", {"loan.bridging": True, "loan.amount": 30000}, "fail", "First mortgage below 50,000.")])

R("LOAN-005", "Bridging term max 2 years", "loan", NEVER, "Ch.10.6.2",
  "A bridging loan has a maximum term of 2 years.",
  cmp("loan.bridging_term_years", "<=", 2,
      only_when=cmp("loan.bridging", "is_true"),
      expression="if bridging: bridging_term_years <= 2"),
  "Cap the bridging term at 2 years.",
  [ex("1-year bridge", {"loan.bridging": True, "loan.bridging_term_years": 1}, "pass", "Within 2 years."),
   ex("3-year bridge", {"loan.bridging": True, "loan.bridging_term_years": 3}, "fail", "Exceeds 2 years.")])

R("LOAN-006", "Bridging amount basis", "loan", INFO, "Ch.10.6.1",
  "Bridging amount is based on 99% of the sale price (definitively sold) or 95% of the appraised value (not yet sold).",
  manual("bridging: 99% of sale price if sold, else 95% of appraised value."),
  "Apply the correct bridging percentage.",
  [ex("Sold home", {"loan.bridging": True, "loan.old_home_sold": True}, "unknown", "Use 99% of sale price.")], auto=False)

R("LOAN-007", "Pure refinance LTV 100% (else 80%)", "loan", BLOCK, "Ch.10.7.1",
  "A pure refinance is allowed up to 100% of value if the annuity test charge fits the allowed burden; otherwise up to 80%.",
  manual("pure refinance: 100% if annuity charge fits; else 80%."),
  "Confirm the annuity charge fits, else cap at 80%.",
  [ex("Pure refinance", {"loan.pure_refinance": True}, "unknown", "Check burden fit.")], auto=False)

R("LOAN-008", "Refinance to NHG conditions", "loan", BLOCK, "Ch.10.7.2",
  "Refinancing from non-NHG to NHG requires >=10% extra linear/annuity repayment, or a renovation of >= EUR 2,500, or it being needed to keep the home.",
  manual("refinance to NHG: +10% repayment OR >=2,500 renovation OR home retention."),
  "Meet one of the refinance-to-NHG conditions.",
  [ex("Refinance to NHG", {"loan.refinance_to_nhg": True}, "unknown", "Verify a qualifying condition.")], auto=False)

R("LOAN-009", "No refinancing of business loans", "loan", NEVER, "Ch.10.8",
  "Refinancing a loan for business purposes is never allowed.",
  cmp("loan.refinances_business_loan", "is_false", expression="refinances_business_loan == false"),
  "Business-loan refinancing is not permitted.",
  [ex("Consumer refinance", {"loan.refinances_business_loan": False}, "pass", "Not a business loan."),
   ex("Business refinance", {"loan.refinances_business_loan": True}, "fail", "Business-loan refinancing not allowed.")])

R("LOAN-010", "Refinanced consumer credit repaid in <=10 years", "loan", BLOCK, "Ch.10.8",
  "Refinanced consumer credits must be repaid on annuity/linear basis within 10 years.",
  cmp("loan.refinanced_consumer_credit_term_years", "<=", 10,
      only_when=cmp("loan.refinanced_consumer_credit_term_years", "exists"),
      expression="refinanced consumer credit term <= 10"),
  "Set the refinanced consumer-credit term to <=10 years.",
  [ex("8-year term", {"loan.refinanced_consumer_credit_term_years": 8}, "pass", "Within 10 years."),
   ex("15-year term", {"loan.refinanced_consumer_credit_term_years": 15}, "fail", "Exceeds 10 years.")])

R("LOAN-011", "Bank guarantee only with our mortgage", "loan", INFO, "Ch.10.11",
  "A bank guarantee is issued only when the mortgage is taken out with us.",
  manual("bank guarantee only if mortgage is with us."),
  "Bank guarantee requires an ASN mortgage.",
  [ex("Guarantee request", {"loan.bank_guarantee_requested": True}, "unknown", "Only with our mortgage.")], auto=False)

R("LOAN-012", "Interest-only max 50% for existing customers", "loan", INFO, "Ch.10.8",
  "Existing customers may finance up to 50% interest-only if the post-financing LTV is <=50% (not for credit refinancing).",
  manual("existing customers: interest-only up to 50% if resulting LTV <= 50%."),
  "Verify the resulting LTV and customer tenure.",
  [ex("Existing customer", {"loan.existing_customer": True}, "unknown", "Verify LTV <=50%.")], auto=False)

# ============================================================ 11. Maatwerk
R("MW-001", "No maatwerk above EUR 1,250,000", "maatwerk", BLOCK, "Ch.11",
  "Maatwerk (deviation from the standard norm) is not possible for mortgages above EUR 1,250,000.",
  cmp("loan.amount", "<=", 1250000,
      only_when=cmp("loan.maatwerk", "is_true"),
      expression="if maatwerk: amount <= 1,250,000"),
  "Maatwerk is unavailable above EUR 1,250,000.",
  [ex("Maatwerk 900k", {"loan.maatwerk": True, "loan.amount": 900000}, "pass", "Within limit."),
   ex("Maatwerk 1.4M", {"loan.maatwerk": True, "loan.amount": 1400000}, "fail", "Above maatwerk limit.")])

R("MW-002", "Maatwerk interest-only max 40%", "maatwerk", BLOCK, "Ch.11.1",
  "Under maatwerk an interest-only loan part is allowed up to 40% of market value (50% in specific cases).",
  cmp("loan.interest_only_pct_of_value", "<=", 40,
      only_when=cmp("loan.maatwerk", "is_true"),
      expression="if maatwerk: interest_only_pct_of_value <= 40"),
  "Cap interest-only at 40% under maatwerk.",
  [ex("Maatwerk 35%", {"loan.maatwerk": True, "loan.interest_only_pct_of_value": 35}, "pass", "Within 40%."),
   ex("Maatwerk 48%", {"loan.maatwerk": True, "loan.interest_only_pct_of_value": 48}, "fail", "Exceeds 40%.")])

R("MW-003", "Robust stable income at LTV >= 80%", "maatwerk", BLOCK, "Ch.11.3",
  "When LTV >= 80%, at least 80% of test income must be fixed and stable; otherwise maatwerk is not possible.",
  cmp("income.fixed_stable_pct", ">=", 80,
      only_when=cmp("loan.ltv_pct", ">=", 80),
      expression="if ltv >= 80: fixed_stable_pct >= 80"),
  "Increase the share of fixed/stable income or reduce LTV.",
  [ex("90% fixed at LTV 85", {"loan.ltv_pct": 85, "income.fixed_stable_pct": 90}, "pass", "Robust income."),
   ex("60% fixed at LTV 85", {"loan.ltv_pct": 85, "income.fixed_stable_pct": 60}, "fail", "Insufficient fixed income at high LTV.")])

R("MW-004", "Maatwerk + joint-liability release min 12 months", "maatwerk", BLOCK, "Ch.11.2",
  "Maatwerk with release of joint liability is only possible if the current mortgage has run >=12 months at an ASN brand.",
  cmp("loan.months_at_asn", ">=", 12,
      only_when=cmp("loan.release_joint_liability", "is_true"),
      expression="if release joint liability: months_at_asn >= 12"),
  "Wait until the mortgage has run >=12 months at an ASN brand.",
  [ex("18 months", {"loan.release_joint_liability": True, "loan.months_at_asn": 18}, "pass", "Eligible."),
   ex("6 months", {"loan.release_joint_liability": True, "loan.months_at_asn": 6}, "fail", "Under 12 months.")])

R("MW-005", "Seniors AOW-gap fixed-rate period >= 10 years", "maatwerk", BLOCK, "Ch.11.4",
  "For seniors with an AOW gap tested on actual charges, the fixed-rate period must be at least 10 years (and last to the youngest applicant's AOW date).",
  cmp("loan.fixed_rate_period_years", ">=", 10,
      only_when=cmp("loan.senior_aow_gap", "is_true"),
      expression="if senior AOW gap: fixed_rate_period_years >= 10"),
  "Set the fixed-rate period to >=10 years for AOW-gap cases.",
  [ex("RVP 15y", {"loan.senior_aow_gap": True, "loan.fixed_rate_period_years": 15}, "pass", "Within rule."),
   ex("RVP 5y", {"loan.senior_aow_gap": True, "loan.fixed_rate_period_years": 5}, "fail", "Fixed-rate period too short.")])

R("MW-006", "Seniors buying another home: fixed-rate >= 20 years", "maatwerk", BLOCK, "Ch.11.5",
  "Seniors buying another home and tested on actual charges need a fixed-rate period of at least 20 years (max 80% LTV without NHG).",
  cmp("loan.fixed_rate_period_years", ">=", 20,
      only_when=cmp("loan.senior_new_home", "is_true"),
      expression="if senior new home: fixed_rate_period_years >= 20"),
  "Set the fixed-rate period to >=20 years.",
  [ex("RVP 20y", {"loan.senior_new_home": True, "loan.fixed_rate_period_years": 20}, "pass", "Within rule."),
   ex("RVP 10y", {"loan.senior_new_home": True, "loan.fixed_rate_period_years": 10}, "fail", "Fixed-rate period too short.")])

# ============================================================ 12-22. Changes
R("CHG-001", "Calcasa not allowed with maatwerk", "changes", BLOCK, "Ch.12.1",
  "A Calcasa desktop valuation is not allowed in combination with maatwerk.",
  manual("Calcasa not allowed with maatwerk."),
  "Use a validated NWWI valuation under maatwerk.",
  [ex("Maatwerk + Calcasa", {"loan.maatwerk": True, "valuation.method": "calcasa"}, "unknown", "Calcasa not allowed.")], auto=False)

R("CHG-002", "WOZ valuation only to lower tariff group", "changes", INFO, "Ch.12.1",
  "A WOZ valuation may be used only to lower the tariff group, up to 75% of WOZ value (85% of WOZ used as market value).",
  manual("WOZ valuation only for tariff-group lowering; up to 75% WOZ."),
  "Use WOZ only for tariff-group reductions.",
  [ex("Tariff request", {"valuation.method": "WOZ", "change.lower_tariff": True}, "unknown", "WOZ allowed for tariff lowering.")], auto=False)

R("CHG-003", "Late payments allow change rejection", "changes", WARN, "Ch.12.2",
  "If a customer has not paid on time (with us or elsewhere), a change request may be rejected and routed to Bijzonder Beheer.",
  cmp("change.payment_arrears", "is_false", expression="payment_arrears == false (else may reject)"),
  "Resolve arrears; Bijzonder Beheer assesses if active.",
  [ex("No arrears", {"change.payment_arrears": False}, "pass", "No arrears."),
   ex("Arrears present", {"change.payment_arrears": True}, "warning", "Change may be rejected.")])

R("CHG-004", "Switch to interest-only = new mortgage", "changes", BLOCK, "Ch.13.4",
  "Changing the repayment form to interest-only is treated as a new mortgage (full income and value testing).",
  manual("to interest-only -> full acceptance testing."),
  "Apply full acceptance rules for switches to interest-only.",
  [ex("To interest-only", {"change.to_interest_only": True}, "unknown", "Full testing required.")], auto=False)

R("CHG-005", "Joint-liability release conditions", "changes", BLOCK, "Ch.17.1",
  "A co-debtor can be released only if the remaining customer obtains full ownership, has 5 years of clean payments, and has sufficient income.",
  manual("release: full ownership + 5y clean payments + sufficient income."),
  "Verify ownership, payment history, and income.",
  [ex("Divorce buyout", {"change.release_joint_liability": True}, "unknown", "Verify release conditions.")], auto=False)

R("CHG-006", "NWWI valuation for joint-liability release", "changes", BLOCK, "Ch.17.2",
  "The value for a joint-liability release must come from a validated NWWI valuation (Calcasa only if the divorce settlement used it).",
  manual("joint-liability release value from NWWI taxatie (Calcasa only per settlement)."),
  "Provide a validated NWWI valuation.",
  [ex("Release valuation", {"change.release_joint_liability": True}, "unknown", "NWWI valuation required.")], auto=False)

R("CHG-007", "New debtor equal share, no arrears", "changes", BLOCK, "Ch.17.3",
  "A new partner joining as owner/debtor must take an equal ownership share and have no payment arrears.",
  manual("new debtor: equal share + no arrears + KYC."),
  "Verify equal share and clean credit for the new debtor.",
  [ex("New partner added", {"change.new_debtor": True}, "unknown", "Verify share and credit.")], auto=False)

R("CHG-008", "Surviving partner affordability", "changes", BLOCK, "Ch.18.1",
  "If the surviving partner stays in the home, the mortgage may continue if that partner can afford the monthly charges.",
  manual("surviving partner must afford the monthly charges."),
  "Test the surviving partner's affordability.",
  [ex("Partner stays", {"change.surviving_partner": True}, "unknown", "Affordability test required.")], auto=False)

R("CHG-009", "Heir takeover = full testing", "changes", BLOCK, "Ch.18.2",
  "An heir taking over the home from other heirs is fully tested on income and value (with KYC).",
  manual("heir takeover -> full acceptance testing + KYC."),
  "Apply full acceptance rules to heir takeovers.",
  [ex("Heir buyout", {"change.heir_takeover": True}, "unknown", "Full testing required.")], auto=False)

R("CHG-010", "Repay within 1 year of death without penalty", "changes", INFO, "Ch.18.3",
  "On death of the debtor/cohabiting partner, the mortgage may be (partly) repaid within 1 year without an early-repayment penalty.",
  manual("repayment within 1 year of death is penalty-free."),
  "Allow penalty-free repayment within 1 year of death.",
  [ex("Death of debtor", {"change.death_event": True}, "unknown", "Penalty-free within 1 year.")], auto=False)

R("CHG-011", "End-date refinance interest-only <= 50%", "changes", INFO, "Ch.19",
  "At the mortgage end date a new mortgage may finance up to 50% interest-only even outside the standard norm (absolute amount may not grow).",
  manual("end-date refinance: interest-only <= 50%; absolute amount not larger."),
  "Cap interest-only at 50% on end-date refinance.",
  [ex("End-date refinance", {"change.end_date_refinance": True}, "unknown", "Interest-only <=50%.")], auto=False)

R("CHG-012", "Bridging extension only for existing build", "changes", BLOCK, "Ch.19.3",
  "A bridging loan for new build (2y) cannot be extended; existing build (1y) can be extended by max 1 year under conditions.",
  manual("new-build bridge not extendable; existing-build +1y under conditions."),
  "Verify build type and extension conditions.",
  [ex("Bridge extension", {"change.bridging_extension": True}, "unknown", "Verify extension eligibility.")], auto=False)

R("CHG-013", "Belgium mortgage replacement max 25 years", "changes", BLOCK, "Ch.19.4",
  "For the legacy Belgium mortgage, a replacement loan must be fully amortising with a max term of 25 years.",
  manual("Belgium mortgage replacement: fully amortising, term <= 25 years."),
  "Structure a fully amortising loan within 25 years.",
  [ex("Belgium legacy", {"change.belgium_mortgage": True}, "unknown", "Max 25-year amortising loan.")], auto=False)

R("CHG-014", "No permanent rental of the home", "changes", NEVER, "Ch.20",
  "The home may not be rented out permanently; only temporary (Leegstandswet) or temporary recreational rental is allowed.",
  cmp("change.permanent_rental", "is_false", expression="permanent_rental == false"),
  "Permanent rental is not allowed; obtain consent for temporary rental.",
  [ex("Owner-occupied", {"change.permanent_rental": False}, "pass", "Not permanently rented."),
   ex("Permanent rental", {"change.permanent_rental": True}, "fail", "Permanent rental not allowed.")])

R("CHG-015", "Temporary recreational rental limits", "changes", BLOCK, "Ch.20.2",
  "Temporary recreational rental needs prior written consent: home remains main residence, <=60 days/year, never >4 weeks consecutively, with suitable insurance.",
  cmp("change.recreational_rental_days", "<=", 60,
      only_when=cmp("change.recreational_rental", "is_true"),
      expression="if recreational rental: days <= 60/year"),
  "Limit recreational rental to <=60 days/year with consent.",
  [ex("40 days", {"change.recreational_rental": True, "change.recreational_rental_days": 40}, "pass", "Within limit."),
   ex("90 days", {"change.recreational_rental": True, "change.recreational_rental_days": 90}, "fail", "Exceeds 60 days.")])

R("CHG-016", "Second charge requires risk assessment", "changes", WARN, "Ch.21.1",
  "Allowing a second mortgage charge behind ours requires a risk assessment including a BKR check; it may be refused.",
  manual("second charge: risk assessment + BKR check; may refuse."),
  "Perform a risk assessment for the second charge.",
  [ex("Second charge request", {"change.second_charge": True}, "unknown", "Risk assessment required.")], auto=False)

R("CHG-017", "Partial release valuation thresholds", "changes", INFO, "Ch.21.2",
  "Partial release: <5 m2 needs no income/value test; 5 m2-10% may use Calcasa if LTV<90%; larger needs an NWWI report before/after.",
  manual("partial release thresholds: <5m2 none; <10% Calcasa if LTV<90%; else NWWI."),
  "Apply the partial-release thresholds.",
  [ex("Garden strip", {"change.partial_release_m2": 3}, "unknown", "No test for <5 m2.")], auto=False)

R("CHG-018", "Cooperative to apartment-right conversion", "changes", INFO, "Ch.21.3",
  "Converting cooperative ownership to an apartment right is accepted without retesting only if the mortgage is not increased/changed.",
  manual("coop->apartment right: no retest if no increase/change."),
  "Confirm no mortgage increase accompanies the conversion.",
  [ex("Conversion request", {"change.coop_to_apartment": True}, "unknown", "No retest if unchanged.")], auto=False)

R("CHG-019", "Lower repayment target retesting", "changes", BLOCK, "Ch.13.1",
  "Lowering the repayment target requires income and value testing per the acceptance rules.",
  manual("lowering repayment target -> income + value testing."),
  "Apply acceptance testing for a lower repayment target.",
  [ex("Lower target", {"change.lower_repayment_target": True}, "unknown", "Testing required.")], auto=False)

R("CHG-020", "Penalty-free repayment on sale", "changes", INFO, "Ch.14.1",
  "Selling the home and repaying from the proceeds is penalty-free, unless the customer chose the 'penalty on moving' budget option.",
  manual("sale repayment penalty-free unless 'boete bij verhuizen' chosen."),
  "Check the budget-option election for penalties.",
  [ex("Sells home", {"change.sale_repayment": True}, "unknown", "Usually penalty-free.")], auto=False)

# ============================================================ Documents
R("DOC-001", "Valid identification provided", "documents", NEVER, "Ch.2.6",
  "A valid identity document is required for every applicant (Wwft).",
  cmp("applicant.id_document_valid", "is_true", expression="id_document_valid == true"),
  "Provide a valid passport/ID card for every applicant.",
  [ex("Valid ID", {"applicant.id_document_valid": True}, "pass", "Valid ID."),
   ex("No ID", {"applicant.id_document_valid": False}, "fail", "No valid ID.")])

R("DOC-002", "Employer's statement for salaried income", "documents", BLOCK, "Stukkenlijst/Ch.3",
  "A werkgeversverklaring is required for salaried applicants.",
  cmp("documents", "contains", "werkgeversverklaring", expression="'werkgeversverklaring' in documents"),
  "Provide the employer's statement for each salaried applicant.",
  [ex("Provided", {"documents": ["werkgeversverklaring", "loonstrook"]}, "pass", "Statement provided."),
   ex("Missing", {"documents": ["loonstrook"]}, "fail", "Statement missing.")])

R("DOC-003", "Salary slips provided", "documents", BLOCK, "Stukkenlijst/Ch.3",
  "Recent salary slips (loonstrook) are required for salaried income.",
  cmp("documents", "contains", "loonstrook", expression="'loonstrook' in documents"),
  "Provide recent salary slips.",
  [ex("Slip present", {"documents": ["loonstrook"]}, "pass", "Slips provided."),
   ex("No slip", {"documents": ["werkgeversverklaring"]}, "fail", "Salary slips missing.")])

R("DOC-004", "UWV report for short/temporary employment", "documents", WARN, "Stukkenlijst/Ch.3.7",
  "A UWV-verzekeringsbericht is required for employment <3 months, a second job, or a temporary contract.",
  {"for_each": "income.applicants",
   "when": {"any_of": [cmp("type", "==", "temporary"), cmp("months_at_employer", "<", 3)]},
   "require": cmp("documents", "contains", "uwv_verzekeringsbericht", scope="root"),
   "expression": "temporary/<3-month -> 'uwv_verzekeringsbericht' in documents"},
  "Request the UWV-verzekeringsbericht.",
  [ex("Temp + UWV", {"income.applicants": [{"type": "temporary", "months_at_employer": 27}], "documents": ["uwv_verzekeringsbericht"]}, "pass", "UWV present."),
   ex("Temp, no UWV", {"income.applicants": [{"type": "temporary", "months_at_employer": 27}], "documents": ["werkgeversverklaring"]}, "warning", "UWV outstanding.")])

R("DOC-005", "Property valuation provided", "documents", BLOCK, "Ch.8",
  "A valuation (validated taxatierapport, or Calcasa where allowed) is required.",
  cmp("documents", "contains_any", ["taxatierapport", "calcasa_desktop_taxatie", "woz_taxatieverslag"],
      expression="documents contains a valuation"),
  "Provide a validated valuation report.",
  [ex("Taxatie", {"documents": ["taxatierapport"]}, "pass", "Valuation provided."),
   ex("None", {"documents": ["koopovereenkomst"]}, "fail", "No valuation.")])

R("DOC-006", "Income verification complete (jaaropgave)", "documents", WARN, "Stukkenlijst/Ch.3",
  "Income verification needs salary slips and the annual statement (jaaropgave).",
  cmp("documents", "contains_all", ["loonstrook", "jaaropgave"],
      expression="documents contains loonstrook AND jaaropgave"),
  "Request the missing income documents (jaaropgave / tax returns).",
  [ex("Both present", {"documents": ["loonstrook", "jaaropgave"]}, "pass", "Income docs complete."),
   ex("Jaaropgave missing", {"documents": ["loonstrook"]}, "warning", "Jaaropgave outstanding.")])

R("DOC-007", "Purchase agreement provided", "documents", BLOCK, "Stukkenlijst",
  "A signed purchase agreement (koopovereenkomst) is required for a purchase.",
  cmp("documents", "contains", "koopovereenkomst",
      skip_when=cmp("loan.purpose", "in", ["refinance", "oversluiten"]),
      expression="'koopovereenkomst' in documents (for purchases)"),
  "Provide the signed purchase agreement.",
  [ex("Provided", {"documents": ["koopovereenkomst"], "loan.purpose": "primary residence purchase"}, "pass", "Agreement provided."),
   ex("Missing", {"documents": ["taxatierapport"], "loan.purpose": "primary residence purchase"}, "fail", "Purchase agreement missing.")])

R("DOC-008", "Bank statements provided", "documents", WARN, "Stukkenlijst",
  "Recent bank statements are required to assess the financial situation.",
  cmp("documents", "contains", "bank_statements", expression="'bank_statements' in documents"),
  "Provide recent bank statements.",
  [ex("Provided", {"documents": ["bank_statements"]}, "pass", "Statements provided."),
   ex("Missing", {"documents": ["loonstrook"]}, "warning", "Bank statements outstanding.")])

R("DOC-009", "Self-employed annual figures provided", "documents", BLOCK, "Ch.4",
  "Self-employed applicants must provide annual figures / tax returns to establish income.",
  cmp("documents", "contains_any", ["annual_accounts", "tax_returns", "jaarrapport"],
      only_when=cmp("self_employed.years_active", "exists"),
      expression="self-employed -> annual figures in documents"),
  "Provide annual accounts / tax returns.",
  [ex("Accounts present", {"self_employed.years_active": 5, "documents": ["jaarrapport"]}, "pass", "Figures provided."),
   ex("Missing", {"self_employed.years_active": 5, "documents": ["loonstrook"]}, "fail", "Annual figures missing.")])

R("DOC-010", "Energy/sustainability quotation for 106% uplift", "documents", WARN, "ASN Duurzaam Wonen",
  "When the sustainability uplift is used, an energy label and sustainability quotation must support the extra amount.",
  cmp("documents", "contains_any", ["energy_label", "sustainability_quotation"],
      only_when=cmp("loan.sustainability_financed", "is_true"),
      expression="sustainability -> energy/sustainability quotation in documents"),
  "Provide the sustainability quotation/energy label.",
  [ex("Label present", {"loan.sustainability_financed": True, "documents": ["energy_label"]}, "pass", "Quotation present."),
   ex("Missing", {"loan.sustainability_financed": True, "documents": ["loonstrook"]}, "warning", "Sustainability quotation outstanding.")])

R("CREDIT-001", "Credit score proxy threshold (optional)", "credit", INFO, "Pipeline proxy",
  "Optional FICO-style score gate for pipelines supplying a numeric score; NL practice relies on BKR.",
  cmp("credit_score", ">=", 680,
      skip_when=cmp("credit_score", "not_exists"),
      expression="credit_score >= 680 (if supplied)"),
  "If a numeric score is low, rely on the BKR assessment.",
  [ex("690", {"credit_score": 690}, "pass", "Above threshold."),
   ex("660", {"credit_score": 660}, "info", "Below proxy threshold.")])


def main() -> None:
    doc = {
        "schema_version": "1.1",
        "ruleset_id": "asn_mortgage_acceptance",
        "ruleset_name": "ASN Bank mortgage acceptance rules (machine-readable)",
        "generated_date": "2026-06-22",
        "rule_count": len(rules),
        "source": {
            "title": "Regels voor het accepteren, verstrekken en wijzigen van een hypotheek",
            "issuer": "ASN Bank NV",
            "version_date": "2025-07-01",
            "disclaimer": "SYNTHETIC / SUMMARISED for pipeline testing. Derived from public ASN documentation. Not legal or financial advice. Verify against the live ASN ruleset and NHG norms before any real use.",
        },
        "usage": {
            "description": "Each rule has a machine-evaluable `check` (when `auto_evaluable` is true) plus pass/fail `examples`. An agent maps the parsed application JSON to field paths, evaluates each rule, and emits a finding.",
            "finding_output_contract": {
                "rule_id": "string",
                "rule_name": "string",
                "status": "one of status_values",
                "evidence": "string",
                "remediation": "string",
            },
            "status_values": ["pass", "fail", "warning", "unknown"],
            "severity_values": {
                "blocking_never_deviate": "Hard stop; ASN never deviates. A fail rejects the application.",
                "blocking": "Must pass; exceptions only via individual maatwerk review.",
                "warning": "Does not block but needs attention / extra documentation.",
                "info": "Informational threshold; surface for the adviser.",
            },
            "operators": ["==", "!=", "<", "<=", ">", ">=", "in", "not_in", "contains",
                          "not_contains", "contains_any", "contains_all", "not_contains_any",
                          "exists", "not_exists", "is_true", "is_false"],
            "nhg_scope": {
                "both": "Applies with and without NHG.",
                "with_nhg_only": "Only when NHG is requested.",
                "without_nhg_only": "Only when NHG is not requested.",
            },
            "check_shapes": [
                "leaf: {field, operator, value|value_field}",
                "composite: {all_of:[...]} or {any_of:[...]}",
                "for_each: {for_each, when?, require}",
                "aggregate: {field, operator, value, aggregate:'max'}",
                "manual_review: {type:'manual_review', expression}",
                "gating: any check may add only_when/skip_when/stage",
            ],
        },
        "categories": sorted({r["category"] for r in rules}),
        "rules": rules,
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rules)} rules to {OUT}")


if __name__ == "__main__":
    main()
