from scrapers.playwright_scraper import render_page

html = render_page(
    "https://www.lenskart.com"
)

print(html[:5000])