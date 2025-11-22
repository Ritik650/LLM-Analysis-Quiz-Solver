from typing import List
from langchain_core.tools import tool
import subprocess


@tool
def add_dependencies(dependencies: List[str]) -> str:
    """
    Install the given Python packages into the environment.

    Parameters:
        dependencies (List[str]):
            A list of Python package names to install. Each name must match the 
            corresponding package name on PyPI.

    Returns:
        str:
            A message indicating success or failure.
    """

    try:
        subprocess.check_call(
            ["uv", "add"] + dependencies,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return "Successfully installed dependencies: " + ", ".join(dependencies)
    
    except subprocess.CalledProcessError as e:
        return (
            "Dependency installation failed.\n"
            f"Exit code: {e.returncode}\n"
            f"Error: {e.stderr or 'No error output.'}"
        )
    
    except Exception as e:
        return f"Unexpected error while installing dependencies: {e}" 
