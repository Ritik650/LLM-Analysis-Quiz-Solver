from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from agent import run_agent
from dotenv import load_dotenv
import uvicorn
import os 
load_dotenv()

EMAIL = os.getenv("EMAIL") 
SECRET = os.getenv("SECRET")

app = FastAPI()
@app.post("/solve")
async def solve(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not data:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    url = data.get("url")
    secret = data.get("secret")
    if not url or not secret:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    if secret != SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    background_tasks.add_task(run_agent, url)

    return JSONResponse(status_code=200, content={"status": "ok"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)