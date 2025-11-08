from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse
from tinydb import TinyDB
import fitz  # PyMuPDF for PDF parsing
import re, os
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or specify ["http://localhost:3000/", "https://your-frontend.vercel.app/"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




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
    data = await request.json()
    question = data.get("question", "").lower()
    keywords = [w.strip(".,?") for w in question.split() if len(w) > 2]

    docs = db.all()
    results = []

    for d in docs:
        text = d["text"]
        chunks = re.split(r"\n\s*\n", text)
        doc_hits = []

        for c in chunks:
            lowered = c.lower()
            if any(w in lowered for w in keywords):
                doc_hits.append(c.strip())

        # take top 2 matches per doc to ensure coverage
        if doc_hits:
            results.extend(doc_hits[:2])

    if not results:
        return JSONResponse({"chunks": []})

    # limit total to top 6–8 to stay concise
    return JSONResponse({"chunks": results[:8]})
