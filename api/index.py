from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse
from tinydb import TinyDB
import fitz  # PyMuPDF for PDF parsing
import re, os

app = FastAPI()

# Database file inside Vercel's temp directory
db_path = "/tmp/mcp_db.json"
db = TinyDB(db_path)

# --- 1️⃣  Ingest Route: upload & store PDF text ---
@app.post("/mcp/ingest")
async def ingest(file: UploadFile = File(...)):
    try:
        # Save uploaded PDF to /tmp
        pdf_path = f"/tmp/{file.filename}"
        with open(pdf_path, "wb") as f:
            f.write(await file.read())

        # Extract text from PDF
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text("text") + "\n"
        doc.close()

        # Store document text in TinyDB
        db.insert({"filename": file.filename, "text": text})
        print(f"✅ Stored {file.filename} ({len(text)} chars)")

        return JSONResponse({"mcp_document_id": file.filename})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# --- 2️⃣  Query Route: retrieve relevant text chunks ---
@app.post("/mcp/query_collection")
async def query_collection(request: Request):
    try:
        data = await request.json()
        question = data.get("question", "").lower()

        # Simple keyword-based retrieval
        docs = db.all()
        results = []
        for d in docs:
            text = d["text"]
            # Split text into small paragraphs
            chunks = re.split(r"\n\s*\n", text)
            for c in chunks:
                if any(word in c.lower() for word in question.split()):
                    results.append(c.strip())

        if not results:
            return JSONResponse({"chunks": []})

        # Return top 3 relevant chunks
        return JSONResponse({"chunks": results[:3]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

