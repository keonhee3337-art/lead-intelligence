"""
GEO Audit Agent — Project B: Lead Intelligence

Checks each company's AI discoverability across three dimensions:
  - Citability Score    (0-40): structured content on website
  - Crawler Access Score (0-30): robots.txt GPTBot/ClaudeBot/PerplexityBot rules
  - Brand Mention Score  (0-30): Perplexity brand visibility

Total GEO score = sum of three (max 100).
"""

import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / '.env')

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
if not PERPLEXITY_API_KEY:
    raise EnvironmentError("PERPLEXITY_API_KEY not found in .env")

HEADERS = {
    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
    "Content-Type": "application/json",
}
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar"

REQUEST_TIMEOUT = 8
ROBOTS_TIMEOUT = 5


def _perplexity_query(prompt: str) -> str:
    """Send a query to Perplexity sonar. Returns response text or empty string on failure."""
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }
    try:
        resp = requests.post(PERPLEXITY_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    [perplexity error] {e}")
        return ""


def _find_website_url(corp_name: str) -> str | None:
    """Use Perplexity to find the company's official website URL."""
    prompt = f"{corp_name} 공식 홈페이지 site:kr OR site:com"
    response = _perplexity_query(prompt)
    if not response:
        return None

    # Extract first URL-looking token from the response
    import re
    urls = re.findall(r'https?://[^\s\)\]\,\"\']+', response)
    # Prefer .co.kr or .com domains that aren't social media or news
    skip_domains = {'naver', 'daum', 'google', 'kakao', 'instagram', 'facebook', 'linkedin', 'youtube'}
    for url in urls:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not any(skip in host for skip in skip_domains):
            # Clean trailing punctuation
            url = url.rstrip('.,;)')
            return url
    return None


def _score_citability(website_url: str | None) -> int:
    """
    Fetch website HTML and count content-rich paragraphs (>50 words).
    Score = min(block_count * 4, 40).
    Returns 10 if fetch fails or no URL.
    """
    if not website_url:
        return 10

    try:
        resp = requests.get(
            website_url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"},
            allow_redirects=True,
        )
        if resp.status_code in (403, 429, 503):
            print(f"    [citability] {resp.status_code} — using default score 10")
            return 10
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"    [citability fetch error] {e}")
        return 10

    # Count paragraphs with >50 words (naive split on <p> tags or block separators)
    import re
    # Strip script/style blocks
    html = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Extract text between tags
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, flags=re.DOTALL | re.IGNORECASE)
    # Also capture divs with substantial text if paragraphs are sparse
    if len(paragraphs) < 3:
        paragraphs += re.findall(r'<div[^>]*>(.*?)</div>', html, flags=re.DOTALL | re.IGNORECASE)

    block_count = 0
    for p in paragraphs:
        # Strip HTML tags inside paragraph
        text = re.sub(r'<[^>]+>', ' ', p).strip()
        word_count = len(text.split())
        if word_count > 50:
            block_count += 1

    score = min(block_count * 4, 40)
    # Floor at 10 — if the page loaded, there's some basic web presence
    score = max(score, 10)
    print(f"    [citability] {block_count} rich blocks → {score}/40")
    return score


