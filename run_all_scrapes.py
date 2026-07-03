"""
run_all_scrapes.py
------------------
Runs the crawler for multiple business types/countries sequentially,
then merges all results into a single combined CSV for the dashboard.

Usage:
    python run_all_scrapes.py
"""

import os
import sys
import time
import pandas as pd

# Each scrape config: (business_type, country, max_cities)
SCRAPE_JOBS = [
    ("gym", "india", 2),
    ("restaurant", "usa", 2),
    ("salon", "uk", 2),
    ("cafe", "canada", 2),
]

RAW_OUTPUT = "output/local_business_leads.csv"
FINAL_OUTPUT = "output/final_ai_leads.csv"

os.makedirs("output", exist_ok=True)

# Import the crawler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrapers.crawler import generate_leads

all_frames = []

# Load existing leads from previous runs to append new ones to them
if os.path.exists(FINAL_OUTPUT):
    try:
        existing = pd.read_csv(FINAL_OUTPUT)
        if not existing.empty:
            print(f"\nLoaded {len(existing)} existing leads to append to.\n")
            all_frames.append(existing)
    except Exception as e:
        print(f"Could not load existing leads: {e}")

for idx, (biz, country, max_cities) in enumerate(SCRAPE_JOBS, 1):
    print(f"\n{'='*60}")
    print(f"  JOB {idx}/{len(SCRAPE_JOBS)}: {biz} in {country} (max {max_cities} cities)")
    print(f"{'='*60}\n")

    try:
        df = generate_leads(biz, country, max_cities=max_cities)
        if df is not None and not df.empty:
            df["business_type"] = biz
            df["country"] = country
            all_frames.append(df)
            print(f"\n  -> Got {len(df)} leads for {biz} in {country}")
        else:
            print(f"\n  -> No leads returned for {biz} in {country}")
    except Exception as e:
        print(f"\n  -> ERROR scraping {biz} in {country}: {e}")

    # Clean up progress file between jobs
    progress_file = "output/progress.txt"
    if os.path.exists(progress_file):
        os.remove(progress_file)

    # Save progress after each job
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        combined.drop_duplicates(subset=["business_name"], keep="first", inplace=True)
        combined.to_csv(RAW_OUTPUT, index=False)
        print(f"  Saved progressive results to: {RAW_OUTPUT} ({len(combined)} total leads)")
        
        # Run lead cleaner progressively
        import subprocess
        print("  Running lead cleaner...")
        subprocess.run([sys.executable, "lead_cleaner.py"], check=False)

    time.sleep(3)

print(f"\n{'='*60}")
print(f"  ALL JOBS COMPLETE")
print(f"{'='*60}")
