"""
GEO Audit Agent — Project B: Lead Intelligence

Scores each company across five consultant-grade GEO dimensions:

  Category 1: AI Citability & Share of Voice    (0-50)
    - Content-rich paragraphs on website         (0-40, citability)
    - Competitive AI citation frequency           (0-10, share_of_voice)

  Category 2: Crawler & Agent Accessibility     (0-30)
    - robots.txt AI bot rules                    (0-20, ai_bot_access)
    - llms.txt / AI policy file at site root     (0-10, ai_policy_file)

  Category 3: Schema & Structured Data          (0-30)
    - JSON-LD Organization schema                (0-15, org_schema)
    - FAQ / HowTo / Article schemas              (0-15, content_schema)

  Category 4: Local Sync — KR Platforms         (0-20)
    - Naver Smart Place / Business Profile       (0-10, naver_presence)
    - 사업자등록번호 on website + Kakao Map       (0-10, kr_platform_sync)

  Category 5: Brand Sentiment & Mention Quality (0-20)
    - How brand is described by AI (premium vs. commodity)
    - Whether brand appears in expert/editorial context

Total GEO score = sum of five categories (max 150, normalized to /100 in audit_company_geo).
"""

import os
import re
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

for _p in [Path(__file__).parent / '.env', Path(__file__).parent.parent / '.env', Path(__file__).parent.parent.parent / '.env']:
    if _p.exists():
        load_dotenv(dotenv_path=_p)
        break

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

# Schema.org types that indicate structured content depth
SCHEMA_ORG_TYPES = ["Organization", "LocalBusiness", "Corporation"]
SCHEMA_CONTENT_TYPES = ["FAQPage", "HowTo", "Article", "Product", "ItemList", "BreadcrumbList"]


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

    urls = re.findall(r'https?://[^\s\)\]\,\"\']+', response)
    skip_domains = {'naver', 'daum', 'google', 'kakao', 'instagram', 'facebook', 'linkedin', 'youtube'}
    for url in urls:
        url = re.split(r'[^a-zA-Z0-9\-\.\/\:\?=&#%_~]', url)[0]
        url = url.rstrip('.,;)/\\')
        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
        except ValueError:
            continue
        if host and '.' in host and not any(skip in host for skip in skip_domains):
            return url
    return None


# ─────────────────────────────────────────────────────────────
# Category 1: AI Citability & Share of Voice (max 50)
# ─────────────────────────────────────────────────────────────

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
            headers={"User-Agent": "Mozilla/5.0 (compatible; GEOBot/1.0)"},
            allow_redirects=True,
        )
        if resp.status_code in (403, 429, 503):
            print(f"    [citability] {resp.status_code} — using default 10")
            return 10
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"    [citability fetch error] {e}")
        return 10

    html = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, flags=re.DOTALL | re.IGNORECASE)
    if len(paragraphs) < 3:
        paragraphs += re.findall(r'<div[^>]*>(.*?)</div>', html, flags=re.DOTALL | re.IGNORECASE)

    block_count = 0
    for p in paragraphs:
        text = re.sub(r'<[^>]+>', ' ', p).strip()
        if len(text.split()) > 50:
            block_count += 1

    score = min(block_count * 4, 40)
    score = max(score, 10)
    print(f"    [citability] {block_count} rich blocks → {score}/40")
    return score


