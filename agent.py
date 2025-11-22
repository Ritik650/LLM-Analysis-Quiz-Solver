from langgraph.graph import StateGraph, END, START
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.prebuilt import ToolNode
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tools import get_rendered_html, download_file, post_request, run_code, add_dependencies
from typing import TypedDict, Annotated, List, Any
from langchain.chat_models import init_chat_model
from langgraph.graph.message import add_messages
import os
from dotenv import load_dotenv
load_dotenv()
# -------------------------------------------------
# STATE
# -------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]


TOOLS = [run_code, get_rendered_html, download_file, post_request, add_dependencies]


# -------------------------------------------------
# GEMINI LLM
# -------------------------------------------------
rate_limiter = InMemoryRateLimiter(
    requests_per_second=10/60,  
    check_every_n_seconds=0.1,  
    max_bucket_size=10  
)
llm = init_chat_model(
   model_provider="google_genai",
   model="gemini-2.5-flash",
   rate_limiter=rate_limiter
).bind_tools(TOOLS)   


# -------------------------------------------------
# SYSTEM PROMPT
# -------------------------------------------------
SYSTEM_PROMPT = f"""
You are a quiz solving agent. You will be a given a url to a webpage that contains a task. 
The task may involve finding an answer and sending a request to a url specified in the webpage with a payload of structure mentioned in the webpage.
Once you send the request, you will get a response. The response will contain either whether your answer was correct or not, and the reason for it.
It may also contain a new task url to visit and repeat the process, or it may contain the same task url in some cases.

REMEMBER:
 - You can use all the tools at your disposal to complete the tasks.
 - Make sure to read all the contents in the webpage to find all the information needed to complete the task.
 - You can download all the files in the webpage and use them as needed.

Some tasks require the following information that you must:
- Email: {os.getenv("EMAIL")}
- Secret: {os.getenv("SECRET")}
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="messages")
])

llm_with_prompt = prompt | llm


# -------------------------------------------------
# AGENT NODE
# -------------------------------------------------
def agent_node(state: AgentState):
    result = llm_with_prompt.invoke({"messages": state["messages"]})
    return {"messages": state["messages"] + [result]}


# -------------------------------------------------
# GRAPH
# -------------------------------------------------
def route(state):
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END
graph = StateGraph(AgentState)

graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(TOOLS))



graph.add_edge(START, "agent")
graph.add_edge("tools", "agent")
graph.add_conditional_edges(
    "agent",    
    route       
)

app = graph.compile()


# -------------------------------------------------
# TEST
# -------------------------------------------------
url = "https://tds-llm-analysis.s-anand.net/demo"
def run_agent(url: str) -> str:
    out = app.invoke({
        "messages": [{"role": "user", "content": url}]},
        config={"recursion_limit": 50},
    )
    return out["messages"][-1]
