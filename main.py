from dotenv import load_dotenv
from scraper import get_rendered_html
import tempfile
import google.generativeai as genai
import os
import json
import subprocess
import re
import json
import ast
import textwrap
import sys
import re
import subprocess

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def extract_program(json_str: str) -> tuple[str, list[str]]:
    json_str = re.sub(r"^```(?:json|python)?\s*", "", json_str.strip(), flags=re.IGNORECASE | re.MULTILINE)
    json_str = re.sub(r"```$", "", json_str.strip(), flags=re.MULTILINE)
    match = re.search(r'\{[\s\S]*\}', json_str)

    if not match:
        return "", []

    try:
        data = json.loads(match.group())
        program = data.get("program", "")
        dependencies = data.get("dependencies", [])
        if not isinstance(dependencies, list):
            dependencies = []

        # --- Cleaning Stage ---
        program = re.sub(r"^```(?:python|json)?\s*", "", program.strip(), flags=re.IGNORECASE | re.MULTILINE)
        program = re.sub(r"```$", "", program.strip(), flags=re.MULTILINE)

        program = program.replace("\r\n", "\n")

        program = textwrap.dedent(program)

        program = program.strip("\n").lstrip()  # <- This ensures first line starts flush left

        try:
            ast.parse(program)
        except SyntaxError as e:
            print(f"⚠️ SyntaxError detected (tolerated): {e}")

        return program, dependencies

    except json.JSONDecodeError:
        return "", []

PROMPT = """
   Write a Python program that accomplishes the follows the following requirements strictly:
   - It must be a **Python 3 program** that accomplishes the task described below.
   - The program should be **self-contained** and executable directly (e.g., via `python main.py`).
   - The program must define a variable named `answer` that holds the final computed result.
   - The program should **not print intermediate or debug outputs**; it must only print the final result of `answer`.
   - At the end of execution, the program must print only this block:
     ```
     FINAL_OUTPUT_START
     <JSON-encoded value of 'answer'>
     FINAL_OUTPUT_END
     ```
     Example:
     ```
     FINAL_OUTPUT_START
     12345
     FINAL_OUTPUT_END
     ```
   - If `answer` is a complex object (list, dict, etc.), it must be printed as a **JSON string** using `json.dumps(answer)`.
   - If an exception occurs, catch it and print a single line containing the word “error” and the message (e.g., `print("error:", e)`) and stop the program immediately.
   - Include a list variable called `dependencies` with all external libraries required (installable via `pip install <name>`).
   - Use only the necessary dependencies, and prefer Python standard libraries when possible.

    - Return the final output as a valid JSON object with the following structure:
   {{
     "program": "<The executable python program>",
     "dependencies": ["list", "of", "required", "packages"]
   }}
   The task to be accomplished is as follows:

"""


def generateCode(request: str):
    
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        contents= PROMPT + request 
    )
    return extract_program(response.text)

def executeCode(code: str, dependencies):
    try:
        for pkg in dependencies:
            result = subprocess.run(["uv", "add",  pkg], capture_output=True, text=True, check=True)
            print("Command output:")
            print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        print(f"Stderr: {e.stderr}")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        result = subprocess.run(
            [sys.executable, f.name],
            capture_output=True,
            text=True
        )

    if not result:
        return {"Error": "While executing the code, no result was returned."}
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        return {"error": f"error: {stderr}"}
    match = re.search(r"FINAL_OUTPUT_START\s*(.*?)\s*FINAL_OUTPUT_END", stdout, re.S)
    if match:
        answer = match.group(1).strip()
        return {"output": answer}

    return {"output": stdout}


def promptGenerator(question: str):
    llm = genai.GenerativeModel("gemini-2.5-flash")
    response = llm.generate_content(
        contents = f"""
            You are a html reading agent. You will be given the html content of a quiz webpage.
            Your task is to read the content and extract the following information:
            1. Task described in the quiz.
            2. 
            """
    )
    return response.text


def main(request: str, prev: str = ""):
    prompt = promptGenerator(request)
    code, deps = generateCode(prompt)
    result = executeCode(code, deps)
    return result["output"] if "output" in result else "Some error occurred."

request = """
Visit the following url and do the task mentioned in the webpage. Also return the answer to me.
https://tds-llm-analysis.s-anand.net/demo-audio?email=24f1001482@ds.study.iitm.ac.in
"""
print(main(request))