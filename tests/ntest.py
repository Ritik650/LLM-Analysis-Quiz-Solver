from dotenv import load_dotenv
import tempfile
import google.generativeai as genai
import os
import json
import subprocess
import sys
import re
from pathlib import Path

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def extract_program(json_str: str) -> tuple[str, list]:
    """Extract program and dependencies from LLM response"""
    # Remove markdown code blocks if present
    json_str = re.sub(r'```json\s*', '', json_str)
    json_str = re.sub(r'```\s*', '', json_str)
    print(json_str)
    match = re.search(r'\{.*\}', json_str, re.DOTALL)
    if not match:
        return "", []
    
    try:
        data = json.loads(match.group())
        program = data.get("program", "").strip()
        dependencies = data.get("dependencies", [])
        
        if not isinstance(dependencies, list):
            dependencies = []
        
        return program, dependencies
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return "", []

PROMPT = """
Write a Python program that accomplishes the task described below.

CRITICAL REQUIREMENTS:
1. The program MUST store its final result in a variable called 'answer'
2. The 'answer' variable should contain:
   - A number (int/float) for calculations
   - A string for text results
   - A dict/list for structured data
   - A base64 data URI string for visualizations (e.g., "data:image/png;base64,...")
3. Import ALL required libraries at the top
4. Handle errors gracefully with try-except blocks
5. Do NOT use input() or any interactive elements
6. Do NOT print anything except via the 'answer' variable

Example structure:
```
import requests
import pandas as pd

# Your code here
data = requests.get(url).text
df = pd.read_csv(...)
result = df['column'].sum()

# MUST have this:
answer = result
```

Return a valid JSON object with this structure:
{
  "program": "<the complete Python code as a string>",
  "dependencies": ["package1", "package2"]
}

Use exact pip package names (e.g., "beautifulsoup4" not "bs4", "pillow" not "PIL").
"""

def generateCode(request: str) -> tuple[str, list]:
    """Generate code using Gemini"""
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(
        contents=request + "\n\n" + PROMPT
    )
    return extract_program(response.text)

