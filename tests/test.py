import re
import requests
import base64

def extract_decoded_content(url):
    # Step 1: Get the HTML source
    html = requests.get(url).text

    # Step 2: Find Base64 string inside atob(`...`)
    match = re.search(r"atob\(`([^`]+)`\)", html)
    if not match:
        return "No Base64 found."

    # Step 3: Decode the Base64
    encoded_str = match.group(1).replace("\n", "")
    decoded = base64.b64decode(encoded_str).decode('utf-8', errors='ignore')

    return decoded


# Example usage
url = "http://localhost:8000/new.html"
print(extract_decoded_content(url))
