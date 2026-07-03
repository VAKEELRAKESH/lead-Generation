"""
dashboard_service.py
---------------------
Pure data-access / business-logic layer for the Lead Generation Dashboard.

This module ONLY reads from output/final_ai_leads.csv. It never writes to it
and never touches main.py / crawler.py / lead_cleaner.py, so the existing
crawling pipeline keeps working exactly as before.

Every public function in this file is defensive: if the CSV does not exist
yet (the crawler hasn't been run), every function returns an empty / zeroed
result instead of raising, so the dashboard can show
"No leads generated yet." instead of crashing.
"""

from __future__ import annotations

import io
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# dashboard/ lives at <project_root>/dashboard, so the project root is one
# level up from this file's directory.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# Allow overriding via env var (handy for Docker volumes / tests) while
# defaulting to the real pipeline output location.
CSV_PATH = os.environ.get(
    "LEADS_CSV_PATH",
    os.path.join(PROJECT_ROOT, "output", "final_ai_leads.csv"),
)

NO_DATA_MESSAGE = "No leads generated yet."

# ---------------------------------------------------------------------------
# Column mapping: raw CSV header -> internal snake_case field name
# ---------------------------------------------------------------------------

RAW_COLUMNS = [
    "business_name",
    "phone",
    "website",
    "address",
    "instagram",
    "facebook",
    "linkedin",
    "email",
    "city",
    "Has Website",
    "Has Email",
    "Has Social Media",
    "Contact Completeness %",
    "Lead Score",
    "Priority",
    "spin",
    "scraped_at",
]

RENAME_MAP = {
    "Contact Completeness %": "contact_completeness",
    "Lead Score": "lead_score",
    "Priority": "priority",
    "Has Website": "has_website",
    "Has Email": "has_email",
    "Has Social Media": "has_social_media",
}

STRING_FIELDS = [
    "business_name",
    "phone",
    "website",
    "address",
    "instagram",
    "facebook",
    "linkedin",
    "email",
    "city",
    "has_website",
    "has_email",
    "has_social_media",
    "priority",
    "spin",
    "scraped_at",
]

TABLE_FIELDS = [
    "id",
    "business_name",
    "phone",
    "email",
    "website",
    "instagram",
    "facebook",
    "linkedin",
    "lead_score",
    "priority",
    "contact_completeness",
    "spin",
    "scraped_at",
]

DETAIL_EXTRA_FIELDS = ["address", "city", "has_website", "has_email", "has_social_media"]

VALID_PRIORITIES = {"Hot", "Warm", "Cold"}

SCORE_BUCKETS = [
    ("0-20", 0, 20),
    ("21-40", 21, 40),
    ("41-60", 41, 60),
    ("61-80", 61, 80),
    ("81-100", 81, 100),
]

COMPLETENESS_BUCKETS = [
    ("0-25%", 0, 25),
    ("26-50%", 26, 50),
    ("51-75%", 51, 75),
    ("76-100%", 76, 100),
]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def csv_exists() -> bool:
    return os.path.isfile(CSV_PATH)


