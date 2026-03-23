import os
import functools
import concurrent.futures
import dart_fss as dart
from pathlib import Path
from dotenv import load_dotenv

for _p in [Path(__file__).parent / '.env', Path(__file__).parent.parent / '.env', Path(__file__).parent.parent.parent / '.env']:
    if _p.exists():
        load_dotenv(dotenv_path=_p)
        break

DART_API_KEY = os.getenv("DARTFSS_API_KEY")
if DART_API_KEY:
    dart.set_api_key(DART_API_KEY)
# Key will be validated at runtime in screen_companies() if missing


@functools.lru_cache(maxsize=1)
def _get_corp_list():
    """Fetch and cache the full DART corp list. Called once per process."""
    return dart.get_corp_list()


# Fallback company list used only when DART keyword search returns no results
_FALLBACK_COMPANIES = [
    "삼성전기", "솔브레인", "현대모비스", "LG이노텍", "DB하이텍",
]


_FS_TIMEOUT = 45  # seconds per company -- avoid hanging forever


def _extract_financials(corp) -> list[dict]:
    """Pull annual financials for a corp object. Returns list of yearly dicts."""
    def _fetch():
        return corp.extract_fs(bgn_de='20220101', end_de='20241231', report_tp='annual')

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
            _future = _ex.submit(_fetch)
            fs = _future.result(timeout=_FS_TIMEOUT)
    except concurrent.futures.TimeoutError:
        raise RuntimeError(f"extract_fs timed out after {_FS_TIMEOUT}s")
    except Exception as e:
        raise RuntimeError(f"extract_fs failed: {e}")

    records = []

    # dart-fss returns a FinancialStatement with MultiIndex columns.
    # Try 'is' (income statement) first -- has revenue + operating profit.
    # Fall back to 'cis' (comprehensive income) if 'is' is None.
    is_df = None
    for key in ('is', 'cis'):
        try:
            candidate = fs[key]
            if candidate is not None and not candidate.empty:
                is_df = candidate
                break
        except Exception:
            continue

    if is_df is None:
        return records

    try:
        # Find the label_ko column -- second level of MultiIndex is the field name
        stmt_title = next(c[0] for c in is_df.columns if c[1] == 'label_ko')
        label_col = (stmt_title, 'label_ko')

        # Find year columns -- second level contains tuples with financial statement type
        import re as _re
        year_cols = [
            c for c in is_df.columns
            if isinstance(c[1], tuple) and any('재무제표' in str(x) for x in c[1])
        ]
    except Exception:
        return records

    for year_col in year_cols:
        try:
            # Parse year from the date range string e.g. '20230101-20231231'
            date_str = str(year_col[0])
            year_match = _re.search(r'(\d{4})\d{4}-(\d{4})\d{4}', date_str)
            if not year_match:
                continue
            year = int(year_match.group(2))  # end year

            def _get_value(target_labels):
                for target in target_labels:
                    mask = is_df[label_col].astype(str).str.strip() == target
                    rows = is_df[mask]
                    if not rows.empty:
                        val = rows.iloc[0][year_col]
                        if val is not None and str(val).strip() not in ('', '-', 'nan', 'None'):
                            try:
                                return float(str(val).replace(',', ''))
                            except ValueError:
                                continue
                return None

            revenue = _get_value(['매출액', '수익(매출액)', '영업수익', '매출'])
            op_profit = _get_value(['영업이익', '영업이익(손실)'])

            if revenue is None:
                continue

            # dart-fss values are in KRW -- divide by 1e9 for billions
            revenue_bn = revenue / 1e9
            op_profit_bn = (op_profit / 1e9) if op_profit is not None else None
            op_margin = (
                round(op_profit_bn / revenue_bn * 100, 2)
                if (op_profit_bn is not None and revenue_bn > 0)
                else None
            )

            records.append({
                'year': year,
                'revenue_bn_krw': round(revenue_bn, 2),
                'operating_profit_bn_krw': round(op_profit_bn, 2) if op_profit_bn is not None else None,
                'operating_margin_pct': op_margin,
            })
        except Exception:
            continue

    return records


def screen_companies(
    sector: str,
    min_revenue_bn_krw: float = 100,
    max_revenue_bn_krw: float = 500,
    top_n: int = 5,
) -> list[dict]:
    """
    Search DART for Korean companies matching ICP criteria.

    Returns list of dicts:
        {corp_code, corp_name, revenue_bn_krw, operating_profit_bn_krw,
         operating_margin_pct, year, financials_history}

    sector: Korean sector name e.g. "manufacturing" -- used for DART keyword search
    min/max_revenue: in billions KRW -- filters on the most recent year available
    top_n: max companies to return
    """
    # Ensure DART API key is set (handles Streamlit Cloud where secrets load after module import)
    key = os.getenv("DARTFSS_API_KEY")
    if not key:
        raise EnvironmentError("DARTFSS_API_KEY not set. Add it to Streamlit Cloud secrets.")
    dart.set_api_key(key)
    corp_list = _get_corp_list()
    results = []

    # Build candidate list from DART keyword search on sector, fall back to hardcoded list
    sector_results = corp_list.find_by_corp_name(sector, exactly=False)
    candidate_names = (
        [c.corp_name for c in sector_results[:max(top_n * 3, 15)]]
        if sector_results
        else _FALLBACK_COMPANIES
    )

    for name in candidate_names:
        try:
            corps = corp_list.find_by_corp_name(name, exactly=True)
            if not corps:
                print(f"  [skip] {name}: not found")
                continue

            corp = corps[0]
            financials = _extract_financials(corp)

            if not financials:
                print(f"  [skip] {name}: no financials extracted")
                continue

            # Use most recent year
            latest = sorted(financials, key=lambda x: x['year'], reverse=True)[0]
            revenue = latest['revenue_bn_krw']

            if not (min_revenue_bn_krw <= revenue <= max_revenue_bn_krw):
                print(f"  [filter] {name}: revenue {revenue:.1f}B KRW out of range")
                continue

            results.append({
                'corp_code': corp.corp_code,
                'corp_name': corp.corp_name,
                'revenue_bn_krw': latest['revenue_bn_krw'],
                'operating_profit_bn_krw': latest['operating_profit_bn_krw'],
                'operating_margin_pct': latest['operating_margin_pct'],
                'year': latest['year'],
                'financials_history': financials,
            })
            print(f"  [ok] {name}: {revenue:.1f}B KRW ({latest['year']})")

        except Exception as e:
            print(f"  [error] {name}: {e}")
            continue

    results = results[:top_n]
    print(f"\nScreener done: {len(results)} companies passed filter ({sector}, {min_revenue_bn_krw}-{max_revenue_bn_krw}B KRW)")
    return results


if __name__ == "__main__":
    print("Running DART screener...\n")
    results = screen_companies("제조업", min_revenue_bn_krw=50, max_revenue_bn_krw=1000)

    print("\n--- Top 5 Results ---")
    for r in results[:5]:
        print(
            f"{r['corp_name']} ({r['year']}) | "
            f"Revenue: {r['revenue_bn_krw']:.1f}B KRW | "
            f"OP Margin: {r['operating_margin_pct']}%"
        )
