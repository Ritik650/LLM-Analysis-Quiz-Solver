from fastapi import FastAPI, Request
from agent import run_agent


app = FastAPI()

@app.post("/solve")
async def solve(request: Request):
    data = await request.json()
    url = data.get("url")

print(run_agent("https://tds-llm-analysis.s-anand.net/demo2"))

