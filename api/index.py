from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/mcp/ingest")
async def ingest(file: UploadFile = File(...)):
    # Read the uploaded PDF (for now, just confirm it was received)
    content = await file.read()
    print(f"✅ Received file: {file.filename} ({len(content)} bytes)")
    # Return a fake MCP document ID
    return JSONResponse({"mcp_document_id": file.filename})

@app.post("/mcp/query_collection")
async def query_collection(request: Request):
    data = await request.json()
    question = data.get("question", "")
    print(f"💬 Query received: {question}")
    # Return a simple dummy answer
    return JSONResponse({
        "answer": f"This is a test MCP response for: {question}",
        "citations": []
    })

