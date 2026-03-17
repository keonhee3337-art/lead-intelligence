import os
import dart_fss as dart
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / '.env')

DART_API_KEY = os.getenv("DARTFSS_API_KEY")
if not DART_API_KEY:
    raise EnvironmentError("DARTFSS_API_KEY not found in .env")

dart.set_api_key(DART_API_KEY)

SAMPLE_COMPANIES = [
    "현대모비스", "LG이노텍", "삼성SDI", "한화솔루션", "OCI",
    "효성", "롯데케미칼", "SKC", "코오롱인더스트리", "GS칼텍스",
    "포스코케미칼", "일진머티리얼즈", "삼성전기", "DB하이텍", "파크시스템스",
    "비에이치", "원익IPS", "테크윙", "솔브레인", "동진쎄미켐"
]


def _extract_financials(corp) -> list[dict]:
    """Pull annual financials for a corp object. Returns list of yearly dicts."""
    try:
        fs = corp.extract_fs(bgn_de='20220101', end_de='20241231', report_tp='annual')
    except Exception as e:
        raise RuntimeError(f"extract_fs failed: {e}")

    records = []

    # fs is a FinancialStatement object; iterate over available years
    # fs['bs'], fs['is'], fs['cis'] — use income statement
    try:
        if hasattr(fs, 'show'):
            is_df = fs['is']
        else:
            is_df = fs.get('is') or fs.get('cis')
    except Exception:
        is_df = None

    if is_df is None or (hasattr(is_df, 'empty') and is_df.empty):
        return records

    # The DataFrame has account labels as index, years as columns
    # Column names are typically tuples or strings like '2023' / '20231231'
    try:
        cols = list(is_df.columns)
    except Exception:
        return records

    for col in cols:
        try:
            year_str = str(col).replace('(', '').replace(')', '').strip()
            # Extract 4-digit year
            year = None
            for part in year_str.split():
                if len(part) == 4 and part.isdigit():
                    year = int(part)
                    break
            if year is None and len(year_str) >= 4 and year_str[:4].isdigit():
                year = int(year_str[:4])
            if year is None:
                continue

            def _get_value(labels):
                for label in labels:
                    try:
                        row = is_df.loc[is_df.index.str.contains(label, na=False)]
                        if not row.empty:
                            val = row.iloc[0][col]
                            if val is not None and str(val).strip() not in ('', '-', 'nan'):
                                return float(str(val).replace(',', ''))
                    except Exception:
                        continue
                return None

            revenue = _get_value(['매출액', '수익(매출액)', '영업수익'])
            op_profit = _get_value(['영업이익'])

            if revenue is None:
                continue

            # Convert from KRW (units vary — dart-fss returns in 원, divide to get billions)
            revenue_bn = revenue / 1e9
            op_profit_bn = (op_profit / 1e9) if op_profit is not None else None
            op_margin = (op_profit_bn / revenue_bn * 100) if (op_profit_bn is not None and revenue_bn > 0) else None

            records.append({
                'year': year,
                'revenue_bn_krw': round(revenue_bn, 2),
                'operating_profit_bn_krw': round(op_profit_bn, 2) if op_profit_bn is not None else None,
                'operating_margin_pct': round(op_margin, 2) if op_margin is not None else None,
            })
        except Exception:
            continue

    return records


def screen_companies(
    sector: str,
    min_revenue_bn_krw: float = 100,
    max_revenue_bn_krw: float = 500
) -> list[dict]:
    """
    Search DART for Korean companies matching ICP criteria.

    Returns list of dicts:
        {corp_code, corp_name, revenue_bn_krw, operating_profit_bn_krw,
         operating_margin_pct, year, financials_history}

    sector: Korean sector name e.g. "제조업" (informational; DART search is by name)
    min/max_revenue: in billions KRW — filters on the most recent year available
    """
    from dart_fss.utils import find_by_corp_name

    results = []

    for name in SAMPLE_COMPANIES:
        try:
            corps = find_by_corp_name(name, exactly=True)
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
