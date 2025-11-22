from langchain_core.tools import tool
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

@tool
def get_rendered_html(url: str) -> str:
    """
    Fetch and return the fully rendered HTML of a webpage.

    This function uses Playwright to load a webpage in a headless Chromium
    browser, allowing all JavaScript on the page to execute. Use this for
    dynamic websites that require rendering.

    IMPORTANT RESTRICTIONS:
    - ONLY use this for actual HTML webpages (articles, documentation, dashboards).
    - DO NOT use this for direct file links (URLs ending in .csv, .pdf, .zip, .png).
      Playwright cannot render these and will crash. Use the 'download_file' tool instead.

    Parameters
    ----------
    url : str
        The URL of the webpage to retrieve and render.

    Returns
    -------
    str
        The fully rendered and cleaned HTML content.
    """
    # ... existing code ...
    print("\nFetching and rendering:", url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Load the page (let JS execute)
            page.goto(url, wait_until="networkidle")

            # Extract rendered HTML
            content = page.content()

            browser.close()
            return content

    except Exception as e:
        return f"Error fetching/rendering page: {str(e)}"