import pandas as pd
import os
import requests
import json
import math
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config import N8N_WEBHOOK_URL, N8N_WEBHOOK_SECRET, N8N_SEND_ON_COMPLETION

input_file = "output/local_business_leads.csv"

if not os.path.exists(input_file) or os.path.getsize(input_file) == 0:
    print("No leads CSV found (or file is empty) — skipping cleaner.")
    print("LEAD_CLEANER_STATUS: NO_LEADS")
    sys.exit(2)

try:
    df = pd.read_csv(input_file)
except pd.errors.EmptyDataError:
    print("Leads CSV exists but has no rows/columns to parse — skipping cleaner.")
    print("LEAD_CLEANER_STATUS: NO_LEADS")
    sys.exit(2)

if df.empty:
    print("Leads CSV parsed but contains 0 rows — skipping cleaner.")
    print("LEAD_CLEANER_STATUS: NO_LEADS")
    sys.exit(2)

print(f"\nOriginal Leads: {len(df)}")

# ----------------------------------------
# CLEAN
# ----------------------------------------

# Explicitly cast all potential string/text columns to string to prevent float64 type inference issues
text_cols = ["business_name", "phone", "website", "address", "instagram", "facebook", "linkedin", "email", "city", "business_type", "country", "spin", "scraped_at"]
for col in text_cols:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str).replace(["nan", "0", "0.0", "None"], "").str.strip()

# Safely handle NaN in all other columns (numeric, boolean, etc.) without raising TypeErrors
for col in df.columns:
    if col not in text_cols:
        if df[col].dtype == 'object':
            df[col] = df[col].fillna("")
        else:
            df[col] = df[col].fillna(0)

if "spin" not in df.columns:
    df["spin"] = "Legacy Run"
if "scraped_at" not in df.columns:
    df["scraped_at"] = ""

df = df.drop_duplicates(subset=["business_name", "spin"], keep="first")
df = df[~((df["email"] != "") & df.duplicated(subset=["email", "spin"]))]
df = df[~((df["phone"] != "") & df.duplicated(subset=["phone", "spin"]))]
df = df[df["business_name"].str.strip() != ""]

# ----------------------------------------
# FEATURE ENGINEERING
# ----------------------------------------

def has_social_media(row):
    return any([row["instagram"] != "", row["facebook"] != "", row["linkedin"] != ""])

def completeness(row):
    fields = ["phone", "website", "email", "instagram", "facebook", "linkedin"]
    filled = sum(1 for f in fields if str(row[f]).strip() != "")
    return round((filled / len(fields)) * 100, 2)

def lead_score(row):
    score = 0
    if row["phone"] != "":     score += 20
    if row["website"] != "":   score += 20
    if row["email"] != "":     score += 40
    if row["instagram"] != "": score += 10
    if row["facebook"] != "":  score += 5
    if row["linkedin"] != "":  score += 5
    return score

def priority(score):
    if score >= 70: return "Hot"
    elif score >= 40: return "Warm"
    return "Cold"

df["Has Website"]            = df["website"].apply(lambda x: "Yes" if str(x).strip() else "No")
df["Has Email"]              = df["email"].apply(lambda x: "Yes" if str(x).strip() else "No")
df["Has Social Media"]       = df.apply(lambda row: "Yes" if has_social_media(row) else "No", axis=1)
df["Contact Completeness %"] = df.apply(completeness, axis=1)
df["Lead Score"]             = df.apply(lead_score, axis=1)
df["Priority"]               = df["Lead Score"].apply(priority)

df = df.sort_values(by="Lead Score", ascending=False)

# ----------------------------------------
# SAVE  (unchanged — still saves to output/)
# ----------------------------------------

output_file = "output/final_ai_leads.csv"
df.to_csv(output_file, index=False)

# ----------------------------------------
# SUMMARY
# ----------------------------------------

hot  = len(df[df["Priority"] == "Hot"])
warm = len(df[df["Priority"] == "Warm"])
cold = len(df[df["Priority"] == "Cold"])

print(f"Cleaned Leads : {len(df)}")
print(f"  Hot  (70+)  : {hot}")
print(f"  Warm (40-69): {warm}")
print(f"  Cold (<40)  : {cold}")
print(f"\nSaved to: {output_file}")
print("\nLead Cleaning Complete!")

# ----------------------------------------
# SEND TO N8N WEBHOOK
# ----------------------------------------

def send_to_n8n(dataframe):
    if not N8N_SEND_ON_COMPLETION:
        print("\n[N8N] Webhook sending is disabled in config. Skipping.")
        return

    print(f"\n[N8N] Sending {len(dataframe)} leads to N8N webhook...")

    headers = {"Content-Type": "application/json"}
    if N8N_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = N8N_WEBHOOK_SECRET

    # Convert dataframe to list of dicts
    leads_list = dataframe.to_dict(orient="records")

    # Clean NaN/inf values for safe JSON serialization
    def clean_value(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    leads_list = [{k: clean_value(v) for k, v in row.items()} for row in leads_list]

    payload = {
        "total_leads": len(leads_list),
        "hot_leads": hot,
        "warm_leads": warm,
        "cold_leads": cold,
        "leads": leads_list
    }

    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=30
        )
        if response.status_code in (200, 201):
            print(f"[N8N] OK - Successfully sent to N8N! Status: {response.status_code}")
        else:
            print(f"[N8N] FAIL - N8N returned status {response.status_code}: {response.text[:200]}")
    except requests.exceptions.Timeout:
        print("[N8N] FAIL - Request timed out. Leads still saved locally.")
    except requests.exceptions.ConnectionError:
        print("[N8N] FAIL - Could not connect to N8N. Check the URL. Leads still saved locally.")
    except Exception as e:
        print(f"[N8N] FAIL - Unexpected error: {e}. Leads still saved locally.")

send_to_n8n(df)