def _score_share_of_voice(corp_name: str) -> dict:
    """
    Competitive Share of Voice: query Perplexity for industry competitors,
    check if target company is cited alongside them.

    Returns {"sov_score": int 0-10, "competitors_found": list[str], "cited": bool}
    """
    industry_prompt = f"{corp_name} 경쟁사 OR 동종업계 OR 업종 한국 기업"
    industry_resp = _perplexity_query(industry_prompt)

    if not industry_resp:
        print(f"    [sov] Perplexity failed → 0")
        return {"sov_score": 0, "competitors_found": [], "cited": False}

    cited = corp_name in industry_resp

    # Extract company names from response (Korean company suffix heuristic)
    corp_patterns = re.findall(
        r'[\uAC00-\uD7A3]{2,10}(?:주식회사|㈜|코리아|전자|중공업|화학|제약|물산|건설|에너지|반도체|소재|침대|가구|식품)?',
        industry_resp
    )
    competitors = [c for c in corp_patterns if c != corp_name and len(c) > 1][:5]

    sov_score = 7 if cited else 2
    print(f"    [sov] '{corp_name}' cited: {cited} → {sov_score}/10")
    print(f"    [sov] Competitors: {competitors[:3]}")

    return {"sov_score": sov_score, "competitors_found": competitors, "cited": cited}


# ─────────────────────────────────────────────────────────────
# Category 2: Crawler & Agent Accessibility (max 30)
# ─────────────────────────────────────────────────────────────

