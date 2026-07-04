import re
import time
import json
import requests
import pandas as pd
import urllib3
import os

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Cookie injection — bypass Google datacenter-IP consent walls
# ---------------------------------------------------------------------------

# Looks for cookies in this order:
#   1. GOOGLE_COOKIES_PATH env var
#   2. /app/config/google_cookies.json  (Docker / server path)
#   3. config/google_cookies.json       (local dev path)
COOKIE_SEARCH_PATHS = [
    os.environ.get("GOOGLE_COOKIES_PATH", ""),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "google_cookies.json"),
    "/app/config/google_cookies.json",
]


def _load_cookies() -> list:
    """Load Google cookies from JSON file. Returns [] if not found."""
    for path in COOKIE_SEARCH_PATHS:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                print(f"  [Cookies loaded from {os.path.basename(path)} — {len(cookies)} cookies]")
                return cookies
            except Exception as e:
                print(f"  [Cookie load failed from {os.path.basename(path)}: {e}]")
    print("  [No google_cookies.json found — running without cookies (may hit consent wall)]")
    return []


def _inject_cookies(context, cookies: list):
    """Inject cookies into a Playwright browser context."""
    if not cookies:
        return
    try:
        # Playwright expects: name, value, domain, path — filter to Google domains
        playwright_cookies = []
        for c in cookies:
            entry = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ".google.com"),
                "path": c.get("path", "/"),
            }
            # Optional fields
            if "secure" in c:
                entry["secure"] = c["secure"]
            if "httpOnly" in c:
                entry["httpOnly"] = c["httpOnly"]
            if "sameSite" in c and c["sameSite"] in ("Strict", "Lax", "None"):
                entry["sameSite"] = c["sameSite"]
            playwright_cookies.append(entry)
        context.add_cookies(playwright_cookies)
        print(f"  [Injected {len(playwright_cookies)} cookies into browser context]")
    except Exception as e:
        print(f"  [Cookie injection error: {e}]")

print("CRAWLER V2 LOADED")


# ============================================
# PROGRESS CALLBACK (used by dashboard)
# ============================================

class ScrapeCancelled(Exception):
    """Raised by the progress callback to abort a running scrape."""
    pass

_progress_callback = None

def set_progress_callback(fn):
    """Set a callback fn(event_type: str, data: dict) for live progress."""
    global _progress_callback
    _progress_callback = fn

def clear_progress_callback():
    """Remove the progress callback (restores default CLI-only behaviour)."""
    global _progress_callback
    _progress_callback = None

def _notify(event_type, data=None):
    """Fire the callback if one is registered. Silently no-ops otherwise."""
    if _progress_callback is not None:
        _progress_callback(event_type, data or {})


