"""
Korean SME Lead Intelligence — Streamlit UI
"""

import concurrent.futures
from pathlib import Path
from dotenv import load_dotenv

for _p in [Path(__file__).parent / '.env', Path(__file__).parent.parent / '.env', Path(__file__).parent.parent.parent / '.env']:
    if _p.exists():
        load_dotenv(dotenv_path=_p)
        break

import streamlit as st

# Streamlit Cloud: load secrets into env before any pipeline imports
import os
for _key in ["PERPLEXITY_API_KEY", "ANTHROPIC_API_KEY", "DARTFSS_API_KEY"]:
    if not os.environ.get(_key):
        try:
            os.environ[_key] = st.secrets[_key]
        except (KeyError, FileNotFoundError):
            pass

st.set_page_config(
    page_title="Korean SME Lead Intelligence",
    page_icon="🔍",
    layout="wide",
)



# ------------------------------------------------------------------
# Sidebar — ICP Filter
# ------------------------------------------------------------------
with st.sidebar:
    st.header("ICP Filter")

    min_revenue = st.slider(
        "Min Revenue (Billion KRW)",
        min_value=10,
        max_value=500,
        value=50,
        step=10,
    )

    max_revenue = st.slider(
        "Max Revenue (Billion KRW)",
        min_value=100,
        max_value=2000,
        value=1000,
        step=50,
    )

    top_n = st.slider(
        "Top N Companies",
        min_value=5,
        max_value=20,
        value=10,
        step=1,
    )

    run_button = st.button("Run Lead Scan", type="primary", use_container_width=True)

# ------------------------------------------------------------------
# Main area — header
# ------------------------------------------------------------------
st.title("Korean SME Lead Intelligence")
st.caption(
    "Automated DART screening + AI readiness scoring + GEO audit + outreach generation for Korean manufacturers."
)

# ------------------------------------------------------------------
# Run pipeline on button click
# ------------------------------------------------------------------
if run_button:
    st.session_state.pop("results", None)
    st.session_state.pop("excel_path", None)

    try:
        with st.spinner(
            "Scanning 5 Korean manufacturers via DART (3-5 min). "
            "Financial data extraction runs in the background — please wait."
        ):
            from pipeline import run_full_pipeline
            PIPELINE_TIMEOUT = 300  # 5-minute hard cap
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    run_full_pipeline,
                    min_revenue_bn_krw=float(min_revenue),
                    max_revenue_bn_krw=float(max_revenue),
                    top_n=top_n,
                )
                try:
                    companies, excel_path = future.result(timeout=PIPELINE_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    raise TimeoutError(
                        f"Pipeline exceeded {PIPELINE_TIMEOUT}s. "
                        "Try reducing Top N or check network/API connectivity."
                    )

        if not companies:
            st.warning(
                "No companies returned by the pipeline. "
                "Try widening the revenue range or check your API keys."
            )
        else:
            st.session_state["results"] = companies
            st.session_state["excel_path"] = excel_path
            st.success(f"Pipeline complete — {len(companies)} companies processed.")

    except TimeoutError as e:
        st.error(str(e))
    except EnvironmentError as e:
        st.error(
            f"Environment error: {e}\n\n"
            "Check that DARTFSS_API_KEY and PERPLEXITY_API_KEY are set in your .env file."
        )
    except Exception as e:
        st.error(str(e))

# ------------------------------------------------------------------
# Display results from session_state
# ------------------------------------------------------------------
if "results" in st.session_state:
    companies = st.session_state["results"]
    excel_path = st.session_state.get("excel_path", "")

    # ---------------------------------------------------------------
    # Section 1 — Top Companies table
    # ---------------------------------------------------------------
    st.subheader("Top Companies")

    import pandas as pd

    table_rows = []
    for c in companies:
        table_rows.append({
            "corp_name": c.get("corp_name", ""),
            "readiness_score": c.get("readiness_score"),
            "geo_score": c.get("geo_score"),
            "revenue_bn_krw": c.get("revenue_bn_krw"),
            "operating_margin": c.get("operating_margin_pct"),
            "website_url": c.get("website_url") or "",
        })

    df = pd.DataFrame(table_rows)
    if not df.empty and "readiness_score" in df.columns:
        df = df.sort_values("readiness_score", ascending=False).reset_index(drop=True)

    st.dataframe(df, use_container_width=True)

    st.divider()

    # ---------------------------------------------------------------
    # Section 2 — GEO Audit Breakdown
    # ---------------------------------------------------------------
    st.subheader("GEO Audit Breakdown")

    for c in companies:
        with st.expander(c.get("corp_name", "")):
            geo_score = c.get("geo_score", "N/A")
            breakdown = c.get("geo_breakdown", {})
            citability = breakdown.get("citability", "N/A")
            crawler = breakdown.get("crawler_access", "N/A")
            brand = breakdown.get("brand_mention", "N/A")
            website = c.get("website_url") or "Not found"

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("GEO Score", f"{geo_score}/100")
            col2.metric("Citability", f"{citability}/40")
            col3.metric("Crawler Access", f"{crawler}/30")
            col4.metric("Brand Mention", f"{brand}/30")
            st.write(f"Website: {website}")

    st.divider()

    # ---------------------------------------------------------------
    # Section 3 — Outreach Emails
    # ---------------------------------------------------------------
    st.subheader("Outreach Emails")

    for c in companies:
        with st.expander(c.get("corp_name", "")):
            subject = c.get("email_subject", "")
            body = c.get("email_body", "")
            score = c.get("email_score", "N/A")

            st.markdown(f"**Subject:** {subject}")
            st.text_area(
                "Email body",
                value=body,
                height=200,
                disabled=True,
                key=f"email_{c.get('corp_name', '')}",
                label_visibility="collapsed",
            )
            st.caption(f"Email quality score: {score}/10")

    st.divider()

    # ---------------------------------------------------------------
    # Section 4 — Download
    # ---------------------------------------------------------------
    st.subheader("Download Report")

    if excel_path and Path(excel_path).exists():
        with open(excel_path, "rb") as f:
            excel_bytes = f.read()
        st.download_button(
            label="Download Excel Report",
            data=excel_bytes,
            file_name="lead_intelligence_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("Excel report not available. Run the pipeline to generate it.")

else:
    # Placeholder before first run
    st.info(
        "Set your ICP filters in the sidebar and click **Run Lead Scan** to start. "
        "The pipeline will screen DART-listed Korean manufacturers, score AI readiness, "
        "run a GEO audit, and generate Korean outreach emails."
    )
