from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
import json

url = "https://www.brasilf1.com/en/time-schedule-19"

try:
    # Setup Selenium (headless Chrome)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    # Wait a few seconds for JavaScript to render
    time.sleep(6)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    # Extract year dynamically from the URL
    match = re.search(r"/racing/(\d{4})/brazil", url)
    year = match.group(1) if match else "2025"

    schedule = {}

    # Look for blocks containing session details
    # (Formula1.com often wraps sessions under <time> or <span> tags with date/time data)
    blocks = soup.find_all(["li", "div"], string=re.compile(r"(Practice|Qualifying|Race)", re.IGNORECASE))

    if not blocks:
        # Fallback: broader search
        blocks = soup.find_all(text=re.compile(r"(Practice|Qualifying|Race)", re.IGNORECASE))

    session_count = {}

    for b in blocks:
        text = b.get_text(" ", strip=True) if hasattr(b, "get_text") else str(b)
        session_match = re.search(r"(Practice\s*\d*|Qualifying|Race)", text, re.IGNORECASE)
        if not session_match:
            continue
        session_name = session_match.group(1).strip()

        base_name = re.sub(r"\s*\d*$", "", session_name).strip().title()
        session_count[base_name] = session_count.get(base_name, 0) + 1
        if base_name.lower() == "practice" and not re.search(r"\d", session_name):
            session_name = f"Practice {session_count[base_name]}"

        # Extract date and time (e.g., "07 Nov", "14:00")
        date_match = re.search(r"(\d{1,2}\s+\w+)", text)
        time_match = re.search(r"(\d{1,2}:\d{2})", text)

        if not date_match or not time_match:
            continue

        date_str = date_match.group(1)
        time_str = time_match.group(1)

        try:
            date_obj = datetime.strptime(f"{date_str} {year}", "%d %b %Y")
            formatted_date = date_obj.strftime("%Y-%m-%d")
        except Exception:
            formatted_date = f"{year}-01-01"

        schedule[session_name] = {
            "Date": formatted_date,
            "Start Time (Local)": time_str,
            "Session": session_name
        }

    answer = schedule

    # Optional: save to JSON for reference
    with open("brazil_gp_2025_schedule.json", "w", encoding="utf-8") as f:
        json.dump(answer, f, indent=2, ensure_ascii=False)

except Exception as e:
    print(f"Error fetching or parsing schedule: {e}")
    answer = {}

print(answer)
