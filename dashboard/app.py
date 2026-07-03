"""
app.py
------
FastAPI application for the Lead Generation Dashboard.

Run with:
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
(from inside the dashboard/ folder)
"""

from __future__ import annotations

from typing import Optional
import os
import shutil
import subprocess
import sys

from fastapi import FastAPI, Query, Request, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import dashboard_service as svc
import scraper_service

app = FastAPI(title="Lead Generation Dashboard", version="1.0.0")

app.mount("/static", StaticFiles(directory=os.path.join(_THIS_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_THIS_DIR, "templates"))


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    business_type: str
    country: str
    max_cities: int = Field(default=30, ge=1, le=200)


# ---------------------------------------------------------------------------
# Favicon
# ---------------------------------------------------------------------------

@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    return RedirectResponse(url="/static/favicon.svg")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# API: stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def api_stats():
    return svc.get_stats()


# ---------------------------------------------------------------------------
# API: charts
# ---------------------------------------------------------------------------

@app.get("/api/charts")
def api_charts():
    return svc.get_charts()


# ---------------------------------------------------------------------------
# API: leads (search / filter / sort / paginate)
# ---------------------------------------------------------------------------

@app.get("/api/leads")
def api_leads(
    search: Optional[str] = Query(None),
    priority: Optional[str] = Query(None, description="all | Hot | Warm | Cold"),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    sort_by: Optional[str] = Query("lead_score"),
    sort_order: Optional[str] = Query("desc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    spin: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    return svc.get_leads_page(
        search=search,
        priority=priority,
        min_score=min_score,
        max_score=max_score,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        spin=spin,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/api/spins")
def api_spins():
    return {
        "spins": svc.get_unique_spins()
    }


# ---------------------------------------------------------------------------
# Export: CSV / Excel (respects current filters, ignores pagination)
# ---------------------------------------------------------------------------

@app.get("/api/export/csv")
def export_csv(
    search: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    sort_by: Optional[str] = Query("lead_score"),
    sort_order: Optional[str] = Query("desc"),
    spin: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    df = svc.get_filtered_leads(search, priority, min_score, max_score, sort_by, sort_order, spin, start_date, end_date)
    if df is None or df.empty:
        df = svc.load_leads()
        if df is None:
            import pandas as pd
            df = pd.DataFrame(columns=svc.EXPORT_COLUMNS)

    content = svc.export_csv_bytes(df)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@app.get("/api/export/excel")
def export_excel(
    search: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    sort_by: Optional[str] = Query("lead_score"),
    sort_order: Optional[str] = Query("desc"),
    spin: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    df = svc.get_filtered_leads(search, priority, min_score, max_score, sort_by, sort_order, spin, start_date, end_date)
    if df is None or df.empty:
        df = svc.load_leads()
        if df is None:
            import pandas as pd
            df = pd.DataFrame(columns=svc.EXPORT_COLUMNS)

    content = svc.export_excel_bytes(df)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leads_export.xlsx"},
    )


# ---------------------------------------------------------------------------
# Health check (useful for Docker healthcheck / uptime monitoring)
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "csv_found": svc.csv_exists(), "csv_path": svc.CSV_PATH}


# ---------------------------------------------------------------------------
# Scraper control
# ---------------------------------------------------------------------------

@app.post("/api/scrape/start")
def scrape_start(req: ScrapeRequest):
    return scraper_service.start_scrape(
        business_type=req.business_type,
        country=req.country,
        max_cities=req.max_cities,
    )


@app.get("/api/scrape/status")
def scrape_status():
    return scraper_service.get_scrape_status()


@app.post("/api/scrape/stop")
def scrape_stop():
    return scraper_service.stop_scrape()
