from bs4 import BeautifulSoup

from scrapers.playwright_scraper import render_page


def scrape_page(url):

    html = render_page(url)

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    return soup, html