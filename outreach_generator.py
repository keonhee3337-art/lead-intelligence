"""
Outreach Email Generator — Project B: Lead Intelligence

Generates personalized Korean B2B outreach emails using:
  - Company DART financials (revenue, operating margin)
  - GEO audit score (citability, crawler access, brand mention)

Pipeline:
  1. claude-sonnet-4-6 drafts the email
  2. claude-haiku-4-5-20251001 scores it (persuasiveness, specificity, professionalism)
  3. If avg score < 7.5 and iterations < 3, improve and retry

Email is always in Korean, signed by 김건희 / SDC (SKKU-Deloitte Consulting).
"""

import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / '.env')

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise EnvironmentError("ANTHROPIC_API_KEY not found in .env")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

SCORE_THRESHOLD = 7.5
MAX_ITERATIONS = 3


def _format_company_context(company: dict) -> str:
    """Build a concise context block for prompt injection."""
    corp_name = company.get("corp_name", "")
    revenue = company.get("revenue_bn_krw")
    margin = company.get("operating_margin_pct")
    year = company.get("year", "")
    geo_score = company.get("geo_score")
    geo_breakdown = company.get("geo_breakdown", {})
    readiness_score = company.get("readiness_score")

    lines = [f"회사명: {corp_name}"]
    if revenue is not None:
        lines.append(f"매출액 ({year}): {revenue:.1f}억원")
    if margin is not None:
        lines.append(f"영업이익률 ({year}): {margin:.1f}%")
    if readiness_score is not None:
        lines.append(f"AI 준비도 점수: {readiness_score}/100")
    if geo_score is not None:
        lines.append(f"GEO(AI 가시성) 점수: {geo_score}/100")
        citability = geo_breakdown.get("citability")
        crawler = geo_breakdown.get("crawler_access")
        brand = geo_breakdown.get("brand_mention")
        if citability is not None:
            lines.append(f"  - 콘텐츠 인용 가능성: {citability}/40")
        if crawler is not None:
            lines.append(f"  - AI 크롤러 접근성: {crawler}/30")
        if brand is not None:
            lines.append(f"  - AI 검색 브랜드 언급: {brand}/30")

    return "\n".join(lines)


def _draft_email(company: dict, feedback: str = "") -> tuple[str, str]:
    """
    Use claude-sonnet-4-6 to draft the outreach email.
    Returns (subject, body).
    """
    corp_name = company.get("corp_name", "")
    geo_score = company.get("geo_score", "N/A")
    context_block = _format_company_context(company)

    feedback_section = ""
    if feedback:
        feedback_section = f"\n\n이전 이메일의 개선 요청사항:\n{feedback}\n위 피드백을 반영하여 더 나은 이메일을 작성해주세요."

    system_prompt = (
        "당신은 한국 B2B 영업 전문가입니다. "
        "반드시 한국어로만 이메일을 작성하세요. "
        "영어를 사용하지 마세요. "
        "전문적이고 간결한 한국 비즈니스 이메일 톤을 유지하세요."
    )

    user_prompt = f"""다음 기업 정보를 바탕으로 영업 아웃리치 이메일을 한국어로 작성해주세요.

[기업 데이터]
{context_block}

[이메일 구조]
1. 제목: "[{corp_name}] AI 경쟁력 진단 — 귀사의 AI 가시성 점수는 {geo_score}점입니다" (이 제목을 그대로 사용하세요)

2. 본문 구성:
   - 인사 및 발신자 소개: SDC (SKKU-Deloitte Consulting) 소개 포함
   - 핵심 발견: GEO 점수 {geo_score}/100 언급, 경쟁사 대비 현황 언급
   - 구체적 수치: 매출액, 영업이익률 등 위 데이터 직접 인용
   - 제안: 무료 AI 가시성 진단 보고서 제공 (2페이지 분량)
   - CTA: 회신 요청 (간결하게)
   - 서명: 김건희 | SDC (SKKU-Deloitte Consulting) 회장

[작성 지침]
- 전체 이메일을 한국어로 작성하세요
- 200-300자 이내로 간결하게
- 과도한 경어나 불필요한 인사말 없이 핵심만
- 수치를 구체적으로 언급하여 신뢰감 형성
- 제목은 위에 명시된 그대로 사용

다음 형식으로 응답하세요:
제목: [이메일 제목]
---
[이메일 본문]
{feedback_section}"""

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )

    raw = response.content[0].text.strip()

    # Parse subject and body
    if "---" in raw:
        parts = raw.split("---", 1)
        subject_line = parts[0].strip()
        body = parts[1].strip()
        # Extract just the subject text after "제목:"
        if subject_line.startswith("제목:"):
            subject = subject_line[3:].strip()
        else:
            subject = subject_line
    else:
        # Fallback: first line = subject
        lines = raw.splitlines()
        subject = lines[0].replace("제목:", "").strip()
        body = "\n".join(lines[1:]).strip()

    return subject, body


