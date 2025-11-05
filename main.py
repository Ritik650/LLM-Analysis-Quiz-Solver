from dotenv import load_dotenv
import tempfile
import google.generativeai as genai
import os
import json
import importlib
import subprocess
import re, json, ast, textwrap
import sys
import re
import subprocess
import importlib
load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def extract_program(json_str: str) -> tuple[str, list[str]]:
    json_str = re.sub(r"^```(?:json|python)?\s*", "", json_str.strip(), flags=re.IGNORECASE | re.MULTILINE)
    json_str = re.sub(r"```$", "", json_str.strip(), flags=re.MULTILINE)
    match = re.search(r'\{[\s\S]*\}', json_str)

    print(match)
    if not match:
        return "", []

    try:
        data = json.loads(match.group())
        program = data.get("program", "")
        dependencies = data.get("dependencies", [])
        if not isinstance(dependencies, list):
            dependencies = []

        # --- Cleaning Stage ---
        # 1️⃣ Remove Markdown fences
        program = re.sub(r"^```(?:python|json)?\s*", "", program.strip(), flags=re.IGNORECASE | re.MULTILINE)
        program = re.sub(r"```$", "", program.strip(), flags=re.MULTILINE)

        # 2️⃣ Normalize all newlines
        program = program.replace("\r\n", "\n")

        # 3️⃣ Dedent consistently
        program = textwrap.dedent(program)

        # 4️⃣ Strip all leading/trailing blank lines or spaces
        program = program.strip("\n").lstrip()  # <- This ensures first line starts flush left

        # 5️⃣ Optional syntax check
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
   - If an exception occurs, catch it and print a single line containing the word “error” and the message (e.g., `print("error:", e)`).
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

    stdout = result.stdout.strip()

    # 5️⃣ Extract only final answer (ignore markers and logs)
    match = re.search(r"FINAL_OUTPUT_START\s*(.*?)\s*FINAL_OUTPUT_END", stdout, re.S)
    if match:
        answer = match.group(1).strip()
        return {"output": answer}

    # 6️⃣ Fallback if no markers found
    return {"output": stdout}


def promptGenerator(question: str):
    llm = genai.GenerativeModel("gemini-2.5-flash")
    response = llm.generate_content(
        contents = f"""
            1. You are a prompt generator for an AI coding assistant. You will be given an user's request to solve a problem/question.
            2. Your task is to generate a detailed prompt that will help the AI coding assistant understand the problem/question.
            3. You should only return the prompt as the output and nothing else.
            4. The user's question is: {question}
            """
    )
    return response.text
request = """
Visit an invalid URL like https://thisurldoesnotexist1234.com
Print an error containing the word 'error'.
"""

prompt = promptGenerator(request)
print(prompt)
code, deps = generateCode(prompt)
print("Generated Code: \n",code, deps)
result = executeCode(code, deps)
print(result)