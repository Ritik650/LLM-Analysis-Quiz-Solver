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
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        directory_name = "LLMFiles"
        os.makedirs(directory_name, exist_ok=True)
        path = os.path.join(directory_name, filename)
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return filename
    except Exception as e:
        return f"Error downloading file: {str(e)}"