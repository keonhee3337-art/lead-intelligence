"""
AI Readiness Scorer — Project B: Lead Intelligence

Scores companies from dart_screener on AI readiness potential.

Weights:
  - Financial health    30%  (operating margin proxy)
  - Growth trajectory   30%  (3Y revenue CAGR)
  - Company size signal 20%  (100-500B KRW sweet spot)
  - DART disclosure     20%  (stubbed at 15/20 — full impl in Session 2)
"""


def _score_financial_health(company: dict) -> float:
    """
    Operating margin > 20% = full 30 pts.
    Scales linearly from 0 at 0% margin to 30 at 20%+.
    """
    margin = company.get('operating_margin_pct')
    if margin is None:
        return 0.0
    score = min(margin / 20.0, 1.0) * 30
    return round(max(score, 0.0), 2)


def _score_growth_trajectory(company: dict) -> float:
    """
    3Y revenue CAGR > 10% = full 30 pts.
    Calculated from financials_history if available (needs >= 2 years).
    Score = (CAGR / 10) * 30, capped at 30.
    Negative CAGR = 0.
    """
    history = company.get('financials_history', [])

    if len(history) < 2:
        # Fallback: single year, no growth data — give neutral 10/30
        return 10.0

    sorted_hist = sorted(history, key=lambda x: x['year'])
    earliest = sorted_hist[0]
    latest = sorted_hist[-1]

    years_delta = latest['year'] - earliest['year']
    if years_delta <= 0:
        return 10.0

    rev_start = earliest.get('revenue_bn_krw')
    rev_end = latest.get('revenue_bn_krw')

    if not rev_start or not rev_end or rev_start <= 0:
        return 10.0

    cagr = ((rev_end / rev_start) ** (1.0 / years_delta) - 1) * 100  # in %
    score = min(cagr / 10.0, 1.0) * 30
    return round(max(score, 0.0), 2)


def _score_size_signal(company: dict) -> float:
    """
    Revenue 100-500B KRW = full 20 pts (AI project budget present, not too complex).
    <100B KRW: scales from 0 at 0 to 20 at 100B.
    >500B KRW: scales down from 20 at 500B to 10 at 2000B+.
    """
    revenue = company.get('revenue_bn_krw', 0)
    if revenue <= 0:
        return 0.0

    if 100 <= revenue <= 500:
        return 20.0
    elif revenue < 100:
        score = (revenue / 100.0) * 20
    else:
        # Larger companies: diminishing returns (harder to sell into, slower decisions)
        excess = revenue - 500
        penalty = min(excess / 1500.0, 0.5) * 20  # max 10pt penalty
        score = 20.0 - penalty

    return round(max(score, 0.0), 2)


def _score_dart_disclosure(company: dict) -> float:
    """
    Proxy for disclosure recency / transparency.
    Full score = 20. Stub: 15/20 for all companies pulled from DART
    (we assume recency since we just queried them).
    TODO Session 2: check actual filing dates via dart_fss disclosures API.
    """
    return 15.0


def score_company(company: dict) -> dict:
    """
    Takes a company dict from dart_screener.screen_companies().
    Returns the same dict with two new keys added:
        readiness_score: float (0-100)
        score_breakdown: dict with per-dimension scores
    """
    financial_health = _score_financial_health(company)
    growth = _score_growth_trajectory(company)
    size = _score_size_signal(company)
    disclosure = _score_dart_disclosure(company)

    total = financial_health + growth + size + disclosure

    scored = {**company}
    scored['readiness_score'] = round(total, 2)
    scored['score_breakdown'] = {
        'financial_health': financial_health,
        'growth_trajectory': growth,
        'size_signal': size,
        'dart_disclosure': disclosure,
    }
    return scored


def rank_companies(companies: list[dict]) -> list[dict]:
    """
    Score all companies, sort descending by readiness_score.
    Returns top 10.
    """
    scored = [score_company(c) for c in companies]
    ranked = sorted(scored, key=lambda x: x['readiness_score'], reverse=True)
    return ranked[:10]


if __name__ == "__main__":
    # Sample test data — mimics output shape from dart_screener
    sample_companies = [
        {
            'corp_code': '000001',
            'corp_name': '테스트제조A',
            'revenue_bn_krw': 320.0,
            'operating_profit_bn_krw': 48.0,
            'operating_margin_pct': 15.0,
            'year': 2024,
            'financials_history': [
                {'year': 2022, 'revenue_bn_krw': 210.0, 'operating_profit_bn_krw': 25.0, 'operating_margin_pct': 11.9},
                {'year': 2023, 'revenue_bn_krw': 260.0, 'operating_profit_bn_krw': 35.0, 'operating_margin_pct': 13.5},
                {'year': 2024, 'revenue_bn_krw': 320.0, 'operating_profit_bn_krw': 48.0, 'operating_margin_pct': 15.0},
            ],
        },
        {
            'corp_code': '000002',
            'corp_name': '테스트제조B',
            'revenue_bn_krw': 80.0,
            'operating_profit_bn_krw': 4.0,
            'operating_margin_pct': 5.0,
            'year': 2024,
            'financials_history': [
                {'year': 2023, 'revenue_bn_krw': 75.0, 'operating_profit_bn_krw': 3.5, 'operating_margin_pct': 4.7},
                {'year': 2024, 'revenue_bn_krw': 80.0, 'operating_profit_bn_krw': 4.0, 'operating_margin_pct': 5.0},
            ],
        },
        {
            'corp_code': '000003',
            'corp_name': '테스트제조C',
            'revenue_bn_krw': 450.0,
            'operating_profit_bn_krw': 90.0,
            'operating_margin_pct': 20.0,
            'year': 2024,
            'financials_history': [
                {'year': 2022, 'revenue_bn_krw': 380.0, 'operating_profit_bn_krw': 68.0, 'operating_margin_pct': 17.9},
                {'year': 2023, 'revenue_bn_krw': 415.0, 'operating_profit_bn_krw': 80.0, 'operating_margin_pct': 19.3},
                {'year': 2024, 'revenue_bn_krw': 450.0, 'operating_profit_bn_krw': 90.0, 'operating_margin_pct': 20.0},
            ],
        },
    ]

    print("--- AI Readiness Scores ---\n")
    ranked = rank_companies(sample_companies)
    for i, c in enumerate(ranked, 1):
        breakdown = c['score_breakdown']
        print(
            f"#{i} {c['corp_name']} | Score: {c['readiness_score']}/100 | "
            f"Health: {breakdown['financial_health']} | "
            f"Growth: {breakdown['growth_trajectory']} | "
            f"Size: {breakdown['size_signal']} | "
            f"Disclosure: {breakdown['dart_disclosure']}"
        )
