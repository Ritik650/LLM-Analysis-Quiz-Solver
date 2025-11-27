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
        delay = data.get("delay", 0)
        delay = delay if isinstance(delay, (int, float)) else 0
        correct = data.get("correct")
        if not correct and delay < 180:
            del data["url"]
        if delay >= 180:
            data = {
                "url": data.get("url")
            }
        print("Got the response: \n", json.dumps(data, indent=4), '\n')
        return data
    except requests.HTTPError as e:
        # Extract server’s error response
        err_resp = e.response

        try:
            err_data = err_resp.json()
        except ValueError:
            err_data = err_resp.text

        print("HTTP Error Response:\n", err_data)
        return err_data

    except Exception as e:
        print("Unexpected error:", e)
        return str(e)