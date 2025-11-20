from langchain_core.tools import tool
import requests
import os

@tool
def download_file(url: str, filename: str) -> str:
    """
    Download a file from a URL and save it with the given filename
    in the current working directory.

    Args:
        url (str): Direct URL to the file.
        filename (str): The filename to save the downloaded content as.

    Returns:
        str: Full path to the saved file.
    """
    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(os.path.join("LLMFiles", filename), "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return filename
