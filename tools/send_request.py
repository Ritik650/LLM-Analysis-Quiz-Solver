from langchain_core.tools import tool
import requests
import json
from typing import Any, Dict, Optional

@tool
def post_request(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any:
    """
    Send an HTTP POST request to the given URL with the provided payload.

    This function is designed for LangGraph applications, where it can be wrapped
    as a Tool or used inside a Runnable to call external APIs, webhooks, or backend
    services during graph execution.
    REMEMBER: This a blocking function so it may take a while to return. Wait for the response.
    Args:
        url (str): The endpoint to send the POST request to.
        payload (Dict[str, Any]): The JSON-serializable request body.
        headers (Optional[Dict[str, str]]): Optional HTTP headers to include
            in the request. If omitted, a default JSON header is applied.

    Returns:
        Any: The response body. If the server returns JSON, a parsed dict is
        returned. Otherwise, the raw text response is returned.

    Raises:
        requests.HTTPError: If the server responds with an unsuccessful status.
        requests.RequestException: For network-related errors.
    """
    headers = headers or {"Content-Type": "application/json"}
    try:
        print(f"\nSending Answer \n{json.dumps(payload, indent=4)}\n to url: {url}")
        response = requests.post(url, json=payload, headers=headers)

        # Raise on 4xx/5xx
        response.raise_for_status()

        # Try to return JSON, fallback to raw text
        data = response.json()
        print("Got the response: \n", json.dumps(data, indent=4), '\n')
        return data
    except ValueError:
        return response.text
    except Exception as e:
        return e