def fetch_cities_from_wikipedia(country, max_cities=30):
    """
    Dynamically fetch major cities for any country using Wikipedia's API.
    Looks up the 'List of cities in <Country> by population' page and
    extracts city names from the wikitable.
    Returns [] if it fails for any reason (network, page not found, etc).
    """

    headers = {
        "User-Agent": "LeadGenBot/1.0 (Educational lead generation tool)"
    }

    country_clean = country.strip().title().replace(" ", "_")

    candidate_titles = [
        f"List_of_cities_in_{country_clean}_by_population",
        f"List_of_cities_and_towns_in_{country_clean}",
        f"List_of_largest_cities_in_{country_clean}",
        f"List_of_cities_in_{country_clean}",
    ]

    for title in candidate_titles:

        try:
            # Fetch rendered HTML to parse the table properly
            html_response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "parse",
                    "page": title,
                    "format": "json",
                    "prop": "text"
                },
                headers=headers,
                timeout=15
            )

            if html_response.status_code != 200:
                continue

            html_data = html_response.json()

            if "error" in html_data:
                continue

            html_content = html_data["parse"]["text"]["*"]

            soup = BeautifulSoup(html_content, "html.parser")

            tables = soup.find_all("table", {"class": "wikitable"})

            if not tables:
                continue

            cities = []

            # Known non-city terms that sometimes appear as links in these tables
            blacklist_terms = [
                "census", "population", "metropolitan", "urban agglomeration",
                "state", "province", "territory", "district", "region",
                "wikipedia", "citation", "reference", "list of",
                "municipal corporation", "capital", "country"
            ]

            for table in tables:
                rows = table.find_all("tr")

                # Identify header row to find which column is the "City" column
                header_cells = rows[0].find_all(["th", "td"]) if rows else []
                header_texts = [h.get_text(strip=True).lower() for h in header_cells]

                city_col_index = None
                for idx, text in enumerate(header_texts):
                    if "city" in text or "name" in text or "town" in text:
                        city_col_index = idx
                        break

                for row in rows[1:]:  # skip header row

                    cells = row.find_all(["td", "th"])

                    if not cells:
                        continue

                    # Use identified city column if found, else try column 1 (often "Rank" is column 0)
                    target_cells = []
                    if city_col_index is not None and city_col_index < len(cells):
                        target_cells = [cells[city_col_index]]
                    elif len(cells) > 1:
                        target_cells = [cells[1]]
                    else:
                        target_cells = [cells[0]]

                    for cell in target_cells:
                        link = cell.find("a")
                        if link and link.get_text(strip=True):
                            city_name = link.get_text(strip=True)
                            city_name_lower = city_name.lower()

                            is_blacklisted = any(term in city_name_lower for term in blacklist_terms)

                            if (
                                2 < len(city_name) < 40
                                and not city_name.isdigit()
                                and not is_blacklisted
                                and city_name not in cities
                            ):
                                cities.append(city_name)

                if len(cities) >= 5:  # only accept this table if it yielded a reasonable city list
                    break
                else:
                    cities = []  # reset and try next table

            if cities:
                print(f"  Found {len(cities)} cities via Wikipedia page: {title}")
                return cities[:max_cities]

        except Exception as e:
            print(f"  Wikipedia lookup failed for '{title}': {str(e)[:80]}")
            continue

    return []


def fetch_cities_via_wikipedia_search(country, max_cities=30):
    """
    Fallback web lookup: uses Wikipedia's search API to find ANY page
    related to cities in the given country (handles cases where the
    exact page title guess in fetch_cities_from_wikipedia() didn't match,
    e.g. unusual country name formatting). Still 100% web-sourced.
    """

    headers = {
        "User-Agent": "LeadGenBot/1.0 (Educational lead generation tool)"
    }

    try:
        search_response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"list of cities in {country} by population",
                "format": "json",
                "srlimit": 5
            },
            headers=headers,
            timeout=15
        )

        if search_response.status_code != 200:
            return []

        results = search_response.json().get("query", {}).get("search", [])

        for result in results:
            page_title = result.get("title", "")

            if not page_title:
                continue

            html_response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "parse",
                    "page": page_title,
                    "format": "json",
                    "prop": "text"
                },
                headers=headers,
                timeout=15
            )

            if html_response.status_code != 200:
                continue

            html_data = html_response.json()

            if "error" in html_data:
                continue

            html_content = html_data["parse"]["text"]["*"]
            soup = BeautifulSoup(html_content, "html.parser")
            tables = soup.find_all("table", {"class": "wikitable"})

            if not tables:
                continue

            cities = []

            blacklist_terms = [
                "census", "population", "metropolitan", "urban agglomeration",
                "state", "province", "territory", "district", "region",
                "wikipedia", "citation", "reference", "list of",
                "municipal corporation", "capital", "country"
            ]

            for table in tables:
                rows = table.find_all("tr")

                header_cells = rows[0].find_all(["th", "td"]) if rows else []
                header_texts = [h.get_text(strip=True).lower() for h in header_cells]

                city_col_index = None
                for idx, text in enumerate(header_texts):
                    if "city" in text or "name" in text or "town" in text:
                        city_col_index = idx
                        break

                for row in rows[1:]:

                    cells = row.find_all(["td", "th"])

                    if not cells:
                        continue

                    target_cells = []
                    if city_col_index is not None and city_col_index < len(cells):
                        target_cells = [cells[city_col_index]]
                    elif len(cells) > 1:
                        target_cells = [cells[1]]
                    else:
                        target_cells = [cells[0]]

                    for cell in target_cells:
                        link = cell.find("a")
                        if link and link.get_text(strip=True):
                            city_name = link.get_text(strip=True)
                            city_name_lower = city_name.lower()

                            is_blacklisted = any(term in city_name_lower for term in blacklist_terms)

                            if (
                                2 < len(city_name) < 40
                                and not city_name.isdigit()
                                and not is_blacklisted
                                and city_name not in cities
                            ):
                                cities.append(city_name)

                if len(cities) >= 5:
                    break
                else:
                    cities = []

            if cities:
                print(f"  Found {len(cities)} cities via Wikipedia search result: {page_title}")
                return cities[:max_cities]

    except Exception as e:
        print(f"  Wikipedia search fallback failed: {str(e)[:80]}")

    return []


