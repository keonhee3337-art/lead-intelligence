"""
Full Pipeline Orchestrator — Project B: Lead Intelligence

Stages:
  1. DART Screener      — filter companies by revenue range
  2. AI Readiness Scorer — score + rank, keep top_n
  3. GEO Audit          — citability, crawler, brand mention per company
  4. Outreach Generator — Korean email per company (sonnet draft + haiku refine)
  5. Excel Export       — Rankings + Outreach sheets
"""

import time
from pathlib import Path
from dotenv import load_dotenv

for _p in [Path(__file__).parent / '.env', Path(__file__).parent.parent / '.env', Path(__file__).parent.parent.parent / '.env']:
    if _p.exists():
        load_dotenv(dotenv_path=_p)
        break

from dart_screener import screen_companies
from ai_readiness_scorer import rank_companies
from geo_audit import run_geo_audit
from outreach_generator import generate_all_emails
from export import export_to_excel


def run_full_pipeline(
    min_revenue_bn_krw: float = 50,
    max_revenue_bn_krw: float = 1000,
    top_n: int = 10,
) -> tuple[list[dict], str]:
    """
    Runs the full lead intelligence pipeline end-to-end.

    Steps:
      1. Screen companies via DART (revenue filter)
      2. Score and rank → keep top_n
      3. Run GEO audit on each
      4. Generate outreach emails
      5. Export to Excel

    Returns:
      (companies, excel_path)
        companies — enriched list of dicts (all pipeline fields)
        excel_path — absolute path to generated .xlsx file
    """

    # ------------------------------------------------------------------
    # Stage 1: DART Screener
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STAGE 1 / 4 — DART Screener")
    print(f"  Revenue filter: {min_revenue_bn_krw}–{max_revenue_bn_krw} B KRW")
    print("=" * 60)

    screened = screen_companies(
        sector="제조업",
        min_revenue_bn_krw=min_revenue_bn_krw,
        max_revenue_bn_krw=max_revenue_bn_krw,
    )

    if not screened:
        print("[pipeline] No companies passed the screener. Aborting.")
        return [], ""

    print(f"\n[pipeline] Stage 1 complete: {len(screened)} companies screened.")
    time.sleep(1)

    # ------------------------------------------------------------------
    # Stage 2: AI Readiness Scoring + Ranking
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"STAGE 2 / 4 — AI Readiness Scoring (top {top_n})")
    print("=" * 60)

    # rank_companies returns top 10 by default — pass top_n override
    scored = [_score_one(c) for c in screened]
    ranked = sorted(scored, key=lambda x: x["readiness_score"], reverse=True)[:top_n]

    print(f"\n[pipeline] Stage 2 complete: {len(ranked)} companies ranked.")
    for i, c in enumerate(ranked, 1):
        print(f"  #{i} {c['corp_name']} — readiness: {c['readiness_score']}/100")
    time.sleep(1)

    # ------------------------------------------------------------------
    # Stage 3: GEO Audit
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STAGE 3 / 4 — GEO Audit")
    print("=" * 60)

    audited = run_geo_audit(ranked)

    print(f"\n[pipeline] Stage 3 complete: {len(audited)} companies audited.")
    time.sleep(1)

    # ------------------------------------------------------------------
    # Stage 4: Outreach Email Generation
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STAGE 4 / 4 — Outreach Email Generation")
    print("=" * 60)

    with_emails = generate_all_emails(audited)

    print(f"\n[pipeline] Stage 4 complete: {len(with_emails)} emails generated.")
    time.sleep(1)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("EXPORT — Writing Excel Report")
    print("=" * 60)

    excel_path = export_to_excel(with_emails)
    print(f"[pipeline] Export complete: {excel_path}")

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print(f"  Companies processed: {len(with_emails)}")
    print(f"  Excel report: {excel_path}")
    print("=" * 60 + "\n")

    return with_emails, excel_path


# ------------------------------------------------------------------
# Internal helper: score one company without the rank_companies cap
# ------------------------------------------------------------------
from ai_readiness_scorer import score_company as _score_one


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("Starting Lead Intelligence Pipeline...")
    print("This will take 2–5 minutes (DART + Perplexity API calls).\n")

    companies, excel_path = run_full_pipeline(
        min_revenue_bn_krw=50,
        max_revenue_bn_krw=1000,
        top_n=10,
    )

    if companies:
        print("\n--- Summary ---")
        for i, c in enumerate(companies, 1):
            print(
                f"#{i} {c['corp_name']} | "
                f"Readiness: {c.get('readiness_score', 'N/A')}/100 | "
                f"GEO: {c.get('geo_score', 'N/A')}/100 | "
                f"Email score: {c.get('email_score', 'N/A')}/10"
            )
        print(f"\nExcel report: {excel_path}")
    else:
        print("Pipeline returned no results.")
