"""
Generate a sample ASN mortgage application *submission pack* as a PDF.

This produces a realistic, multi-document pack of the kind an applicant (and their
adviser) would submit for an ASN Bank mortgage. It is intended as test input for the
mortgage review pipeline in ``examples/mortgage_agents.py`` (the Application Parser
expects PDF text / OCR output, which this file emulates).

The scenario intentionally contains a few issues (a borderline loan-to-value, a
temporary employment contract, a student debt, and some missing documents) so the
Rule Validator has something meaningful to flag.

Usage (from project root):

    pip install fpdf2
    python examples/sample_data/generate_submission_pack.py

Output:
    examples/sample_data/asn_mortgage_submission_pack.pdf
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fpdf import FPDF

OUTPUT_PATH = Path(__file__).resolve().parent / "asn_mortgage_submission_pack.pdf"

# ASN core fonts (Helvetica) use latin-1, which has no euro glyph. Use "EUR" text.
EUR = "EUR "

NAVY = (15, 40, 90)
GREY = (90, 90, 90)
LIGHT = (235, 238, 245)


class SubmissionPack(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*NAVY)
        self.cell(0, 8, "ASN Bank - Mortgage Application Submission Pack", align="L")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 8, f"Ref: ASN-2026-008814   Page {self.page_no()}", align="R")
        self.ln(10)
        self.set_draw_color(*LIGHT)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GREY)
        self.multi_cell(
            0,
            4,
            "SAMPLE / SYNTHETIC DOCUMENT - generated for testing the mortgage review "
            "pipeline. Not a real application and not financial advice.",
            align="C",
        )

    # ---- helpers ---------------------------------------------------------
    def section_title(self, text: str) -> None:
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(2)
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"  {text}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def field_row(self, label: str, value: str) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*GREY)
        self.cell(62, 6, label)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def kv_table(self, rows: list[tuple[str, str]]) -> None:
        for label, value in rows:
            self.field_row(label, value)
        self.ln(1)

    def checklist(self, items: list[tuple[str, bool]]) -> None:
        for label, provided in items:
            self.set_font("Helvetica", "B", 10)
            if provided:
                self.set_text_color(20, 120, 40)
                mark = "[X] "
            else:
                self.set_text_color(190, 30, 30)
                mark = "[ ] "
            self.cell(8, 6, mark)
            self.set_text_color(0, 0, 0)
            self.set_font("Helvetica", "", 9)
            self.multi_cell(0, 6, label, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body(self, text: str) -> None:
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def note(self, text: str) -> None:
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY)
        self.multi_cell(0, 4.5, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)


def build() -> SubmissionPack:
    pdf = SubmissionPack(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 16, 18)

    # ---------------- Cover page ----------------
    pdf.add_page()
    pdf.ln(20)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 14, "ASN Bank", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Mortgage Application Submission Pack", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.w - pdf.r_margin, pdf.get_y() + 2)
    pdf.ln(14)
    pdf.set_line_width(0.2)

    pdf.set_text_color(0, 0, 0)
    pdf.kv_table(
        [
            ("Application reference:", "ASN-2026-008814"),
            ("Product:", "ASN Hypotheek (with ASN Duurzaam Wonen)"),
            ("NHG requested:", "Yes (Nationale Hypotheek Garantie)"),
            ("Submission date:", date(2026, 6, 22).strftime("%d %B %Y")),
            ("Adviser:", "M. Jansen - Onafhankelijk Hypotheekadvies B.V."),
            ("Applicant:", "Daan Bakker"),
            ("Co-applicant:", "Sophie de Vries"),
            ("Property:", "Lijsterstraat 14, 3514 AB Utrecht"),
        ]
    )
    pdf.ln(6)
    pdf.set_fill_color(*LIGHT)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 8, "  Contents of this pack", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    for i, item in enumerate(
        [
            "Document checklist (stukkenlijst)",
            "1. Mortgage application form (aanvraagformulier)",
            "2. Identification details",
            "3. Employer's statement (werkgeversverklaring) & intention statement",
            "4. Salary / income summary (loonstrook)",
            "5. Bank account & assets summary",
            "6. Existing obligations & BKR overview",
            "7. Property valuation (taxatie) & purchase agreement",
            "8. Affordability summary (betaalbaarheid)",
            "9. Applicant declaration & signatures",
        ],
        start=1,
    ):
        pdf.cell(0, 6, item, new_x="LMARGIN", new_y="NEXT")

    # ---------------- Checklist ----------------
    pdf.add_page()
    pdf.section_title("Document Checklist (stukkenlijst)")
    pdf.body(
        "Overview of documents required by ASN Bank to assess this application. "
        "Items marked [X] are enclosed in this pack; items marked [ ] are still "
        "outstanding and must be supplied before a binding offer can be issued."
    )
    pdf.checklist(
        [
            ("Valid identification for both applicants (passport / ID card)", True),
            ("Werkgeversverklaring (employer's statement) - applicant", True),
            ("Werkgeversverklaring (employer's statement) - co-applicant", True),
            ("Intention statement (intentieverklaring) - co-applicant temporary contract", True),
            ("UWV-verzekeringsbericht (employment history) - co-applicant", False),
            ("Recent salary slips (loonstrook) - both applicants", True),
            ("Bank statements (last 3 months)", True),
            ("Purchase agreement (koopovereenkomst)", True),
            ("Property valuation report (taxatierapport)", True),
            ("Energy label / sustainability quotation (verduurzaming)", True),
            ("BKR credit overview", True),
            ("Most recent annual income statement / jaaropgave", False),
            ("Proof of own funds (eigen middelen) for costs", True),
        ]
    )

    # ---------------- 1. Application form ----------------
    pdf.section_title("1. Mortgage Application Form (aanvraagformulier)")

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, "Applicant", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.kv_table(
        [
            ("Full name:", "Daan Bakker"),
            ("Date of birth:", "12 March 1990 (age 36)"),
            ("Nationality:", "Dutch"),
            ("Marital status:", "Registered partnership"),
            ("Current address:", "Kanaalweg 88-2, 3533 HH Utrecht"),
            ("Phone / email:", "+31 6 1234 5678 / daan.bakker@example.nl"),
        ]
    )

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, "Co-applicant", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.kv_table(
        [
            ("Full name:", "Sophie de Vries"),
            ("Date of birth:", "5 July 1992 (age 33)"),
            ("Nationality:", "Dutch"),
            ("Relationship:", "Registered partner (co-owner, 50/50)"),
        ]
    )

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, "Loan request", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.kv_table(
        [
            ("Loan purpose:", "Purchase of primary residence (own occupancy)"),
            ("Requested loan amount:", f"{EUR}465,000"),
            ("  of which sustainability (verduurzaming):", f"{EUR}18,000 (solar panels + insulation)"),
            ("Purchase price:", f"{EUR}450,000"),
            ("Appraised market value (taxatie):", f"{EUR}455,000"),
            ("Repayment type:", "Annuity (annuiteiten), 30 years"),
            ("Requested fixed-rate period:", "20 years"),
            ("Occupancy:", "Primary residence (owner-occupied)"),
        ]
    )

    # ---------------- 2. Identification ----------------
    pdf.section_title("2. Identification Details")
    pdf.kv_table(
        [
            ("Applicant document:", "Dutch passport NX1234567, valid to 2030-04-18"),
            ("Co-applicant document:", "Dutch ID card IK7654321, valid to 2029-11-02"),
            ("BSN provided:", "On signing of the offer (privacy - not in this pack)"),
            ("Identification by:", "Adviser (in person) and notary at transfer"),
        ]
    )

    # ---------------- 3. Employer's statement ----------------
    pdf.section_title("3. Employer's Statement (werkgeversverklaring)")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, "Applicant - Daan Bakker", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.kv_table(
        [
            ("Employer:", "TechNova Solutions B.V., Utrecht"),
            ("Position:", "Senior Software Engineer"),
            ("Contract type:", "Permanent (onbepaalde tijd), probation passed"),
            ("In service since:", "1 September 2019"),
            ("Gross annual salary:", f"{EUR}68,400 incl. holiday allowance"),
            ("Structural 13th month:", f"{EUR}5,700"),
        ]
    )
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, "Co-applicant - Sophie de Vries", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.kv_table(
        [
            ("Employer:", "BrightMedia Agency B.V., Amsterdam"),
            ("Position:", "Marketing Specialist"),
            ("Contract type:", "Temporary (bepaalde tijd), ends 2027-02-28"),
            ("In service since:", "1 March 2024"),
            ("Gross annual salary:", f"{EUR}42,000 incl. holiday allowance"),
            (
                "Intention statement:",
                "Provided - employer intends to offer a permanent contract "
                "subject to unchanged performance.",
            ),
        ]
    )
    pdf.note(
        "Note for assessor: co-applicant has a temporary contract with an intention "
        "statement (intentieverklaring). The UWV-verzekeringsbericht confirming "
        "employment history is still outstanding."
    )

    # ---------------- 4. Income summary ----------------
    pdf.section_title("4. Salary / Income Summary (loonstrook)")
    pdf.kv_table(
        [
            ("Applicant gross monthly:", f"{EUR}5,700"),
            ("Co-applicant gross monthly:", f"{EUR}3,500"),
            ("Combined gross monthly income:", f"{EUR}9,200"),
            ("Combined gross annual (toetsinkomen):", f"{EUR}110,400"),
            ("Income paid into:", "Dutch bank account (NL)"),
            ("Latest salary slips:", "May 2026 enclosed for both applicants"),
            ("Jaaropgave (annual statement):", "OUTSTANDING - to follow"),
        ]
    )

    # ---------------- 5. Assets ----------------
    pdf.section_title("5. Bank Account & Assets Summary")
    pdf.kv_table(
        [
            ("Joint savings (ASN spaarrekening):", f"{EUR}46,000"),
            ("Applicant checking (betaalrekening):", f"{EUR}8,200"),
            ("Co-applicant checking:", f"{EUR}3,100"),
            ("Total own funds available:", f"{EUR}57,300"),
            ("Funds earmarked for purchase costs:", f"{EUR}22,000 (k.k. - kosten koper)"),
            ("Gift / family loan (schenking):", "None"),
        ]
    )

    # ---------------- 6. Obligations / BKR ----------------
    pdf.section_title("6. Existing Obligations & BKR Overview")
    pdf.kv_table(
        [
            ("DUO student debt (applicant):", f"{EUR}9,800 remaining, monthly {EUR}62"),
            ("Personal loan (co-applicant):", f"{EUR}6,500 remaining, monthly {EUR}145"),
            ("Credit cards / overdraft:", "None active"),
            ("BKR registrations:", "1 x RK (revolving) - on time, no arrears codes"),
            ("BKR special codes (A/H/1-5):", "None"),
            ("Number of registered contracts:", "2"),
        ]
    )
    pdf.note(
        "Equivalent 'credit score' proxy for the pipeline: 690 (no negative BKR codings; "
        "two active contracts in good standing)."
    )

    # ---------------- 7. Property / valuation ----------------
    pdf.section_title("7. Property Valuation (taxatie) & Purchase Agreement")
    pdf.kv_table(
        [
            ("Property address:", "Lijsterstraat 14, 3514 AB Utrecht"),
            ("Property type:", "Terraced family home (eengezinswoning), existing build"),
            ("Year built:", "1998"),
            ("Energy label:", "C (improving to A after planned measures)"),
            ("Purchase price (koopsom):", f"{EUR}450,000"),
            ("Appraised market value:", f"{EUR}455,000"),
            ("Valuation type:", "Full valuation report (NWWI-validated taxatie)"),
            ("Purchase agreement signed:", "9 June 2026 (subject to financing)"),
            ("Transfer date (notary):", "1 September 2026 (planned)"),
        ]
    )

    # ---------------- 8. Affordability ----------------
    pdf.section_title("8. Affordability Summary (betaalbaarheid)")
    pdf.kv_table(
        [
            ("Loan amount:", f"{EUR}465,000"),
            ("Market value:", f"{EUR}455,000"),
            ("Loan-to-value (schuld-marktwaarde):", "102.2% (incl. EUR 18,000 verduurzaming)"),
            ("Max LTV - regular:", "100%"),
            ("Max LTV - incl. sustainability:", "106%"),
            ("Combined gross monthly income:", f"{EUR}9,200"),
            ("Monthly obligations (debts):", f"{EUR}207 (student + personal loan)"),
            ("Estimated monthly mortgage payment:", f"{EUR}2,050 (annuity, test rate)"),
            ("Debt-to-income (indicative):", "approx. 30%"),
            ("Test method:", "Annuity over 30 years per Trhk / NIBUD norms"),
        ]
    )
    pdf.note(
        "Assessor flags to review: (a) LTV above 100% relies on the verduurzaming "
        "uplift to 106% - confirm sustainability quotation; (b) co-applicant on a "
        "temporary contract - rely on intention statement; (c) UWV-verzekeringsbericht "
        "and jaaropgave still outstanding."
    )

    # ---------------- 9. Declaration ----------------
    pdf.section_title("9. Applicant Declaration & Signatures")
    pdf.body(
        "We declare that the information provided in this submission pack is complete and "
        "correct to the best of our knowledge. We authorise ASN Bank to verify the data, "
        "including a BKR credit check and screening against fraud registers, in line with "
        "ASN Bank's acceptance rules and applicable law (Wft, Wwft, Trhk, GHF)."
    )
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(90, 6, "Applicant: Daan Bakker")
    pdf.cell(0, 6, "Co-applicant: Sophie de Vries", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(90, 6, "Signature: ___________________")
    pdf.cell(0, 6, "Signature: ___________________", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(90, 6, f"Date: {date(2026, 6, 22).strftime('%d-%m-%Y')}")
    pdf.cell(0, 6, f"Date: {date(2026, 6, 22).strftime('%d-%m-%Y')}", new_x="LMARGIN", new_y="NEXT")

    return pdf


def main() -> None:
    pdf = build()
    pdf.output(str(OUTPUT_PATH))
    print(f"Wrote submission pack: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