def get_cities(country, max_cities=30):

    print(f"\nLooking up major cities for '{country}'...")

    # 1. Try direct page-title guess first (fast path)
    cities = fetch_cities_from_wikipedia(country, max_cities=max_cities)

    if cities:
        return cities

    # 2. Try Wikipedia search API as a fallback (still fully web-sourced)
    print("  Direct lookup failed — trying Wikipedia search...")
    cities = fetch_cities_via_wikipedia_search(country, max_cities=max_cities)

    if cities:
        return cities

    # 3. Last resort — treat country itself as the single search location
    print(f"  Could not find a city list for '{country}' on the web. Using country name as single location.")
    return [country]


# ============================================
# BROWSER HELPERS
# ============================================

# Titles that indicate a consent/error page — not a real business
_CONSENT_TITLES = [
    "before you continue",
    "sign in",
    "consent",
    "google accounts",
    "verify it's you",
    "choose an account",
    "we use cookies",
]

_LOADED_COOKIES: list = None  # cached after first load


def _get_cookies() -> list:
    global _LOADED_COOKIES
    if _LOADED_COOKIES is None:
        _LOADED_COOKIES = _load_cookies()
    return _LOADED_COOKIES


def launch_browser(p):
    return p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--memory-pressure-off",
            "--lang=en-IN",
        ]
    )


def new_context(browser):
    """
    Create a new browser context with cookies pre-injected.
    Use this instead of browser.new_page() directly so cookies
    persist across pages in the same context.
    """
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        geolocation={"latitude": 20.5937, "longitude": 78.9629},  # India center
        permissions=["geolocation"],
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
    )
    _inject_cookies(context, _get_cookies())
    return context


def new_page(browser):
    """Create a context+page with cookies injected."""
    ctx = new_context(browser)
    return ctx.new_page()


def dismiss_consent_wall(page):
    """
    Detect and click Google's cookie consent dialog.
    Handles the full-page redirect to consent.google.com that datacenter
    IPs trigger — retries up to 3 times with longer waits.
    """
    consent_selectors = [
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'form[action*="consent"] button >> nth=-1',
        'form[action*="consent"] button:last-of-type',
        'form[action*="consent"] button',
        'button:has-text("Accept")',
        'div[aria-label="Accept all"]',
        'button[aria-label="Accept all"]',
        '#L2AGLb',          # "Accept all" button ID seen on consent.google.com
        '.sy4vM',           # Accept button class on newer consent page
        'button.tHlp8d',    # Another consent button class variant
    ]

    for attempt in range(3):
        try:
            # If redirected to consent.google.com wait for it to settle
            current_url = page.url
            if "consent.google" in current_url or "before you continue" in page.title().lower():
                print(f"  [Consent wall detected at: {current_url[:80]}]")
                page.wait_for_load_state("networkidle", timeout=10000)

            clicked = False
            for sel in consent_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=4000):
                        btn.click(timeout=5000)
                        print(f"  [Dismissed Google consent wall (attempt {attempt+1})]")
                        page.wait_for_load_state("domcontentloaded", timeout=15000)
                        page.wait_for_timeout(2000)
                        clicked = True
                        break
                except Exception:
                    continue

            if clicked:
                # Verify we're no longer on the consent page
                if "consent.google" not in page.url:
                    return True
                # Still on consent — retry
                continue

            # No consent button found — we're probably on the real page
            return False

        except Exception:
            pass

    return False


