"""
export_google_cookies.py
------------------------
Exports Google cookies saved by the Chrome extension "Cookie-Editor"
into the correct format for the scraper.

HOW TO USE:
  1. Install the "Cookie-Editor" Chrome extension:
     https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm

  2. Open https://www.google.com/maps in Chrome (make sure you are logged in
     or have previously accepted Google's cookie consent).

  3. Click the Cookie-Editor extension icon -> Export -> Export as JSON
     This copies the cookies to your clipboard.

  4. Paste the clipboard content into a file called:
       config/google_cookies.json
     (inside this project folder)

  5. Run this script to validate the file:
       python export_google_cookies.py

  6. Restart the Docker container on the server:
       docker-compose restart dashboard
"""

import json
import os
import sys

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "google_cookies.json"
)


def validate_and_fix():
    if not os.path.exists(OUTPUT_PATH):
        print("ERROR: config/google_cookies.json not found.")
        print()
        print("Steps to create it:")
        print("  1. Install Chrome extension: Cookie-Editor")
        print("     https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm")
        print("  2. Open https://www.google.com/maps in Chrome")
        print("  3. Click Cookie-Editor icon -> Export -> Export as JSON")
        print("  4. Paste clipboard into:  config/google_cookies.json")
        print("  5. Run this script again to validate")
        sys.exit(1)

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        print("ERROR: Expected a JSON array of cookies.")
        sys.exit(1)

    # Normalize fields to what Playwright expects
    fixed = []
    for c in raw:
        name  = c.get("name", "")
        value = c.get("value", "")
        domain = c.get("domain", ".google.com")
        path   = c.get("path", "/")

        if not name or not value:
            continue

        entry = {
            "name":   name,
            "value":  value,
            "domain": domain if domain.startswith(".") else "." + domain,
            "path":   path,
        }

        # sameSite must be Strict | Lax | None
        same_site = c.get("sameSite", "Lax")
        if same_site not in ("Strict", "Lax", "None"):
            same_site = "Lax"
        entry["sameSite"] = same_site

        if "secure" in c:
            entry["secure"] = bool(c["secure"])
        if "httpOnly" in c:
            entry["httpOnly"] = bool(c["httpOnly"])

        fixed.append(entry)

    # Write back the normalised version
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fixed, f, indent=2)

    print("OK: " + str(len(fixed)) + " cookies validated and saved to " + OUTPUT_PATH)
    print()
    print("Next step -- restart the Docker container on the server:")
    print("  docker-compose restart dashboard")
    print()
    print("The scraper will now inject these cookies into every browser session,")
    print("bypassing Google's datacenter-IP consent wall.")


if __name__ == "__main__":
    validate_and_fix()
