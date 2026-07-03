from playwright.sync_api import sync_playwright


def render_page(url):

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        try:

            page.goto(
                url,
                timeout=60000,
                wait_until="domcontentloaded"
            )

            page.wait_for_timeout(3000)

            html = page.content()

            return html

        finally:

            browser.close()