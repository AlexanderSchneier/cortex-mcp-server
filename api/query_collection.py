from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os, requests

app = FastAPI()

CORTEX_API_URL = os.getenv("CORTEX_API_URL")

@app.post("/mcp/query_collection")
async def mcp_query_collection(request: Request):
    data = await request.json()
    question = data.get("question", "")

    # Forward to your FastAPI backend
    try:
        response = requests.post(
            f"{CORTEX_API_URL}/mcp/query_collection",
            json={"question": question},
            timeout=10
        )
        response.raise_for_status()
        return JSONResponse(content=response.json())
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

