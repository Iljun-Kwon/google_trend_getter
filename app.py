from __future__ import annotations

from pathlib import Path
from datetime import datetime
import pandas as pd
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from trend_download import download_related_queries_only
from process_related_queries import clean_related_queries
from update_trend_csv import update_trend_csv

app = FastAPI(title="Daily Trends API")

BASE_CSV_DIR = Path.cwd() / "csv"
ALLOWED_GEOS = {"KR", "US", "MX"}

# log init
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("daily-trends")


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")

def geo_dir(geo: str) -> Path:
    g = geo.upper()
    if g not in ALLOWED_GEOS:
        raise HTTPException(status_code=400, detail=f"geo must be one of {sorted(ALLOWED_GEOS)}")
    d = BASE_CSV_DIR / g
    d.mkdir(parents=True, exist_ok=True)
    return d

def today_clean_dated_path(gdir: Path) -> Path:
    return gdir / f"relatedQueries_clean_{today_yyyymmdd()}.csv"

def read_clean_as_json(path: Path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "query" not in df.columns or "value" not in df.columns:
        raise ValueError(f"Expected query,value columns in {path.name}")

    df["query"] = df["query"].astype(str).str.strip()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # Keep as int where possible; missing -> None
    rows = []
    for _, r in df.iterrows():
        v = r["value"]
        rows.append({"query": r["query"], "value": (None if pd.isna(v) else int(v))})
    return rows

def read_trend_as_json(path: Path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["query"] = df["query"].astype(str).str.strip()

    # Force blanks -> 100, numeric columns -> int
    for c in df.columns:
        if c != "query":
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(100).round().astype(int)

    return df.to_dict(orient="records")

def _refresh_one_geo(geo: str):
    """
    download -> clean -> update trend.csv -> delete raw -> rename clean to date
    then return today's relatedQueries_clean_YYYYMMDD.csv as JSON.
    """
    gdir = geo_dir(geo)

    raw_csv = gdir / "relatedQueries.csv"
    clean_csv = gdir / "relatedQueries_clean.csv"
    trend_csv = gdir / "trend.csv"
    today_clean = today_clean_dated_path(gdir)

    if today_clean.exists():
        logger.info(
            "[%s] Daily trends already exist (%s) — skipping refresh",
            geo.upper(),
            today_clean.name,
        )
        return {
            "geo": geo.upper(),
            "file": today_clean.name,
            "date": today_yyyymmdd(),
            "rows": read_clean_as_json(today_clean),
        }
    
    # 1) Download raw relatedQueries.csv into csv/{GEO}/
    downloaded_raw = download_related_queries_only(geo.upper(), gdir)
    if downloaded_raw.resolve() != raw_csv.resolve():
        downloaded_raw.replace(raw_csv)

    if not raw_csv.exists():
        raise FileNotFoundError(f"Download finished but {raw_csv.name} not found in {gdir}")

    # 2) Clean into relatedQueries_clean.csv
    clean_related_queries(raw_csv, clean_csv)

    # 3) Update trend.csv, delete RAW, rename CLEAN -> CLEAN_YYYYMMDD.csv
    renamed_clean_path = update_trend_csv(
        trend_csv_path=trend_csv,
        clean_csv_path=clean_csv,
        raw_csv_path=raw_csv,
    )

    # Safety: ensure the renamed file is exactly today's YYYYMMDD file
    expected = today_clean
    if renamed_clean_path.resolve() != expected.resolve():
        # If you ever run refresh past midnight boundary, this makes it explicit
        raise RuntimeError(
            f"Renamed file is {renamed_clean_path.name}, but expected {expected.name}."
        )

    return {
        "geo": geo.upper(),
        "file": expected.name,
        "date": today_yyyymmdd(),
        "rows": read_clean_as_json(expected),
    }

#---------------------------api---------------------------
@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"ok": True, "geos": sorted(ALLOWED_GEOS)}

@app.get("/{geo}/get_daily_trends")
def get_daily_trends(geo: str):
    """
    Return today's relatedQueries_clean_YYYYMMDD.csv as JSON (NO fallback).
    """
    try:
        gdir = geo_dir(geo)
        p = today_clean_dated_path(gdir)
        if not p.exists():
            raise FileNotFoundError(
                f"{p.name} not found. Call POST /{geo}/get_daily_trends/refresh first."
            )
        return {
            "geo": geo.upper(),
            "file": p.name,
            "date": today_yyyymmdd(),
            "rows": read_clean_as_json(p),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/all/get_daily_trends/refresh")
def refresh_all_daily_trends():
    """
    Refresh KR, US, MX sequentially.
    """
    results = []

    for geo in sorted(ALLOWED_GEOS):
        try:
            r = _refresh_one_geo(geo.upper())
            results.append(r)
        except Exception as e:
            results.append({
                "geo": geo,
                "status": "error",
                "error": str(e),
            })

    return {
        "date": today_yyyymmdd(),
        "results": results,
    }

@app.post("/{geo}/get_daily_trends/refresh")
def refresh_daily_trends(geo: str):
    try:
        result = _refresh_one_geo(geo.upper())
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/{geo}/get_all_trends")
def get_all_trends(geo: str):
    """
    Return csv/trend.csv as JSON.
    """
    try:
        gdir = geo_dir(geo)
        trend_csv = gdir / "trend.csv"
        if not trend_csv.exists():
            raise FileNotFoundError(f"{trend_csv.name} not found for {geo.upper()}. Call refresh at least once.")
        return {
            "geo": geo.upper(),
            "file": trend_csv.name,
            "rows": read_trend_as_json(trend_csv),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))