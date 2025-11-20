from langgraph.graph import StateGraph, END, START
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.prebuilt import ToolNode
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tools import generate_and_run, get_rendered_html, download_file, post_request
from typing import TypedDict, Annotated, List, Any
from langchain.chat_models import init_chat_model
from langgraph.graph.message import add_messages
# -------------------------------------------------
# STATE
# -------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]


TOOLS = [generate_and_run, get_rendered_html, download_file, post_request]


# -------------------------------------------------
# GEMINI LLM
# -------------------------------------------------
# NOTE: pip install langchain-google-genai
# Make sure GOOGLE_API_KEY is in env
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
SYSTEM_PROMPT = """
You are a tool-using agent.
Always call a tool when math or structured data is involved.
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
graph = StateGraph(AgentState)

graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(TOOLS))


def route(state):
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"

    return END

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
if __name__ == "__main__":
    out = app.invoke({
        "messages": [{"role": "user", "content": """
                      Do the task that is mentioned in
                    https://tds-llm-analysis.s-anand.net/demo. Complete all the tasks until all are done. If my email was asked
                      use "24f1001482@ds.study.iitm.ac.in" as placeholder. If the secret is asked use the following placeholder: "sai123".
                      Use all the content in the webpage to complete the tasks. Make sure to download any files in the webpage and use them as needed.
                      """}]},
        config={"recursion_limit": 50},
    )

    print(out["messages"][-1].content)
