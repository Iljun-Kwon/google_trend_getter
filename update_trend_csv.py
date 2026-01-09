from __future__ import annotations

from pathlib import Path
from datetime import datetime
import pandas as pd


def _date_label_dash() -> str:
    # For trend.csv column
    return datetime.now().strftime("%Y-%m-%d")


def _date_label_compact() -> str:
    # For filename suffix
    return datetime.now().strftime("%Y%m%d")


def _sorted_datetime_columns(cols: list[str]) -> list[str]:
    """
    Sort column names by datetime if parseable; unparseable columns go last.
    """
    parsed = []
    unparsed = []
    for c in cols:
        try:
            dt = pd.to_datetime(c, errors="raise")
            parsed.append((c, dt))
        except Exception:
            unparsed.append(c)

    parsed_sorted = [c for c, _ in sorted(parsed, key=lambda x: x[1])]
    return parsed_sorted + unparsed


def update_trend_csv(
    trend_csv_path: str | Path = "csv/trend.csv",
    clean_csv_path: str | Path = "csv/relatedQueries_clean.csv",
    raw_csv_path: str | Path = "csv/relatedQueries.csv",
    date_col: str | None = None,
) -> Path:
    trend_csv_path = Path(trend_csv_path)
    clean_csv_path = Path(clean_csv_path)
    raw_csv_path = Path(raw_csv_path)
    date_col = date_col or _date_label_dash()
    date_suffix = _date_label_compact()

    # --- Load daily clean CSV ---
    if clean_csv_path.exists() and clean_csv_path.stat().st_size > 0:
        d = pd.read_csv(clean_csv_path, encoding="utf-8-sig")

        if "query" not in d.columns or "value" not in d.columns:
            raise ValueError(
                f"Expected columns query,value in {clean_csv_path}, got {list(d.columns)}"
            )

        d["query"] = d["query"].astype(str).str.strip()
        d["value"] = pd.to_numeric(d["value"], errors="coerce")

        daily_df = (
            d.dropna(subset=["query"])
             .drop_duplicates(subset=["query"], keep="last")[["query", "value"]]
        )
    else:
        daily_df = pd.DataFrame(columns=["query", "value"])

    # --- Load or create trend.csv ---
    if trend_csv_path.exists() and trend_csv_path.stat().st_size > 0:
        trend = pd.read_csv(trend_csv_path, encoding="utf-8-sig")

        if "query" not in trend.columns:
            raise ValueError(f"trend.csv must have a 'query' column")

        trend["query"] = trend["query"].astype(str).str.strip()
    else:
        trend = pd.DataFrame({"query": []})

    # Ensure today's column exists
    if date_col not in trend.columns:
        trend[date_col] = pd.NA

    # Convert all date columns to numeric
    for c in [col for col in trend.columns if col != "query"]:
        trend[c] = pd.to_numeric(trend[c], errors="coerce")

    # ---------- Merge today's data ----------
    trend = trend.merge(
        daily_df.rename(columns={"value": "__today_value__"}),
        on="query",
        how="outer",
    )

    # Fill historical blanks with 100
    for c in [col for col in trend.columns if col not in ("query", "__today_value__", date_col)]:
        trend[c] = pd.to_numeric(trend[c], errors="coerce").fillna(100)

    # Today's rule: value + 100, else 100
    today_val = pd.to_numeric(trend["__today_value__"], errors="coerce")
    trend[date_col] = today_val.add(100).where(today_val.notna(), 100)

    # Cleanup helper column
    trend = trend.drop(columns=["__today_value__"])

    # Force ints everywhere
    for c in [col for col in trend.columns if col != "query"]:
        trend[c] = pd.to_numeric(trend[c], errors="coerce").fillna(100).round().astype(int)

    # Reorder columns
    sorted_dates = _sorted_datetime_columns([c for c in trend.columns if c != "query"])
    trend = trend[["query"] + sorted_dates]

    # Sort rows
    trend = trend.sort_values("query").reset_index(drop=True)

    trend_csv_path.parent.mkdir(parents=True, exist_ok=True)
    trend.to_csv(trend_csv_path, index=False, encoding="utf-8-sig")
    
    # ---------- Save trend.csv ----------
    trend_csv_path.parent.mkdir(parents=True, exist_ok=True)
    trend.to_csv(trend_csv_path, index=False, encoding="utf-8-sig")

    # ---------- Post-processing ----------
    # 1) Delete raw relatedQueries.csv
    if raw_csv_path.exists():
        raw_csv_path.unlink()

    # 2) Rename clean file with date suffix
    renamed = clean_csv_path.with_name(f"relatedQueries_clean_{date_suffix}.csv")

    if clean_csv_path.exists():
        # replace() overwrites if file exists (more robust than rename on Windows)
        clean_csv_path.replace(renamed)
    else:
        # If the clean file is missing, something upstream failed
        raise FileNotFoundError(f"Expected clean CSV not found: {clean_csv_path}")

    return renamed

#if __name__ == "__main__":
#    update_trend_csv()