def _save_debug_artifacts(page, city):
    """
    Saves a screenshot + HTML snapshot of whatever page actually loaded
    when scraping fails, so failures can be diagnosed instead of just
    showing up as a bare timeout with no leads.
    """
    try:
        debug_dir = os.path.join("output", "debug")
        os.makedirs(debug_dir, exist_ok=True)
        safe_city = re.sub(r"[^a-zA-Z0-9_-]", "_", city)
        png_path = os.path.join(debug_dir, f"{safe_city}.png")
        html_path = os.path.join(debug_dir, f"{safe_city}.html")
        page.screenshot(path=png_path, timeout=10000)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"  [Saved debug artifacts: {png_path}, {html_path}]")
    except Exception as debug_err:
        print(f"  [Could not save debug artifacts: {str(debug_err)[:80]}]")


# ============================================
# EXTRACT EMAILS + SOCIALS FROM WEBSITE
# ============================================

def extract_socials_and_email(url):
    socials = {"instagram": "", "facebook": "", "linkedin": "", "email": ""}

    if not url:
        return socials

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)
        blacklist = ["example", "domain", "email.com", "yourmail", "sentry", "wixpress", "squarespace"]

        for email in emails:
            if not any(b in email.lower() for b in blacklist):
                socials["email"] = email
                break

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "instagram.com" in href and not socials["instagram"]:
                socials["instagram"] = href
            elif "facebook.com" in href and not socials["facebook"]:
                socials["facebook"] = href
            elif "linkedin.com" in href and not socials["linkedin"]:
                socials["linkedin"] = href

    except:
        pass

    return socials


# ============================================
# CLEAN TEXT
# ============================================

def clean_text(text):
    if not text:
        return ""
    text = text.replace("\ue0b0", "").replace("\ue0c8", "").replace("\n", " ")
    return text.strip()


# ============================================
# SCRAPE SINGLE BUSINESS — with browser restart
# ============================================

def _is_consent_page(title: str, url: str) -> bool:
    """Return True if the page is a Google consent/error page, not a real business."""
    title_lower = (title or "").lower()
    url_lower = (url or "").lower()
    if "consent.google" in url_lower:
        return True
    return any(t in title_lower for t in _CONSENT_TITLES)


