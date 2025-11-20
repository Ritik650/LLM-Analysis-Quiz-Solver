from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def get_rendered_html(url: str) -> str:
    print(url)
    """
    Fetch and return the fully rendered HTML of a webpage.

    This function uses Playwright to load a webpage in a headless Chromium
    browser, allowing all JavaScript on the page to execute before extraction.
    After the page finishes rendering, the function captures the final DOM,
    removes all <script> tags to avoid embedded JS, and returns the cleaned
    HTML as a string.

    Parameters
    ----------
    url : str
        The URL of the webpage to retrieve and render.

    Returns
    -------
    str
        The fully rendered and cleaned HTML content of the webpage after
        JavaScript execution, with all <script> tags removed.

    """
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

url = "https://tds-llm-analysis.s-anand.net/demo-audio?email=24f1001482%40ds.study.iitm.ac.in&id=4818"
html = get_rendered_html(url)
print(html)
