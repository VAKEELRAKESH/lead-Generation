import requests
from bs4 import BeautifulSoup
import re


def scrape_website_data(url):

    social_data = {
        "instagram": "",
        "facebook": "",
        "linkedin": "",
        "email": ""
    }

    if url == "":
        return social_data

    try:

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        soup = BeautifulSoup(response.text, "html.parser")

        # ==========================================
        # GET ALL LINKS
        # ==========================================

        links = soup.find_all("a", href=True)

        for link in links:

            href = link["href"]

            # INSTAGRAM
            if "instagram.com" in href:
                social_data["instagram"] = href

            # FACEBOOK
            elif "facebook.com" in href:
                social_data["facebook"] = href

            # LINKEDIN
            elif "linkedin.com" in href:
                social_data["linkedin"] = href

        # ==========================================
        # EMAIL EXTRACTION
        # ==========================================

        emails = re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            response.text
        )

        if emails:
            social_data["email"] = emails[0]

    except Exception as e:

        print(f"Website Scraping Error: {e}")

    return social_data