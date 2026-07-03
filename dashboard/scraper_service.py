"""
scraper_service.py
------------------
Background-thread orchestrator that bridges the dashboard API with the
existing crawler pipeline.  All scraper state is held in a module-level
dict protected by a threading.Lock — no database or files needed.

The dashboard calls:
    start_scrape(business_type, country, max_cities)
    stop_scrape()
    get_scrape_status()

The actual scraping happens in a daemon thread so the FastAPI event loop
stays responsive.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Resolve project root so we can import the crawler package
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# Ensure the project root is on sys.path so "from scrapers.crawler import …"
# works when this file is imported from the dashboard package.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_cancel_event = threading.Event()
_worker_thread: Optional[threading.Thread] = None

MAX_LOG_LINES = 100
_run_history: List[Dict[str, Any]] = []

_status: Dict[str, Any] = {
    "state": "idle",         # idle | running | stopping | completed | error
    "business_type": "",
    "country": "",
    "max_cities": 0,
    "current_city": "",
    "current_city_index": 0,
    "total_cities": 0,
    "current_business_index": 0,
    "total_businesses": 0,
    "cities_completed": 0,
    "total_leads_found": 0,
    "progress_pct": 0,
    "logs": [],
    "error": None,
    "started_at": None,
    "elapsed_seconds": 0,
}

_log_buffer: deque = deque(maxlen=MAX_LOG_LINES)


def _reset_status():
    """Reset to idle defaults."""
    global _log_buffer
    _status.update({
        "state": "idle",
        "business_type": "",
        "country": "",
        "max_cities": 0,
        "current_city": "",
        "current_city_index": 0,
        "total_cities": 0,
        "current_business_index": 0,
        "total_businesses": 0,
        "cities_completed": 0,
        "total_leads_found": 0,
        "progress_pct": 0,
        "logs": [],
        "error": None,
        "started_at": None,
        "elapsed_seconds": 0,
    })
    _log_buffer = deque(maxlen=MAX_LOG_LINES)


def _add_log(message: str):
    """Append a line to the rolling log buffer."""
    _log_buffer.append(message)
    _status["logs"] = list(_log_buffer)


# ---------------------------------------------------------------------------
# Progress callback — injected into crawler.py
# ---------------------------------------------------------------------------

def _progress_callback(event_type: str, data: dict):
    """
    Called by crawler.py at key points during scraping.
    Runs on the worker thread — must be quick and threadsafe.
    """
    from scrapers.crawler import ScrapeCancelled

    # Check cancellation flag first
    if _cancel_event.is_set():
        _add_log("⛔ Cancellation requested — stopping after current operation…")
        with _lock:
            _status["state"] = "stopping"
        raise ScrapeCancelled("Scrape cancelled by user")

    with _lock:
        if event_type == "city_start":
            _status["current_city"] = data.get("city", "")
            _status["current_city_index"] = data.get("city_index", 0)
            _status["total_cities"] = data.get("total_cities", 0)
            _status["current_business_index"] = 0
            _status["total_businesses"] = 0
            _add_log(f"📍 Starting city {data.get('city_index', '?')}/{data.get('total_cities', '?')}: {data.get('city', '?')}")

            # Update progress percentage based on cities
            total = data.get("total_cities", 1)
            done = data.get("city_index", 1) - 1  # current hasn't finished yet
            _status["progress_pct"] = min(int((done / max(total, 1)) * 100), 99)

        elif event_type == "city_done":
            _status["cities_completed"] = data.get("city_index", 0)
            _status["total_leads_found"] = data.get("total_leads", 0)
            city_leads = data.get("city_leads_count", 0)
            _add_log(f"✅ Completed {data.get('city', '?')} — {city_leads} leads found (total: {data.get('total_leads', 0)})")

            total = data.get("total_cities", 1)
            done = data.get("city_index", 0)
            _status["progress_pct"] = min(int((done / max(total, 1)) * 100), 99)

        elif event_type == "businesses_found":
            _status["total_businesses"] = data.get("total_businesses", 0)
            _add_log(f"🔍 Found {data.get('total_businesses', 0)} businesses in {data.get('city', '?')}")

        elif event_type == "business_progress":
            _status["current_business_index"] = data.get("business_index", 0)
            _status["total_businesses"] = data.get("total_businesses", 0)

        elif event_type == "log":
            _add_log(data.get("message", ""))


def _update_last_history_entry():
    """Update the status of the currently running or last run history entry."""
    with _lock:
        if not _run_history:
            return
        entry = _run_history[-1]
        entry["status"] = _status["state"]
        entry["leads_found"] = _status["total_leads_found"]
        
        # Calculate duration string
        if _status["started_at"]:
            elapsed = int(time.time() - _status["started_at"])
            m = elapsed // 60
            s = elapsed % 60
            entry["duration"] = f"{m}m {s}s" if m > 0 else f"{s}s"


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

def _scrape_worker(business_type: str, country: str, max_cities: int):
    """Runs in a background thread. Calls generate_leads() and lead_cleaner."""
    try:
        from scrapers.crawler import (
            generate_leads,
            set_progress_callback,
            clear_progress_callback,
            ScrapeCancelled,
        )

        set_progress_callback(_progress_callback)

        with _lock:
            _status["state"] = "running"
            _add_log(f"🚀 Starting scrape: {business_type} in {country} (max {max_cities} cities)")

        # ---- Run the crawler (unchanged logic) ----
        df = generate_leads(business_type, country, max_cities=max_cities)

        # ---- Run lead cleaner (same as main.py does) ----
        with _lock:
            _add_log("🧹 Running lead cleaner…")

        cleaner_path = os.path.join(PROJECT_ROOT, "lead_cleaner.py")
        result = subprocess.run(
            [sys.executable, cleaner_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            with _lock:
                _add_log("✅ Lead cleaner completed successfully")
        elif result.returncode == 2:
            with _lock:
                _add_log("ℹ️ Lead cleaner: no leads to process")
        else:
            with _lock:
                _add_log(f"⚠️ Lead cleaner exited with code {result.returncode}")

        # ---- Done ----
        with _lock:
            total = len(df) if df is not None else 0
            _status["state"] = "completed"
            _status["progress_pct"] = 100
            _status["total_leads_found"] = total
            _add_log(f"🎉 Scraping complete! Total leads: {total}")

    except ScrapeCancelled:
        with _lock:
            _status["state"] = "completed"
            _add_log("⛔ Scrape was cancelled by user")

    except Exception as e:
        with _lock:
            _status["state"] = "error"
            _status["error"] = str(e)
            _add_log(f"❌ Error: {str(e)}")

    finally:
        clear_progress_callback()
        _cancel_event.clear()

        # Update elapsed time one last time
        with _lock:
            if _status["started_at"]:
                _status["elapsed_seconds"] = int(time.time() - _status["started_at"])
        _update_last_history_entry()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_scrape(business_type: str, country: str, max_cities: int = 30) -> Dict[str, Any]:
    """
    Start a scrape job in the background.
    Returns {"ok": True} or {"ok": False, "error": "..."}.
    """
    global _worker_thread

    business_type = (business_type or "").strip()
    country = (country or "").strip()

    if not business_type:
        return {"ok": False, "error": "Business type is required"}
    if not country:
        return {"ok": False, "error": "Country is required"}
    if max_cities < 1:
        return {"ok": False, "error": "Max cities must be at least 1"}

    with _lock:
        if _status["state"] == "running":
            return {"ok": False, "error": "A scrape is already running"}

        _reset_status()
        _cancel_event.clear()
        _status["state"] = "running"
        _status["business_type"] = business_type
        _status["country"] = country
        _status["max_cities"] = max_cities
        _status["started_at"] = time.time()

        # Add to run history
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        _run_history.append({
            "id": len(_run_history) + 1,
            "business_type": business_type,
            "country": country,
            "max_cities": max_cities,
            "status": "running",
            "timestamp": timestamp_str,
            "leads_found": 0,
            "duration": "0s"
        })

    _worker_thread = threading.Thread(
        target=_scrape_worker,
        args=(business_type, country, max_cities),
        daemon=True,
        name="scraper-worker",
    )
    _worker_thread.start()

    return {"ok": True}


def stop_scrape() -> Dict[str, Any]:
    """Signal the running scrape to stop after the current operation."""
    with _lock:
        if _status["state"] not in ("running",):
            return {"ok": False, "error": "No scrape is currently running"}
        _cancel_event.set()
        _status["state"] = "stopping"
        _add_log("⏹️ Stop requested — will halt after current city/business finishes…")
    return {"ok": True}


def get_scrape_status() -> Dict[str, Any]:
    """Return a snapshot of the current scrape status."""
    with _lock:
        result = dict(_status)
        # Compute live elapsed time if running
        if result["state"] in ("running", "stopping") and result["started_at"]:
            result["elapsed_seconds"] = int(time.time() - result["started_at"])
        result["run_history"] = list(_run_history)
        return result