def _score_email(company: dict, subject: str, body: str) -> tuple[float, str]:
    """
    Use claude-haiku to score the email on three dimensions.
    Returns (average_score, feedback_string).
    """
    context_block = _format_company_context(company)

    prompt = f"""다음 영업 이메일을 평가해주세요. JSON 형식으로만 응답하세요.

[기업 데이터]
{context_block}

[이메일 제목]
{subject}

[이메일 본문]
{body}

평가 기준:
1. persuasiveness (0-10): 수신자가 회신하고 싶어질 만큼 설득력 있는가?
2. specificity (0-10): 실제 DART/GEO 데이터를 구체적으로 활용했는가?
3. professionalism (0-10): 적절한 한국 비즈니스 톤을 유지했는가?

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "persuasiveness": <score>,
  "specificity": <score>,
  "professionalism": <score>,
  "feedback": "<개선이 필요한 부분을 한국어로 간략히 설명>"
}}"""

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    try:
        # Strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        p = float(data.get("persuasiveness", 5))
        s = float(data.get("specificity", 5))
        pr = float(data.get("professionalism", 5))
        avg = round((p + s + pr) / 3, 2)
        feedback = data.get("feedback", "")
        return avg, feedback
    except Exception as e:
        print(f"    [haiku score parse error] {e} | raw: {raw[:200]}")
        return 7.0, ""


def generate_outreach_email(company: dict) -> dict:
    """
    Generates and self-refines a Korean outreach email for one company.

    Returns company dict + {
        "email_subject": str,
        "email_body": str,
        "email_score": float,
        "email_iterations": int
    }
    """
    corp_name = company.get("corp_name", "")
    print(f"\n[Outreach] Generating email for {corp_name}...")

    subject, body = _draft_email(company)
    score, feedback = _score_email(company, subject, body)
    iterations = 1

    print(f"  Iteration {iterations}: score={score}/10")

    while score < SCORE_THRESHOLD and iterations < MAX_ITERATIONS:
        print(f"  Score {score} < {SCORE_THRESHOLD} — improving (iter {iterations + 1})...")
        subject, body = _draft_email(company, feedback=feedback)
        score, feedback = _score_email(company, subject, body)
        iterations += 1
        print(f"  Iteration {iterations}: score={score}/10")

    print(f"  Final: score={score}/10 after {iterations} iteration(s)")

    result = {**company}
    result["email_subject"] = subject
    result["email_body"] = body
    result["email_score"] = score
    result["email_iterations"] = iterations
    return result


def generate_all_emails(companies: list[dict]) -> list[dict]:
    """Generate emails for all companies. 1s sleep between each."""
    results = []
    for i, company in enumerate(companies):
        generated = generate_outreach_email(company)
        results.append(generated)
        if i < len(companies) - 1:
            time.sleep(1)
    print(f"\nEmail generation complete: {len(results)} emails generated.")
    return results


if __name__ == "__main__":
    sample_company = {
        "corp_code": "000001",
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
        "geo_score": 55,
        "geo_breakdown": {
            "citability": 20,
            "crawler_access": 25,
            "brand_mention": 10,
        },
        "website_url": "https://www.soulbrain.co.kr",
    }

    print("Running outreach email generation for 1 sample company...\n")
    result = generate_outreach_email(sample_company)

    print("\n--- Generated Email ---")
    print(f"Subject: {result['email_subject']}")
    print(f"Score: {result['email_score']}/10 (after {result['email_iterations']} iteration(s))")
    print(f"\nBody:\n{result['email_body']}")
