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

CSV_DIR = Path.cwd() / "csv"
RAW_CSV = CSV_DIR / "relatedQueries.csv"
CLEAN_CSV = CSV_DIR / "relatedQueries_clean.csv"
TREND_CSV = CSV_DIR / "trend.csv"

# log init
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("daily-trends")


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")

def today_clean_dated_path() -> Path:
    return CSV_DIR / f"relatedQueries_clean_{today_yyyymmdd()}.csv"

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

#---------------------------api---------------------------
@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/get_daily_trends")
def get_daily_trends():
    """
    Return today's relatedQueries_clean_YYYYMMDD.csv as JSON (NO fallback).
    """
    try:
        p = today_clean_dated_path()
        if not p.exists():
            raise FileNotFoundError(
                f"{p.name} not found. Call POST /get_daily_trends/refresh first."
            )

        return {
            "file": p.name,
            "date": today_yyyymmdd(),
            "rows": read_clean_as_json(p),
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/get_daily_trends/refresh")
def refresh_daily_trends():
    """
    download -> clean -> update trend.csv -> delete raw -> rename clean to date
    then return today's relatedQueries_clean_YYYYMMDD.csv as JSON.
    """
    try:
        CSV_DIR.mkdir(parents=True, exist_ok=True)

        today_clean = today_clean_dated_path()
        if today_clean.exists():
            logger.info(
                "Daily trends already exist (%s) — skipping refresh",
                today_clean.name,
            )
            return {
                "file": today_clean.name,
                "date": today_yyyymmdd(),
                "rows": read_clean_as_json(today_clean),
            }
        
        # 1) Download raw relatedQueries.csv into csv/
        download_related_queries_only()

        if not RAW_CSV.exists():
            raise FileNotFoundError(f"Download finished but {RAW_CSV.name} not found in {CSV_DIR}")

        # 2) Clean into relatedQueries_clean.csv
        clean_related_queries(RAW_CSV, CLEAN_CSV)

        # 3) Update trend.csv, delete RAW, rename CLEAN -> CLEAN_YYYYMMDD.csv
        renamed_clean_path = update_trend_csv(
            trend_csv_path=TREND_CSV,
            clean_csv_path=CLEAN_CSV,
            raw_csv_path=RAW_CSV,
        )

        # Safety: ensure the renamed file is exactly today's YYYYMMDD file
        expected = today_clean_dated_path()
        if renamed_clean_path.resolve() != expected.resolve():
            # If you ever run refresh past midnight boundary, this makes it explicit
            raise RuntimeError(
                f"Renamed file is {renamed_clean_path.name}, but expected {expected.name}."
            )

        return {
            "file": expected.name,
            "date": today_yyyymmdd(),
            "rows": read_clean_as_json(expected),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_all_trends")
def get_all_trends():
    """
    Return csv/trend.csv as JSON.
    """
    try:
        if not TREND_CSV.exists():
            raise FileNotFoundError(f"{TREND_CSV.name} not found. Call refresh at least once.")

        return {
            "file": TREND_CSV.name,
            "rows": read_trend_as_json(TREND_CSV),
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
