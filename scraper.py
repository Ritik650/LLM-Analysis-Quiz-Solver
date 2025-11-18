from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def get_rendered_html(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load the page (let JS execute)
        page.goto(url, wait_until="networkidle")

        # Extract rendered HTML
        content = page.content()

        browser.close()
        soup = BeautifulSoup(content, "html.parser")
        for script in soup(["script"]):
            script.extract()
        return str(soup)

url = "http://localhost:8000/new.html"
html = get_rendered_html(url)
print(html)