def scrape_business(link, p, browser, page):
    for attempt in range(2):
        try:
            if not browser.is_connected() or page.is_closed():
                print("  [Browser crashed — restarting...]")
                try:
                    browser.close()
                except:
                    pass
                browser = launch_browser(p)
                page = new_page(browser)

            page.goto(link, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            # Dismiss consent wall — may redirect then land back on the business page
            dismissed = dismiss_consent_wall(page)
            if dismissed:
                page.wait_for_timeout(2000)

            # Wait for details panel h1 element to load
            try:
                page.wait_for_selector("h1", timeout=12000)
            except Exception:
                pass

            # Guard: reject consent/error pages so they don't get saved as leads
            page_title = ""
            try:
                page_title = page.title()
            except Exception:
                pass

            if _is_consent_page(page_title, page.url):
                print(f"  [Skipped consent/error page: '{page_title[:60]}']")
                return None, browser, page

            try:
                business_name = clean_text(page.locator("h1").first.inner_text(timeout=8000))
            except:
                business_name = ""

            # Fallback to page title if h1 extraction failed or timed out
            if not business_name and page_title:
                clean_title = page_title.split(" - Google")[0].strip()
                # Extra check to ensure title is not a Google system page
                if not _is_consent_page(clean_title, page.url):
                    business_name = clean_title

            # Extra guard on the extracted business name itself
            if _is_consent_page(business_name, page.url):
                print(f"  [Skipped consent page masquerading as lead: '{business_name[:60]}']")
                return None, browser, page

            try:
                phone = clean_text(page.locator('button[data-item-id*="phone"]').first.inner_text(timeout=8000))
            except:
                phone = ""

            try:
                address = clean_text(page.locator('button[data-item-id="address"]').first.inner_text(timeout=8000))
            except:
                address = ""

            try:
                website = page.locator('a[data-item-id="authority"]').first.get_attribute("href", timeout=8000)
            except:
                website = ""

            socials = extract_socials_and_email(website)

            lead = {
                "business_name": business_name,
                "phone": phone,
                "website": website or "",
                "address": address,
                "instagram": socials["instagram"],
                "facebook": socials["facebook"],
                "linkedin": socials["linkedin"],
                "email": socials["email"]
            }

            return lead, browser, page

        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {str(e)[:80]}")
            try:
                browser.close()
            except:
                pass
            browser = launch_browser(p)
            page = new_page(browser)
            time.sleep(3)

    return None, browser, page


# ============================================
# SCRAPE ONE CITY
# ============================================

def scrape_city(business_type, city, p, browser, page):
    city_leads = []
    search_query = f"{business_type} in {city}"

    print(f"\n{'='*50}")
    print(f"  Scraping: {search_query}")
    print(f"{'='*50}")

    search_url = (
        "https://www.google.com/maps/search/"
        + search_query.strip().replace(" ", "+")
        + "?hl=en&gl=in"
    )

    try:
        if not browser.is_connected() or page.is_closed():
            try:
                browser.close()
            except:
                pass
            browser = launch_browser(p)
            page = new_page(browser)

        page.goto(search_url, wait_until="domcontentloaded", timeout=120000)
        time.sleep(5)

        # ---- Handle Google's consent wall ----
        dismiss_consent_wall(page)

        time.sleep(5)
        page.wait_for_selector('div[role="feed"]', timeout=30000)

    except Exception as e:
        print(f"  Failed to load Maps for {city}: {e}")
        _save_debug_artifacts(page, city)
        return city_leads, browser, page

    scrollable_div = page.locator('div[role="feed"]').first
    previous_count = 0
    same_count = 0

    is_quick = os.environ.get("QUICK_SCRAPE") == "true"
    max_scrolls = 2 if is_quick else 80

    for i in range(max_scrolls):
        try:
            scrollable_div.evaluate("(el) => el.scrollTop = el.scrollHeight")
            time.sleep(2 if is_quick else 3)
            cards = scrollable_div.locator('a[href*="/place/"]').all()
            current_count = len(cards)
            print(f"  Scroll {i+1} | Businesses: {current_count}")

            if current_count == previous_count:
                same_count += 1
            else:
                same_count = 0

            previous_count = current_count

            if same_count >= 6:
                break
        except:
            break

    business_links = []
    try:
        cards = scrollable_div.locator('a[href*="/place/"]').all()
        for card in cards:
            try:
                href = card.get_attribute("href")
                if href and "/place/" in href:
                    clean_link = href.split("&")[0]
                    if clean_link not in business_links:
                        business_links.append(clean_link)
            except:
                pass
    except:
        pass

    if is_quick:
        business_links = business_links[:3]

    print(f"\n  Found {len(business_links)} businesses in {city}")
    _notify("businesses_found", {"city": city, "total_businesses": len(business_links)})

    try:
        page.close()
    except:
        pass
    page = new_page(browser)

    for idx, link in enumerate(business_links):
        print(f"  Opening Business {idx+1}/{len(business_links)}", end="\r")
        _notify("business_progress", {"city": city, "business_index": idx + 1, "total_businesses": len(business_links)})

        lead, browser, page = scrape_business(link, p, browser, page)

        if lead and any([lead["business_name"], lead["phone"], lead["website"], lead["address"]]):
            lead["city"] = city
            city_leads.append(lead)

    print(f"\n  Leads collected from {city}: {len(city_leads)}")
    return city_leads, browser, page


# ============================================
# MAIN GENERATE LEADS — COUNTRY MODE
# ============================================

def generate_leads(business_type, country, max_cities=30):
    os.makedirs("output", exist_ok=True)

    cities = get_cities(country, max_cities=max_cities)
    all_leads = []

    # Progress tracking — resume if interrupted
    progress_file = "output/progress.txt"
    completed_cities = set()

    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            completed_cities = set(line.strip() for line in f.readlines())
        print(f"\nResuming — {len(completed_cities)} cities already done.")

    remaining_cities = [c for c in cities if c not in completed_cities]

    # Load existing leads if resuming
    raw_output = "output/local_business_leads.csv"
    if os.path.exists(raw_output) and completed_cities:
        existing_df = pd.read_csv(raw_output)
        all_leads = existing_df.to_dict("records")
        print(f"Loaded {len(all_leads)} existing leads.")

    print(f"\nTarget: {business_type} across {len(cities)} cities in {country}")
    print(f"Remaining cities: {len(remaining_cities)}\n")

    scraped_time = time.strftime("%Y-%m-%d %H:%M:%S")
    friendly_spin = f"{business_type} in {country} ({scraped_time[:16]})"

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = new_page(browser)

        for city_idx, city in enumerate(remaining_cities):
            # Allow dashboard to cancel between cities
            _notify("city_start", {"city": city, "city_index": city_idx + 1, "total_cities": len(remaining_cities)})
            print(f"\n[City {city_idx+1}/{len(remaining_cities)}] {city}")

            city_leads, browser, page = scrape_city(
                business_type, city, p, browser, page
            )

            for lead in city_leads:
                lead["spin"] = friendly_spin
                lead["scraped_at"] = scraped_time

            all_leads.extend(city_leads)

            # Mark city as done
            with open(progress_file, "a") as f:
                f.write(city + "\n")

            # Save after every city
            current_run_df = pd.DataFrame(all_leads)
            if os.path.exists(raw_output):
                try:
                    historical_df = pd.read_csv(raw_output)
                    historical_df = historical_df[historical_df["spin"] != friendly_spin]
                    df_temp = pd.concat([historical_df, current_run_df], ignore_index=True)
                except Exception:
                    df_temp = current_run_df
            else:
                df_temp = current_run_df

            df_temp.drop_duplicates(subset=["business_name", "spin"], inplace=True)
            df_temp.to_csv(raw_output, index=False)

            print(f"\n  Progress saved — Total leads so far: {len(df_temp)}")
            _notify("city_done", {"city": city, "city_index": city_idx + 1, "total_cities": len(remaining_cities), "city_leads_count": len(city_leads), "total_leads": len(df_temp)})

            # Small delay between cities to avoid rate limiting
            time.sleep(5)

        try:
            browser.close()
        except:
            pass

    # Final save
    current_run_df = pd.DataFrame(all_leads)
    if os.path.exists(raw_output):
        try:
            historical_df = pd.read_csv(raw_output)
            historical_df = historical_df[historical_df["spin"] != friendly_spin]
            df = pd.concat([historical_df, current_run_df], ignore_index=True)
        except Exception:
            df = current_run_df
    else:
        df = current_run_df

    df.drop_duplicates(subset=["business_name", "spin"], inplace=True)
    df.to_csv(raw_output, index=False)

    # Clear progress file on success
    if os.path.exists(progress_file):
        os.remove(progress_file)

    print(f"\n{'='*50}")
    print(f"ALL CITIES DONE")
    print(f"Total Leads: {len(df)}")
    print(f"Saved to: {raw_output}")
    print(f"{'='*50}")

    return df