def install_dependencies(dependencies: list) -> bool:
    """Install required dependencies"""
    if not dependencies:
        return True
    
    print(f"Installing dependencies: {dependencies}")
    
    try:
        # Try using pip directly for more reliable installation
        for pkg in dependencies:
            print(f"Installing {pkg}...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"Failed to install {pkg}: {result.stderr}")
                return False
            
            print(f"Successfully installed {pkg}")
        
        return True
    
    except subprocess.TimeoutExpired:
        print("Dependency installation timed out")
        return False
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        return False

def executeCode(code: str, dependencies: list, timeout: int = 120) -> dict:
    """Execute generated code safely"""
    
    # Install dependencies first
    if dependencies and not install_dependencies(dependencies):
        return {
            "error": "Failed to install required dependencies",
            "answer": None
        }
    
    # Create a temporary file with the code
    with tempfile.NamedTemporaryFile(
        mode="w", 
        suffix=".py", 
        delete=False,
        encoding='utf-8'
    ) as f:
        temp_file = f.name
        
        # Wrap code to extract 'answer' variable
        wrapped_code = f"""
import sys
import json

# Generated code starts here
{code}

# Extract answer and print as JSON
if 'answer' in locals():
    print("__ANSWER_START__")
    print(json.dumps({{"answer": answer}}, default=str))
    print("__ANSWER_END__")
else:
    print("__ERROR__: Code did not produce an 'answer' variable")
"""
        f.write(wrapped_code)
    
    try:
        # Execute the code
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        # Clean up temp file
        try:
            os.unlink(temp_file)
        except:
            pass
        
        # Check for execution errors
        if result.returncode != 0:
            return {
                "error": result.stderr.strip(),
                "answer": None,
                "stdout": result.stdout
            }
        
        # Extract answer from output
        output = result.stdout
        
        if "__ERROR__" in output:
            return {
                "error": "Code did not produce an 'answer' variable",
                "answer": None,
                "stdout": output
            }
        
        # Parse answer
        if "__ANSWER_START__" in output and "__ANSWER_END__" in output:
            start = output.find("__ANSWER_START__") + len("__ANSWER_START__")
            end = output.find("__ANSWER_END__")
            answer_json = output[start:end].strip()
            
            try:
                answer_data = json.loads(answer_json)
                return {
                    "error": None,
                    "answer": answer_data["answer"],
                    "stdout": output
                }
            except json.JSONDecodeError:
                return {
                    "error": "Failed to parse answer",
                    "answer": None,
                    "stdout": output
                }
        
        # Fallback: return full output
        return {
            "error": None,
            "answer": output.strip(),
            "stdout": output
        }
    
    except subprocess.TimeoutExpired:
        # Clean up temp file
        try:
            os.unlink(temp_file)
        except:
            pass
        
        return {
            "error": f"Code execution timed out after {timeout} seconds",
            "answer": None
        }
    
    except Exception as e:
        # Clean up temp file
        try:
            os.unlink(temp_file)
        except:
            pass
        
        return {
            "error": f"Execution error: {str(e)}",
            "answer": None
        }

def regenerateCode(request: str, failed_code: str, error: str) -> tuple[str, list]:
    """Regenerate code after failure"""
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    retry_prompt = f"""
The following code failed to execute. Fix the errors and generate corrected code.

Original task:
{request}

Failed code:
```python
{failed_code}
```

Error message:
{error}

Generate corrected code following the same format as before.
Make sure to:
1. Fix the specific error mentioned
2. Add proper error handling
3. Ensure the 'answer' variable is set
4. Include all necessary imports

{PROMPT}
"""
    
    response = model.generate_content(contents=retry_prompt)
    return extract_program(response.text)

def promptGenerator(question: str) -> str:
    """Generate an optimized prompt for code generation"""
    llm = genai.GenerativeModel("gemini-2.0-flash-exp")
    response = llm.generate_content(
        contents=f"""
You are a prompt generator for an AI coding assistant.

Given this user question:
{question}

Generate a clear, detailed prompt that:
1. Describes the task precisely
2. Specifies any URLs, files, or data sources
3. Clarifies what format the answer should be in
4. Mentions any specific operations needed (sum, filter, visualize, etc.)

Return ONLY the enhanced prompt, no explanations.
"""
    )
    return response.text

def solve_with_retry(request: str, max_retries: int = 2) -> dict:
    """Solve with automatic retry on failure"""
    
    # Generate enhanced prompt
    print("Generating enhanced prompt...")
    prompt = promptGenerator(request)
    print(f"Enhanced prompt:\n{prompt}\n")
    
    # First attempt
    print("Generating code (attempt 1)...")
    code, deps = generateCode(prompt)
    
    if not code:
        return {"error": "Failed to generate code", "answer": None}
    
    print(f"Generated code:\n{code}\n")
    print(f"Dependencies: {deps}\n")
    
    # Execute
    print("Executing code...")
    result = executeCode(code, deps)
    
    # Retry if failed
    retry_count = 0
    while result.get("error") and retry_count < max_retries:
        retry_count += 1
        print(f"\nExecution failed. Retrying ({retry_count}/{max_retries})...")
        print(f"Error: {result['error']}\n")
        
        # Regenerate code with error context
        code, deps = regenerateCode(prompt, code, result['error'])
        
        if not code:
            return {"error": "Failed to regenerate code", "answer": None}
        
        print(f"Regenerated code:\n{code}\n")
        result = executeCode(code, deps)
    
    return result

# Test
if __name__ == "__main__":
    request = """
    Extract the race schedule from the following URL: https://www.formula1.com/en/racing/2025/brazil
    Return the data as a structured dictionary with race information.
    """
    
    result = solve_with_retry(request)
    
    print("\n" + "="*50)
    print("FINAL RESULT:")
    print("="*50)
    
    if result.get("error"):
        print(f"Error: {result['error']}")
    else:
        print(f"Answer: {result['answer']}")