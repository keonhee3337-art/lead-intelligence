"""
Excel Export — Project B: Lead Intelligence

Exports full pipeline results to Excel with two sheets:
  - Rankings: financial + GEO scores overview
  - Outreach: generated email content
"""

import os
import pandas as pd
from pathlib import Path


def export_to_excel(
    companies: list[dict],
    output_path: str = "output/lead_intelligence_report.xlsx",
) -> str:
    """
    Exports to Excel with two sheets.

    Sheet 1 "Rankings":
      corp_name | readiness_score | geo_score | revenue_bn_krw | operating_margin | website_url

    Sheet 2 "Outreach":
      corp_name | email_subject | email_body | email_score

    Returns the output_path string.
    """
    # Resolve path relative to this file's directory
    output_file = Path(__file__).parent / output_path
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # --- Sheet 1: Rankings ---
    rankings_rows = []
    for c in companies:
        rankings_rows.append({
            "corp_name": c.get("corp_name", ""),
            "readiness_score": c.get("readiness_score"),
            "geo_score": c.get("geo_score"),
            "revenue_bn_krw": c.get("revenue_bn_krw"),
            "operating_margin_pct": c.get("operating_margin_pct"),
            "website_url": c.get("website_url", ""),
        })
    df_rankings = pd.DataFrame(rankings_rows)

    # Sort by geo_score desc (if available), then readiness_score
    sort_cols = []
    if "geo_score" in df_rankings.columns and df_rankings["geo_score"].notna().any():
        sort_cols.append("geo_score")
    if "readiness_score" in df_rankings.columns and df_rankings["readiness_score"].notna().any():
        sort_cols.append("readiness_score")
    if sort_cols:
        df_rankings = df_rankings.sort_values(sort_cols, ascending=False).reset_index(drop=True)

    # --- Sheet 2: Outreach ---
    outreach_rows = []
    for c in companies:
        outreach_rows.append({
            "corp_name": c.get("corp_name", ""),
            "email_subject": c.get("email_subject", ""),
            "email_body": c.get("email_body", ""),
            "email_score": c.get("email_score"),
        })
    df_outreach = pd.DataFrame(outreach_rows)

    # Write to Excel
    with pd.ExcelWriter(str(output_file), engine="openpyxl") as writer:
        df_rankings.to_excel(writer, sheet_name="Rankings", index=False)
        df_outreach.to_excel(writer, sheet_name="Outreach", index=False)

        # Auto-adjust column widths for Rankings sheet
        ws_rankings = writer.sheets["Rankings"]
        for col in ws_rankings.columns:
            max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
            ws_rankings.column_dimensions[col[0].column_letter].width = min(max_len + 4, 50)

        # For Outreach sheet — wider email_body column
        ws_outreach = writer.sheets["Outreach"]
        for col in ws_outreach.columns:
            header = col[0].value
            if header == "email_body":
                ws_outreach.column_dimensions[col[0].column_letter].width = 80
            else:
                max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
                ws_outreach.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

        # Wrap text in email_body cells
        from openpyxl.styles import Alignment
        for row in ws_outreach.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    print(f"Excel report saved: {output_file}")
    return str(output_file)


if __name__ == "__main__":
    # Test with 3 fake company dicts with all pipeline fields
    fake_companies = [
        {
            "corp_code": "000001",
            "corp_name": "테스트제조A",
            "revenue_bn_krw": 320.0,
            "operating_profit_bn_krw": 48.0,
            "operating_margin_pct": 15.0,
            "year": 2024,
            "financials_history": [],
            "readiness_score": 72.5,
            "score_breakdown": {
                "financial_health": 22.5,
                "growth_trajectory": 25.0,
                "size_signal": 10.0,
                "dart_disclosure": 15.0,
            },
            "geo_score": 65,
            "geo_breakdown": {
                "citability": 28,
                "crawler_access": 25,
                "brand_mention": 12,
            },
            "website_url": "https://www.testa.co.kr",
            "email_subject": "[테스트제조A] AI 경쟁력 진단 — 귀사의 AI 가시성 점수는 65점입니다",
            "email_body": "안녕하세요. SDC(SKKU-Deloitte Consulting) 회장 김건희입니다.\n귀사의 AI 가시성 점수는 65/100점으로 분석되었습니다.\n무료 진단 보고서를 제공해 드리고 싶습니다. 회신 부탁드립니다.\n\n김건희 | SDC (SKKU-Deloitte Consulting) 회장",
            "email_score": 7.8,
            "email_iterations": 1,
        },
        {
            "corp_code": "000002",
            "corp_name": "테스트제조B",
            "revenue_bn_krw": 80.0,
            "operating_profit_bn_krw": 4.0,
            "operating_margin_pct": 5.0,
            "year": 2024,
            "financials_history": [],
            "readiness_score": 42.0,
            "score_breakdown": {
                "financial_health": 7.5,
                "growth_trajectory": 10.0,
                "size_signal": 9.5,
                "dart_disclosure": 15.0,
            },
            "geo_score": 40,
            "geo_breakdown": {
                "citability": 10,
                "crawler_access": 20,
                "brand_mention": 10,
            },
            "website_url": None,
            "email_subject": "[테스트제조B] AI 경쟁력 진단 — 귀사의 AI 가시성 점수는 40점입니다",
            "email_body": "안녕하세요. SDC(SKKU-Deloitte Consulting) 김건희입니다.\n귀사 AI 가시성 진단 결과를 공유드리고자 합니다.\n\n김건희 | SDC 회장",
            "email_score": 6.2,
            "email_iterations": 3,
        },
        {
            "corp_code": "000003",
            "corp_name": "테스트제조C",
            "revenue_bn_krw": 450.0,
            "operating_profit_bn_krw": 90.0,
            "operating_margin_pct": 20.0,
            "year": 2024,
            "financials_history": [],
            "readiness_score": 88.0,
            "score_breakdown": {
                "financial_health": 30.0,
                "growth_trajectory": 28.0,
                "size_signal": 15.0,
                "dart_disclosure": 15.0,
            },
            "geo_score": 75,
            "geo_breakdown": {
                "citability": 32,
                "crawler_access": 28,
                "brand_mention": 15,
            },
            "website_url": "https://www.testc.co.kr",
            "email_subject": "[테스트제조C] AI 경쟁력 진단 — 귀사의 AI 가시성 점수는 75점입니다",
            "email_body": "안녕하세요. SDC(SKKU-Deloitte Consulting) 회장 김건희입니다.\n귀사의 AI 가시성 점수는 75/100점이며, 매출액 4,500억원 대비 AI 인프라 투자 여력이 충분한 것으로 분석됩니다.\n무료 2페이지 진단 보고서를 제공해드릴 수 있습니다.\n\n김건희 | SDC (SKKU-Deloitte Consulting) 회장",
            "email_score": 8.3,
            "email_iterations": 1,
        },
    ]

    print("Running export test with 3 fake companies...\n")
    path = export_to_excel(fake_companies)
    print(f"\nExport complete: {path}")
