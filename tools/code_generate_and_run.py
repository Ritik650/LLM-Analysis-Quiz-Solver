from google import genai
import subprocess
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
from google.genai import types
load_dotenv()
client = genai.Client()

def strip_code_fences(code: str) -> str:
    code = code.strip()
    # Remove ```python ... ``` or ``` ... ```
    if code.startswith("```"):
        # remove first line (```python or ```)
        code = code.split("\n", 1)[1]
    if code.endswith("```"):
        code = code.rsplit("\n", 1)[0]
    return code.strip()

@tool
def generate_and_run(prompt: str) -> dict:
    """
    Generate Python code from a natural-language prompt AND execute it.

    This tool:
      1. Takes a prompt
      2. Generates code using Gemini
      3. Writes code into a temporary .py file
      4. Executes the file
      5. Returns both the code and its output

    Parameters
    ----------
    prompt : str
        Natural-language description of what code to generate.

    Returns
    -------
    dict
        {
            "code": <generated source code>,
            "stdout": <program output>,
            "stderr": <errors if any>,
            "return_code": <exit code>
        }
    """
    sys_instruct = """
    You are a Python programming assistant.
    Given a natural-language prompt, generate a complete Python script that accomplishes the task.
    Ensure the code is syntactically correct.
    Only return the code inside the markdown code fences. Do not include any explanations or text outside the code fences.
    Always have a proper error handling mechanism."""
    # --- Step 1: Generate code ---
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
        system_instruction=sys_instruct,   
    )
    )
    
    code = strip_code_fences(response.text)

    # --- Step 2: Create a temporary Python file ---
    filename = "runner.py"
    with open(os.path.join("LLMFiles", filename), "w") as f:
        f.write(code)

    # --- Step 3: Execute the generated script ---
    proc = subprocess.Popen(
        ["uv", "run", "LLMFiles/"+filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = proc.communicate()

    # --- Step 4: Return everything ---
    return {
        "code": code,
        "stdout": stdout,
        "stderr": stderr,
        "return_code": proc.returncode
    }