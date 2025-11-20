# @title Import necessary libraries
import os
import asyncio
import subprocess
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types # For creating message Content/Parts
from google import genai
from dotenv import load_dotenv
import warnings
from tools.web_scraper import get_rendered_html
# Ignore all warnings
warnings.filterwarnings("ignore")
load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

print("Libraries imported.")
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash"

def strip_code_fences(code: str) -> str:
    code = code.strip()
    # Remove ```python ... ``` or ``` ... ```
    if code.startswith("```"):
        # remove first line (```python or ```)
        code = code.split("\n", 1)[1]
    if code.endswith("```"):
        code = code.rsplit("\n", 1)[0]
    return code.strip()
    
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

    # --- Step 1: Generate code ---
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    
    code = strip_code_fences(response.text)

    # --- Step 2: Create a temporary Python file ---
    filename = "runner.py"
    with open(filename, "w") as f:
        f.write(code)

    # --- Step 3: Execute the generated script ---
    proc = subprocess.Popen(
        ["python", filename],
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

    
# @title Define the Weather Agent
# Use one of the model constants defined earlier
AGENT_MODEL = MODEL_GEMINI_2_0_FLASH # Starting with Gemini

coding_agent = Agent(
    name="coding_agent",
    model=AGENT_MODEL, # Can be a string for Gemini or a LiteLlm object
description = ( "An agent that can solve quiz problems, computational tasks, and webpage-based "
    "questions by either generating and executing Python code or by fetching rendered "
    "HTML content from the web when needed."
),

instruction = (
    "You are a problem-solving agent designed to answer quiz questions, math problems, "
    "data-processing tasks, programming challenges, and webpage-based tasks. "

    "You have access to two tools:\n"
    "1. 'generate_and_run' — Takes a natural-language prompt, generates Python code, "
    "   executes it, and returns both the generated code and its output.\n"
    "2. 'get_rendered_html' — Loads a webpage in a headless browser, executes all "
    "   JavaScript, and returns the fully rendered HTML for analysis.\n\n"

    "When the user asks about a URL, webpage, or any task that requires reading or "
    "extracting content from online pages, you must use 'get_rendered_html' to fetch "
    "the fully rendered HTML before answering. After fetching it, analyze the HTML "
    "directly or, if needed, use 'generate_and_run' to process it programmatically. "

    "When the user asks a question that requires calculations, simulations, data "
    "manipulation, or algorithmic reasoning, construct the proper prompt for "
    "'generate_and_run' so that the necessary Python code is generated and executed "
    "to solve the problem. "

    "After a tool call returns results, interpret them carefully and provide the "
    "final answer clearly to the user. Include optional explanations if helpful. "

    "If a task cannot be solved with the available tools, or a tool fails, respond "
    "politely and explain the limitation. Always ensure that the code you request "
    "via 'generate_and_run' is directly relevant to solving the user’s problem, and "
    "that HTML fetched with 'get_rendered_html' is used appropriately when a webpage "
    "is involved."
),


    tools=[generate_and_run, get_rendered_html], # Pass the function directly
)


# @title Setup Session Service and Runner

# --- Session Management ---
# Key Concept: SessionService stores conversation history & state.
# InMemorySessionService is simple, non-persistent storage for this tutorial.
session_service = InMemorySessionService()

# Define constants for identifying the interaction context
APP_NAME = "coding_agent_app"
USER_ID = "user_1"
SESSION_ID = "session_001" # Using a fixed ID for simplicity

# Create the specific session where the conversation will happen
session = asyncio.run(session_service.create_session(
    app_name=APP_NAME,
    user_id=USER_ID,
    session_id=SESSION_ID
))
print(f"Session created: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")

# --- Runner ---
# Key Concept: Runner orchestrates the agent execution loop.
runner = Runner(
    agent=coding_agent, # The agent we want to run
    app_name=APP_NAME,   # Associates runs with our app
    session_service=session_service # Uses our session manager
)
print(f"Runner created for agent '{runner.agent.name}'.")

# @title Define Agent Interaction Function

async def call_agent_async(query: str, runner, user_id, session_id):
  """Sends a query to the agent and prints the final response."""
  print(f"\n>>> User Query: {query}")

  # Prepare the user's message in ADK format
  content = types.Content(role='user', parts=[types.Part(text=query)])

  final_response_text = "Agent did not produce a final response." # Default

  # Key Concept: run_async executes the agent logic and yields Events.
  # We iterate through events to find the final answer.
  async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
      # You can uncomment the line below to see *all* events during execution
      # print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")

      # Key Concept: is_final_response() marks the concluding message for the turn.
      if event.is_final_response():
          if event.content and event.content.parts:
             # Assuming text response in the first part
             final_response_text = event.content.parts[0].text
          elif event.actions and event.actions.escalate: # Handle potential errors/escalations
             final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
          # Add more checks here if needed (e.g., specific error codes)
          break # Stop processing events once the final response is found

  print(f"<<< Agent Response: {final_response_text}")
  

async def run_conversation():
    await call_agent_async("""
                            Visit the following url and do the task mentioned in the webpage. Also return the answer to me.
                            https://tds-llm-analysis.s-anand.net/demo-audio?email=24f1001482@ds.study.iitm.ac.in
                            """,
                            runner=runner,
                            user_id=USER_ID,
                            session_id=SESSION_ID)

# Execute the conversation using await in an async context (like Colab/Jupyter)
asyncio.run(run_conversation())
