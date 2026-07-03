import sys
import os
import subprocess

print("\n======================================")
print("  AI LEAD GENERATION SYSTEM V2")
print("======================================\n")

# ============================================
# ACCEPT INPUT — CLI args or interactive
# ============================================

if len(sys.argv) >= 3:
    # Server mode: python main.py "gym" "india" [max_cities]
    business_type = sys.argv[1].strip()
    country = sys.argv[2].strip()
    max_cities = int(sys.argv[3]) if len(sys.argv) >= 4 else 30
    print(f"Running in server mode:")
    print(f"  Business Type : {business_type}")
    print(f"  Country       : {country}")
    print(f"  Max Cities    : {max_cities}\n")

else:
    # Interactive mode
    business_type = input("Enter business type (e.g. gym, salon, restaurant): ").strip()
    country = input("Enter country (e.g. india, usa, uk): ").strip()
    max_cities_input = input("Max cities to scrape (default 30, press Enter to skip): ").strip()
    max_cities = int(max_cities_input) if max_cities_input else 30

if not business_type or not country:
    print("ERROR: Business type and country cannot be empty.")
    sys.exit(1)

os.makedirs("output", exist_ok=True)

# ============================================
# RUN CRAWLER
# ============================================

print("\n======================================")
print("  STARTING CRAWLER")
print("======================================\n")

crawler_failed = False
try:
    from scrapers.crawler import generate_leads
    generate_leads(business_type, country, max_cities=max_cities)

except Exception as e:
    print(f"\nCRAWLER ERROR: {e}")
    print("Attempting to continue to lead cleaner with existing data...\n")
    crawler_failed = True

# ============================================
# RUN LEAD CLEANER
# ============================================

print("\n======================================")
print("  RUNNING LEAD CLEANER")
print("======================================\n")

cleaner_failed = False
no_leads = False
try:
    result = subprocess.run(
        [sys.executable, "lead_cleaner.py"],
        check=False
    )
    if result.returncode == 2:
        no_leads = True
    elif result.returncode != 0:
        cleaner_failed = True

except Exception as e:
    print(f"\nLEAD CLEANER ERROR: {e}")
    cleaner_failed = True

print("\n======================================")
if no_leads:
    print("  SYSTEM FINISHED — NO LEADS SCRAPED")
    print("======================================")
    sys.exit(3)
elif crawler_failed or cleaner_failed:
    print("  SYSTEM FINISHED WITH ERRORS")
    print("======================================")
    sys.exit(1)
else:
    print("  SYSTEM FINISHED SUCCESSFULLY")
    print("======================================")