def _score_crawler_access(website_url: str | None) -> int:
    """
    Fetch robots.txt and check for GPTBot, ClaudeBot, PerplexityBot rules.
    Base = 30. Each bot disallowed = -10.
    Returns 25 if robots.txt not found.
    """
    if not website_url:
        return 25

    parsed = urlparse(website_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    try:
        resp = requests.get(
            robots_url,
            timeout=ROBOTS_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 404:
            return 25
        resp.raise_for_status()
        content = resp.text.lower()
    except Exception as e:
        print(f"    [robots.txt error] {e}")
        return 25

    score = 30
    ai_bots = ["gptbot", "claudebot", "perplexitybot"]

    # Parse robots.txt blocks — find relevant user-agent blocks
    import re
    # Build a mapping: user-agent -> list of disallow rules
    blocks = re.split(r'\n\s*\n', content)
    current_agents = []
    disallowed_bots = set()

    for line in content.splitlines():
        line = line.strip()
        if line.startswith('user-agent:'):
            agent = line.split(':', 1)[1].strip()
            current_agents = [agent]
        elif line.startswith('disallow:'):
            disallow_path = line.split(':', 1)[1].strip()
            if disallow_path == '/' or disallow_path == '':
                # disallow: / means blocked; disallow: (empty) means allowed
                if disallow_path == '/':
                    for agent in current_agents:
                        if agent in ai_bots:
                            disallowed_bots.add(agent)

    for bot in ai_bots:
        if bot in disallowed_bots:
            score -= 10
            print(f"    [robots.txt] {bot} disallowed — -10")

    print(f"    [crawler access] score {score}/30")
    return max(score, 0)


def _score_brand_mention(corp_name: str) -> int:
    """
    Query Perplexity for brand visibility in AI/digital context.
    Returns 20 if mentioned, 5 if not, 10 if Perplexity fails.
    """
    prompt = f"{corp_name} 한국 기업 AI 도입 디지털전환"
    response = _perplexity_query(prompt)

    if not response:
        print(f"    [brand mention] Perplexity failed → 10")
        return 10

    # Check if company name appears in response
    if corp_name in response:
        print(f"    [brand mention] '{corp_name}' mentioned → 20")
        return 20
    else:
        print(f"    [brand mention] '{corp_name}' not found in response → 5")
        return 5


def audit_company_geo(company: dict) -> dict:
    """
    Takes company dict with at minimum: corp_name, readiness_score.
    Returns company dict + {
        "geo_score": int,
        "geo_breakdown": {"citability": int, "crawler_access": int, "brand_mention": int},
        "website_url": str or None
    }
    """
    corp_name = company["corp_name"]
    print(f"\n[GEO Audit] {corp_name}")

    # Step 1: Find website URL
    print(f"  Finding website URL...")
    website_url = _find_website_url(corp_name)
    print(f"  URL: {website_url}")

    # Step 2: Run three checks
    print(f"  Check 1 — Citability...")
    citability = _score_citability(website_url)

    print(f"  Check 2 — Crawler Access...")
    crawler_access = _score_crawler_access(website_url)

    print(f"  Check 3 — Brand Mention...")
    brand_mention = _score_brand_mention(corp_name)

    geo_score = citability + crawler_access + brand_mention

    result = {**company}
    result["geo_score"] = geo_score
    result["geo_breakdown"] = {
        "citability": citability,
        "crawler_access": crawler_access,
        "brand_mention": brand_mention,
    }
    result["website_url"] = website_url

    print(f"  GEO Score: {geo_score}/100 (citability={citability}, crawler={crawler_access}, brand={brand_mention})")
    return result


def run_geo_audit(companies: list[dict]) -> list[dict]:
    """Run GEO audit on all companies. Adds 2s sleep between companies."""
    results = []
    for i, company in enumerate(companies):
        audited = audit_company_geo(company)
        results.append(audited)
        if i < len(companies) - 1:
            time.sleep(2)
    print(f"\nGEO audit complete: {len(results)} companies processed.")
    return results


if __name__ == "__main__":
    sample_companies = [
        {
            "corp_code": "000001",
            "corp_name": "현대모비스",
            "revenue_bn_krw": 320.0,
            "operating_profit_bn_krw": 48.0,
            "operating_margin_pct": 15.0,
            "year": 2024,
            "financials_history": [
                {"year": 2022, "revenue_bn_krw": 210.0, "operating_profit_bn_krw": 25.0, "operating_margin_pct": 11.9},
                {"year": 2024, "revenue_bn_krw": 320.0, "operating_profit_bn_krw": 48.0, "operating_margin_pct": 15.0},
            ],
            "readiness_score": 72.5,
            "score_breakdown": {
                "financial_health": 22.5,
                "growth_trajectory": 25.0,
                "size_signal": 10.0,
                "dart_disclosure": 15.0,
            },
        },
        {
            "corp_code": "000002",
            "corp_name": "솔브레인",
            "revenue_bn_krw": 180.0,
            "operating_profit_bn_krw": 36.0,
            "operating_margin_pct": 20.0,
            "year": 2024,
            "financials_history": [
                {"year": 2022, "revenue_bn_krw": 140.0, "operating_profit_bn_krw": 28.0, "operating_margin_pct": 20.0},
                {"year": 2024, "revenue_bn_krw": 180.0, "operating_profit_bn_krw": 36.0, "operating_margin_pct": 20.0},
            ],
            "readiness_score": 80.0,
            "score_breakdown": {
                "financial_health": 30.0,
                "growth_trajectory": 20.0,
                "size_signal": 15.0,
                "dart_disclosure": 15.0,
            },
        },
    ]

    print("Running GEO audit on 2 sample companies...\n")
    results = run_geo_audit(sample_companies)

    print("\n--- GEO Audit Results ---")
    for r in results:
        print(
            f"{r['corp_name']} | GEO: {r['geo_score']}/100 | "
            f"Citability: {r['geo_breakdown']['citability']} | "
            f"Crawler: {r['geo_breakdown']['crawler_access']} | "
            f"Brand: {r['geo_breakdown']['brand_mention']} | "
            f"URL: {r['website_url']}"
        )