def load_leads() -> Optional[pd.DataFrame]:
    """
    Load and normalize the leads CSV.

    Returns None if the file does not exist (or is empty / unreadable),
    so callers can show the "No leads generated yet." state.
    """
    if not csv_exists():
        return None

    try:
        df = pd.read_csv(CSV_PATH)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return None

    if df.empty:
        return None

    df = df.rename(columns=RENAME_MAP)

    # Make sure every expected internal column exists, even if the CSV is
    # missing one (older runs, partial pipeline, etc.)
    for col in [
        "business_name", "phone", "website", "address", "instagram",
        "facebook", "linkedin", "email", "city", "has_website", "has_email",
        "has_social_media", "contact_completeness", "lead_score", "priority",
        "spin", "scraped_at",
    ]:
        if col not in df.columns:
            df[col] = "Legacy Run" if col == "spin" else ("" if col in STRING_FIELDS else 0)

    # Clean string columns
    for col in STRING_FIELDS:
        df[col] = df[col].fillna("").astype(str).str.strip()

    # Clean numeric columns
    df["lead_score"] = pd.to_numeric(df["lead_score"], errors="coerce").fillna(0)
    df["contact_completeness"] = pd.to_numeric(
        df["contact_completeness"], errors="coerce"
    ).fillna(0)

    # Normalize priority casing / unknowns
    df["priority"] = df["priority"].where(df["priority"].isin(VALID_PRIORITIES), "Cold")

    df = df.reset_index(drop=True)
    df["id"] = df.index

    return df


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> Dict[str, Any]:
    df = load_leads()

    if df is None:
        return {
            "has_data": False,
            "message": NO_DATA_MESSAGE,
            "total_leads": 0,
            "hot_leads": 0,
            "warm_leads": 0,
            "cold_leads": 0,
            "avg_score": 0,
            "avg_completeness": 0,
        }

    priority_counts = df["priority"].value_counts()

    return {
        "has_data": True,
        "message": None,
        "total_leads": int(len(df)),
        "hot_leads": int(priority_counts.get("Hot", 0)),
        "warm_leads": int(priority_counts.get("Warm", 0)),
        "cold_leads": int(priority_counts.get("Cold", 0)),
        "avg_score": round(float(df["lead_score"].mean()), 1),
        "avg_completeness": round(float(df["contact_completeness"].mean()), 1),
    }


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _bucket_counts(series: pd.Series, buckets: List[Tuple[str, int, int]]) -> Dict[str, int]:
    result = {}
    for label, low, high in buckets:
        result[label] = int(((series >= low) & (series <= high)).sum())
    return result


def get_charts() -> Dict[str, Any]:
    df = load_leads()

    if df is None:
        return {
            "has_data": False,
            "message": NO_DATA_MESSAGE,
            "priority_distribution": {"Hot": 0, "Warm": 0, "Cold": 0},
            "score_distribution": {label: 0 for label, _, _ in SCORE_BUCKETS},
            "completeness_distribution": {label: 0 for label, _, _ in COMPLETENESS_BUCKETS},
        }

    priority_counts = df["priority"].value_counts()
    priority_distribution = {
        "Hot": int(priority_counts.get("Hot", 0)),
        "Warm": int(priority_counts.get("Warm", 0)),
        "Cold": int(priority_counts.get("Cold", 0)),
    }

    score_distribution = _bucket_counts(df["lead_score"], SCORE_BUCKETS)
    completeness_distribution = _bucket_counts(df["contact_completeness"], COMPLETENESS_BUCKETS)

    return {
        "has_data": True,
        "message": None,
        "priority_distribution": priority_distribution,
        "score_distribution": score_distribution,
        "completeness_distribution": completeness_distribution,
    }


# ---------------------------------------------------------------------------
# Filtering / sorting / pagination (shared by /api/leads and exports)
# ---------------------------------------------------------------------------

SORTABLE_COLUMNS = {
    "business_name", "phone", "email", "website", "lead_score",
    "priority", "contact_completeness",
}


def get_unique_spins() -> List[str]:
    """Return a list of all unique spin values in the leads database."""
    df = load_leads()
    if df is None or "spin" not in df.columns:
        return []
    spins = df["spin"].dropna().unique()
    # Sort them nicely, ignoring empty ones
    return sorted([str(s) for s in spins if str(s).strip()])