def _score_ai_bot_access(website_url: str | None) -> int:
    """
    Fetch robots.txt and check for GPTBot, ClaudeBot, PerplexityBot rules.
    Base = 20 (was 30 — split with ai_policy_file).
    Each bot disallowed = -6.
    Returns 15 if robots.txt not found (neutral).
    """
    if not website_url:
        return 15

    parsed = urlparse(website_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    try:
        resp = requests.get(
            robots_url,
            timeout=ROBOTS_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 404:
            return 15
        resp.raise_for_status()
        content = resp.text.lower()
    except Exception as e:
        print(f"    [robots.txt error] {e}")
        return 15

    score = 20
    ai_bots = ["gptbot", "claudebot", "perplexitybot"]
    current_agents = []
    disallowed_bots = set()

    for line in content.splitlines():
        line = line.strip()
        if line.startswith('user-agent:'):
            agent = line.split(':', 1)[1].strip()
            current_agents = [agent]
        elif line.startswith('disallow:'):
            disallow_path = line.split(':', 1)[1].strip()
            if disallow_path == '/':
                for agent in current_agents:
                    if agent in ai_bots:
                        disallowed_bots.add(agent)

    for bot in ai_bots:
        if bot in disallowed_bots:
            score -= 6
            print(f"    [robots.txt] {bot} disallowed — -6")

    score = max(score, 0)
    print(f"    [ai_bot_access] score {score}/20")
    return score


def _score_ai_policy_file(website_url: str | None) -> int:
    """
    Check if site has an llms.txt file (AI content policy — emerging standard).
    Also checks for ai.txt as an alternative.
    Returns 10 if found and non-empty, 0 otherwise.
    """
    if not website_url:
        return 0

    parsed = urlparse(website_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    for path in ("/llms.txt", "/ai.txt"):
        try:
            resp = requests.get(
                base + path,
                timeout=ROBOTS_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200 and len(resp.text.strip()) > 10:
                print(f"    [ai_policy_file] found at {base + path} → 10")
                return 10
        except Exception:
            continue

    print(f"    [ai_policy_file] not found → 0")
    return 0


# ─────────────────────────────────────────────────────────────
# Category 3: Schema & Structured Data (max 30)
# ─────────────────────────────────────────────────────────────

def _score_schema_structured_data(website_url: str | None) -> dict:
    """
    Fetch homepage HTML and check for schema.org JSON-LD structured data.
    Org schema (Organization/LocalBusiness/Corporation): up to 15 pts
    Content schema (FAQPage/HowTo/Article/Product): up to 15 pts

    Returns {"org_schema": int, "content_schema": int}
    """
    if not website_url:
        return {"org_schema": 0, "content_schema": 0}

    try:
        resp = requests.get(
            website_url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; GEOBot/1.0)"},
            allow_redirects=True,
        )
        if resp.status_code not in (200, 301, 302):
            print(f"    [schema] HTTP {resp.status_code} — 0")
            return {"org_schema": 0, "content_schema": 0}
        html = resp.text
    except Exception as e:
        print(f"    [schema fetch error] {e}")
        return {"org_schema": 0, "content_schema": 0}

    import json as _json
    ld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    org_types_found = set()
    content_types_found = set()

    for block in ld_blocks:
        try:
            data = _json.loads(block.strip())
            items = data if isinstance(data, list) else [data]
            for item in items:
                t = item.get("@type", "")
                types = t if isinstance(t, list) else [t]
                for schema_type in types:
                    if schema_type in SCHEMA_ORG_TYPES:
                        org_types_found.add(schema_type)
                    if schema_type in SCHEMA_CONTENT_TYPES:
                        content_types_found.add(schema_type)
        except Exception:
            continue

    # Org schema: 15 pts if any org type found, 0 if none
    org_score = 15 if org_types_found else 0
    # Content schema: 5 pts per type, max 15
    content_score = min(len(content_types_found) * 5, 15)

    print(f"    [schema] org: {list(org_types_found) or 'none'} → {org_score}/15 | content: {list(content_types_found) or 'none'} → {content_score}/15")
    return {"org_schema": org_score, "content_schema": content_score}


# ─────────────────────────────────────────────────────────────
# Category 4: Local Sync — KR Platforms (max 20)
# ─────────────────────────────────────────────────────────────

def _score_kr_platform_sync(corp_name: str, website_url: str | None) -> dict:
    """
    Check Korean-specific GEO signals:
      - Naver Smart Place / Business Profile (10 pts)
      - 사업자등록번호 on website (5 pts) + Kakao Map listing (5 pts)

    Returns {"naver_presence": int, "kr_platform_sync": int}
    """
    naver_score = 0
    platform_score = 0

    # 1. Naver Smart Place / Business Profile
    naver_prompt = f"{corp_name} 네이버 플레이스 OR 네이버 지도 OR 네이버 비즈니스 공식 등록"
    naver_resp = _perplexity_query(naver_prompt)
    if naver_resp and corp_name in naver_resp:
        naver_score = 10
        print(f"    [kr_platform] Naver profile found → +10")
    else:
        print(f"    [kr_platform] Naver profile not found → 0")

    # 2. 사업자등록번호 on website (signals legitimacy to Korean AI systems)
    if website_url:
        try:
            resp = requests.get(
                website_url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            )
            if resp.status_code == 200 and re.search(r'\d{3}-\d{2}-\d{5}', resp.text):
                platform_score += 5
                print(f"    [kr_platform] 사업자등록번호 found → +5")
            else:
                print(f"    [kr_platform] 사업자등록번호 not found → 0")
        except Exception as e:
            print(f"    [kr_platform] website check error: {e}")

    # 3. Kakao Map listing
    kakao_prompt = f"{corp_name} 카카오맵 OR 카카오 지도 위치 정보"
    kakao_resp = _perplexity_query(kakao_prompt)
    if kakao_resp and corp_name in kakao_resp:
        platform_score += 5
        print(f"    [kr_platform] Kakao Map found → +5")
    else:
        print(f"    [kr_platform] Kakao Map not found → 0")

    print(f"    [kr_platform] naver={naver_score}/10 | platform_sync={platform_score}/10")
    return {"naver_presence": naver_score, "kr_platform_sync": platform_score}


# ─────────────────────────────────────────────────────────────
# Category 5: Brand Sentiment & Mention Quality (max 20)
# ─────────────────────────────────────────────────────────────

def _score_brand_sentiment(corp_name: str) -> dict:
    """
    Assess how the brand is described by AI systems:
      - Basic brand mention (AI knows the company exists): 10 pts
      - Quality signal (AI describes brand with specifics, not generic): +10 pts

    Returns {"brand_mention": int, "sentiment_quality": int}
    """
    prompt = f"{corp_name} 한국 기업 제품 서비스 특징 강점"
    response = _perplexity_query(prompt)

    if not response:
        print(f"    [brand_sentiment] Perplexity failed → 0")
        return {"brand_mention": 0, "sentiment_quality": 0}

    # Basic mention
    mentioned = corp_name in response
    brand_score = 10 if mentioned else 0

    if not mentioned:
        print(f"    [brand_sentiment] '{corp_name}' not mentioned → 0/10 | quality 0/10")
        return {"brand_mention": 0, "sentiment_quality": 0}

    # Quality: response should include specifics (numbers, product names, industry terms)
    # Heuristic: response > 200 chars about the company AND contains specific Korean terms
    quality_signals = [
        r'\d+억|\d+조|\d+%',          # revenue/profit figures
        r'매출|영업이익|시장점유율',      # financial terms
        r'특허|인증|수상|수출',          # credibility markers
        r'제품|솔루션|서비스|플랫폼',    # product specificity
    ]
    quality_count = sum(1 for pattern in quality_signals if re.search(pattern, response))
    sentiment_score = min(quality_count * 3, 10)  # 3 pts per signal, max 10

    print(f"    [brand_sentiment] mentioned: {mentioned} → brand={brand_score}/10 | quality_signals={quality_count} → {sentiment_score}/10")
    return {"brand_mention": brand_score, "sentiment_quality": sentiment_score}


# ─────────────────────────────────────────────────────────────
# Main audit function
# ─────────────────────────────────────────────────────────────

def audit_company_geo(company: dict) -> dict:
    """
    Takes company dict with at minimum: corp_name.
    Runs all 5 GEO categories, returns company dict enriched with:
        geo_score (int /100)
        geo_breakdown (dict with all sub-dimension scores)
        website_url (str or None)
        sov_competitors (list)
        sov_cited (bool)
    """
    corp_name = company["corp_name"]
    print(f"\n[GEO Audit] {corp_name}")

    # Find website
    print(f"  Finding website URL...")
    website_url = _find_website_url(corp_name)
    print(f"  URL: {website_url}")

    # --- Category 1: AI Citability & Share of Voice ---
    print(f"  [Cat 1] AI Citability & Share of Voice...")
    citability = _score_citability(website_url)
    sov_data = _score_share_of_voice(corp_name)
    sov_score = sov_data["sov_score"]
    cat1_total = citability + sov_score  # max 50

    # --- Category 2: Crawler & Agent Accessibility ---
    print(f"  [Cat 2] Crawler & Agent Accessibility...")
    ai_bot_access = _score_ai_bot_access(website_url)
    ai_policy_file = _score_ai_policy_file(website_url)
    cat2_total = ai_bot_access + ai_policy_file  # max 30

    # --- Category 3: Schema & Structured Data ---
    print(f"  [Cat 3] Schema & Structured Data...")
    schema_data = _score_schema_structured_data(website_url)
    org_schema = schema_data["org_schema"]
    content_schema = schema_data["content_schema"]
    cat3_total = org_schema + content_schema  # max 30

    # --- Category 4: Local Sync — KR Platforms ---
    print(f"  [Cat 4] Local Sync - KR Platforms...")
    kr_data = _score_kr_platform_sync(corp_name, website_url)
    naver_presence = kr_data["naver_presence"]
    kr_platform_sync = kr_data["kr_platform_sync"]
    cat4_total = naver_presence + kr_platform_sync  # max 20

    # --- Category 5: Brand Sentiment & Mention Quality ---
    print(f"  [Cat 5] Brand Sentiment & Mention Quality...")
    sentiment_data = _score_brand_sentiment(corp_name)
    brand_mention = sentiment_data["brand_mention"]
    sentiment_quality = sentiment_data["sentiment_quality"]
    cat5_total = brand_mention + sentiment_quality  # max 20

    # Total: max 150, normalized to /100
    raw_total = cat1_total + cat2_total + cat3_total + cat4_total + cat5_total
    geo_score = round(raw_total / 150 * 100)

    result = {**company}
    result["geo_score"] = geo_score
    result["geo_breakdown"] = {
        # Category 1
        "citability": citability,           # /40
        "share_of_voice": sov_score,        # /10
        # Category 2
        "ai_bot_access": ai_bot_access,     # /20
        "ai_policy_file": ai_policy_file,   # /10
        # Category 3
        "org_schema": org_schema,           # /15
        "content_schema": content_schema,   # /15
        # Category 4
        "naver_presence": naver_presence,   # /10
        "kr_platform_sync": kr_platform_sync,  # /10
        # Category 5
        "brand_mention": brand_mention,     # /10
        "sentiment_quality": sentiment_quality,  # /10
        # Legacy keys (for backward compat with app.py / report)
        "crawler_access": ai_bot_access,
        "schema_org": org_schema + content_schema,
        "llms_txt": ai_policy_file,
        "korean_presence": naver_presence + kr_platform_sync,
    }
    result["sov_competitors"] = sov_data.get("competitors_found", [])
    result["sov_cited"] = sov_data.get("cited", False)
    result["website_url"] = website_url

    print(
        f"  GEO Score: {geo_score}/100 (raw {raw_total}/150) | "
        f"Cat1={cat1_total}/50 Cat2={cat2_total}/30 Cat3={cat3_total}/30 Cat4={cat4_total}/20 Cat5={cat5_total}/20"
    )
    return result


def audit_single_company(company_name: str) -> dict:
    """
    Audit any company by name only — no DART data required.
    Works for startups, SMEs, any company with a website.
    Returns a full GEO audit dict compatible with audit_company_geo() output.
    """
    company = {"corp_name": company_name, "readiness_score": None}
    return audit_company_geo(company)


def generate_dynamic_recommendations(breakdown: dict, corp_name: str = "") -> list[str]:
    """
    Generate company-specific recommendations based on which dimensions scored low.
    Maps each of the 5 categories to actionable Korean-language recommendations.
    Returns 3-5 items ordered by impact.
    """
    recs = []

    # --- Category 2: Crawler & Agent Accessibility ---
    ai_bot = breakdown.get("ai_bot_access", breakdown.get("crawler_access", 20))
    ai_policy = breakdown.get("ai_policy_file", breakdown.get("llms_txt", 0))

    if ai_policy == 0:
        recs.append(
            "웹사이트 루트에 llms.txt 파일 생성 — AI 시스템에 콘텐츠 접근 허용을 명시하는 신규 표준입니다. "
            "5분 내 적용 가능하며 GPTBot, ClaudeBot, PerplexityBot의 콘텐츠 인덱싱을 즉시 개선합니다"
        )

    if ai_bot < 14:  # below 70% of 20
        recs.append(
            f"robots.txt에 GPTBot, ClaudeBot, PerplexityBot 허용 규칙 명시 "
            f"(현재 {ai_bot}/20점) — AI 크롤러가 차단되면 AI 추천 결과에 포함될 수 없습니다. "
            "User-agent: GPTBot / Disallow: (blank) 규칙 추가로 즉시 해결됩니다"
        )

    # --- Category 3: Schema & Structured Data ---
    org_schema = breakdown.get("org_schema", 0)
    content_schema = breakdown.get("content_schema", 0)

    if org_schema == 0:
        recs.append(
            "홈페이지에 Organization JSON-LD 구조화 데이터 추가 — "
            "AI 시스템이 기업명, 설립연도, 주요 제품, 위치 정보를 정확히 인식하게 합니다. "
            "30분 내 적용 가능하며 AI 검색 인용 정확도를 직접 높입니다"
        )

    if content_schema == 0:
        recs.append(
            "제품/서비스 페이지에 FAQPage JSON-LD 스키마 추가 — "
            "ChatGPT, Perplexity가 FAQ를 질의 응답으로 직접 인용합니다. "
            "\"자주 묻는 질문\" 섹션을 구조화 데이터로 마크업하면 AI 가시성이 빠르게 향상됩니다"
        )

    # --- Category 1: AI Citability ---
    citability = breakdown.get("citability", 40)
    if citability < 20:
        recs.append(
            "주요 페이지(회사 소개, 제품/서비스)에 50단어 이상의 구체적 텍스트 블록 추가 — "
            "AI는 구조화된 긴 문단을 인용합니다. 수치, 고객 사례, 기술 사양 등 "
            "사실 기반 내용이 AI 인용 빈도를 높입니다"
        )

    # --- Category 4: KR Platforms ---
    naver = breakdown.get("naver_presence", 10)
    kr_sync = breakdown.get("kr_platform_sync", 10)

    if naver == 0:
        recs.append(
            "네이버 스마트플레이스 등록/업데이트 — "
            "한국 AI 생태계(네이버 클로바, 하이퍼클로바)에서의 가시성을 결정합니다. "
            "사업자등록번호를 웹사이트 footer에 표시하면 AI 신뢰도 인식도 함께 높아집니다"
        )

    if kr_sync == 0 and naver > 0:
        recs.append(
            "카카오맵 비즈니스 정보 등록 및 웹사이트에 사업자등록번호 표시 — "
            "한국 플랫폼 교차 검증 신호를 강화하여 한국어 AI 쿼리에서 인용 가능성을 높입니다"
        )

    # --- Category 5: Brand Sentiment ---
    brand_mention = breakdown.get("brand_mention", 10)
    sentiment = breakdown.get("sentiment_quality", 10)

    if brand_mention == 0:
        recs.append(
            f"'{corp_name}' 브랜드가 AI 검색에서 거의 언급되지 않습니다. "
            "업계 질문에 답변이 될 콘텐츠(블로그, 사례 연구, 비교 가이드)를 발행하고 "
            "언론 보도 및 업계 DB 등록으로 AI 인용 기반을 만드세요"
        )
    elif sentiment < 6:
        recs.append(
            "AI가 귀사 브랜드를 언급하지만 구체적 설명이 부족합니다. "
            "매출 규모, 고객사, 수상 이력, 기술 특허 등 검증 가능한 수치를 웹사이트에 추가하면 "
            "AI가 더 구체적이고 긍정적인 방식으로 브랜드를 설명합니다"
        )

    # --- SoV fallback ---
    sov = breakdown.get("share_of_voice", 10)
    if sov < 4 and len(recs) < 3:
        recs.append(
            "경쟁사 대비 AI 인용 빈도가 낮습니다. 업계 키워드에서 AI가 귀사를 추천하도록 "
            "'답변형 콘텐츠'(Q&A, 비교 분석, 가이드)를 우선 발행하세요"
        )

    # Fallback if all dimensions score well
    if not recs:
        recs = [
            "전체적으로 높은 GEO 점수입니다. 월간 SoV 모니터링으로 경쟁사 대비 AI 가시성을 유지하세요",
            "분기별 콘텐츠 업데이트로 AI 시스템의 최신 정보 반영을 유도하세요",
            "신규 제품/서비스 출시 시 구조화된 페이지와 FAQ를 즉시 추가하세요",
        ]

    return recs[:5]


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
            "readiness_score": 72.5,
        },
        {
            "corp_code": "000002",
            "corp_name": "솔브레인",
            "revenue_bn_krw": 180.0,
            "operating_profit_bn_krw": 36.0,
            "operating_margin_pct": 20.0,
            "year": 2024,
            "readiness_score": 80.0,
        },
    ]

    print("Running GEO audit on 2 sample companies...\n")
    results = run_geo_audit(sample_companies)

    print("\n--- GEO Audit Results ---")
    for r in results:
        bd = r['geo_breakdown']
        print(
            f"{r['corp_name']} | GEO: {r['geo_score']}/100 | "
            f"Cat1(Citability+SoV)={bd['citability']+bd['share_of_voice']}/50 | "
            f"Cat2(Crawler)={bd['ai_bot_access']+bd['ai_policy_file']}/30 | "
            f"Cat3(Schema)={bd['org_schema']+bd['content_schema']}/30 | "
            f"Cat4(KR)={bd['naver_presence']+bd['kr_platform_sync']}/20 | "
            f"Cat5(Brand)={bd['brand_mention']+bd['sentiment_quality']}/20"
        )
