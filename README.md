# Korean SME Lead Intelligence

Automated lead generation and AI discoverability audit for Korean manufacturers -- built to identify which Korean SMEs are most likely to buy AI/digital transformation services, and generate personalized Korean outreach.

## What It Does

This system screens DART-listed Korean companies by revenue, scores each company on AI readiness using four weighted dimensions, runs a GEO (generative engine optimization) audit to measure how visible each company is to LLMs like GPT-4 and Claude, and generates a personalized Korean B2B outreach email per company. Output is a ranked Excel report with email drafts ready to send.

**Use case:** A consulting firm or B2B service provider wants to identify which Korean manufacturers are most likely to buy AI/digital transformation services -- and then pitch them with data.

## Architecture

```
ICP filter (revenue range, sector)
        |
        v
[DART Screener] -- dart-fss -> Korean company financials (20 candidates)
        |
        v
[AI Readiness Scorer] -- weighted 4-dimension score -> top 10 ranked
        |
        v
[GEO Audit Agent] -- Perplexity + robots.txt + HTML analysis -> citability score per company
        |
        v
[Outreach Generator] -- claude-sonnet-4-6 draft + claude-haiku self-refine loop -> Korean email per company
        |
        v
Excel export: rankings + outreach drafts
```

## GEO Audit -- 3 Checks

GEO (generative engine optimization) measures how findable and citable a company is in AI-generated search results. This matters because Korean SMEs are systematically underrepresented in LLM outputs -- they have websites but no structured content that AI systems can cite.

| Check | Max Score | What It Measures |
|---|---|---|
| Citability | 40 | Rich-text paragraphs (>50 words each) on the company website -- these are what LLMs pull as citations |
| Crawler Access | 30 | robots.txt allows or blocks GPTBot, ClaudeBot, PerplexityBot -- each blocked bot = -10 pts |
| Brand Mention | 30 | Perplexity sonar query in Korean AI/digital transformation context -- company name appears in response = 20 pts |

**Total GEO score = sum of three checks (max 100).**

A score below 50 means the company is essentially invisible to AI-powered search tools -- a direct pitch point for GEO consulting services.

## AI Readiness Score -- 4 Dimensions

| Dimension | Weight | Logic |
|---|---|---|
| Financial health | 30 pts | Operating margin > 20% = full score |
| Growth trajectory | 30 pts | 3Y revenue CAGR > 10% = full score |
| Company size signal | 20 pts | 100-500B KRW sweet spot -- budget present, not too complex to sell into |
| DART disclosure | 20 pts | Proxy for transparency and data recency |

## Tech Stack

| Tool | Role |
|---|---|
| dart-fss | DART Open API wrapper -- Korean company financials (revenue, operating profit, 3Y history) |
| Perplexity sonar | GEO brand mention check + website URL discovery |
| claude-sonnet-4-6 | Korean B2B outreach email drafting |
| claude-haiku-4-5 | Email scoring (persuasiveness, specificity, professionalism) and self-refinement |
| Python | Core pipeline, pandas, numpy |
| openpyxl | Excel report generation -- two sheets: Rankings + Outreach |
| Streamlit | Interactive UI -- ICP filter sidebar, GEO breakdown, email viewer, download button |

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API keys in .env (one level up from this directory)
# DARTFSS_API_KEY=...
# PERPLEXITY_API_KEY=...
# ANTHROPIC_API_KEY=...

# 3. Run the Streamlit app
streamlit run app.py

# Or run the pipeline directly from the terminal
python pipeline.py
```

## Business Context -- The AI Discoverability Gap for Korean SMEs

Most Korean manufacturers with 50-1000B KRW revenue have corporate websites but score poorly in AI-powered search results. When a potential enterprise buyer or consulting firm asks an LLM "who are the leading Korean precision parts manufacturers?" -- the answer rarely includes mid-market companies, even if they are strong businesses with good financials.

This creates a concrete sales angle: "Your GEO score is 35/100. Here is what that means for your pipeline, and here is what we can fix in 30 days."

This tool automates the research and outreach that would normally take a junior analyst 2-3 days per company.

## Project Files

```
lead-intelligence/
  dart_screener.py        -- Stage 1: DART API screening
  ai_readiness_scorer.py  -- Stage 2: 4-dimension scoring
  geo_audit.py            -- Stage 3: GEO citability audit
  outreach_generator.py   -- Stage 4: Korean email generation + haiku self-refine
  export.py               -- Excel export (Rankings + Outreach sheets)
  pipeline.py             -- Full orchestrator (runs all 4 stages)
  app.py                  -- Streamlit UI
  output/                 -- Generated Excel reports
```

## Author

**Keonhee Kim (Kim Keonhee)**
SKKU Business Administration | SDC (SKKU-Deloitte Consulting) President
GitHub: [keonhee3337-art](https://github.com/keonhee3337-art)

Keywords: DART, Korean SME, lead generation, GEO, generative engine optimization, AI readiness, LLM citability, agentic AI, claude-sonnet, Perplexity API, SKKU, consulting AI automation