def apply_filters(
    df: pd.DataFrame,
    search: Optional[str] = None,
    priority: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    spin: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    filtered = df

    if search:
        s = search.strip().lower()
        if s:
            mask = (
                filtered["business_name"].str.lower().str.contains(s, na=False)
                | filtered["phone"].str.lower().str.contains(s, na=False)
                | filtered["email"].str.lower().str.contains(s, na=False)
                | filtered["website"].str.lower().str.contains(s, na=False)
                | filtered["city"].str.lower().str.contains(s, na=False)
            )
            filtered = filtered[mask]

    if priority and priority.lower() != "all":
        filtered = filtered[filtered["priority"].str.lower() == priority.lower()]

    if min_score is not None:
        filtered = filtered[filtered["lead_score"] >= min_score]

    if max_score is not None:
        filtered = filtered[filtered["lead_score"] <= max_score]

    if spin and spin.lower() != "all":
        filtered = filtered[filtered["spin"].str.lower() == spin.lower()]

    if start_date:
        # compare dates (YYYY-MM-DD)
        filtered = filtered[filtered["scraped_at"].str.slice(0, 10) >= start_date]

    if end_date:
        filtered = filtered[filtered["scraped_at"].str.slice(0, 10) <= end_date]

    return filtered


def apply_sort(df: pd.DataFrame, sort_by: Optional[str], sort_order: Optional[str]) -> pd.DataFrame:
    if not sort_by or sort_by not in SORTABLE_COLUMNS:
        sort_by = "lead_score"
    ascending = (sort_order or "desc").lower() == "asc"

    if df[sort_by].dtype == object:
        return df.sort_values(
            by=sort_by, ascending=ascending, key=lambda c: c.str.lower(), kind="mergesort"
        )
    return df.sort_values(by=sort_by, ascending=ascending, kind="mergesort")


def get_filtered_leads(
    search: Optional[str] = None,
    priority: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    spin: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """Returns the full filtered+sorted DataFrame (no pagination), or None if no data."""
    df = load_leads()
    if df is None:
        return None

    df = apply_filters(df, search, priority, min_score, max_score, spin, start_date, end_date)
    df = apply_sort(df, sort_by, sort_order)
    return df


def get_leads_page(
    search: Optional[str] = None,
    priority: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    spin: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    df = get_filtered_leads(search, priority, min_score, max_score, sort_by, sort_order, spin, start_date, end_date)

    if df is None:
        return {
            "has_data": False,
            "message": NO_DATA_MESSAGE,
            "data": [],
            "total": 0,
            "page": 1,
            "page_size": page_size,
            "total_pages": 0,
        }

    total = len(df)
    page = max(page, 1)
    page_size = max(min(page_size, 500), 1)
    total_pages = max(math.ceil(total / page_size), 1)
    page = min(page, total_pages)

    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end]

    records = page_df[TABLE_FIELDS + DETAIL_EXTRA_FIELDS].to_dict(orient="records")

    return {
        "has_data": True,
        "message": "No matching leads found." if total == 0 else None,
        "data": records,
        "total": int(total),
        "page": int(page),
        "page_size": int(page_size),
        "total_pages": int(total_pages),
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

EXPORT_COLUMNS = [
    "business_name", "phone", "email", "website", "instagram", "facebook",
    "linkedin", "city", "lead_score", "priority", "contact_completeness",
]

EXPORT_HEADERS = [
    "Business Name", "Phone", "Email", "Website", "Instagram", "Facebook",
    "LinkedIn", "City", "Lead Score", "Priority", "Contact Completeness %",
]


def _export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    export_df = df[EXPORT_COLUMNS].copy()
    export_df.columns = EXPORT_HEADERS
    return export_df


def export_csv_bytes(df: pd.DataFrame) -> bytes:
    export_df = _export_dataframe(df)
    buf = io.StringIO()
    export_df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def export_excel_bytes(df: pd.DataFrame) -> bytes:
    export_df = _export_dataframe(df)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Leads")

        # Light auto-fit so the exported file looks professional out of the box.
        worksheet = writer.sheets["Leads"]
        for i, col in enumerate(export_df.columns, start=1):
            max_len = max(
                [len(str(col))] + [len(str(v)) for v in export_df.iloc[:, i - 1].astype(str)]
            )
            worksheet.column_dimensions[worksheet.cell(row=1, column=i).column_letter].width = min(
                max(max_len + 2, 10), 50
            )
    buf.seek(0)
    return buf.getvalue()
