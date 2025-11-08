from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse
from tinydb import TinyDB, Query
import fitz  # PyMuPDF for PDF parsing
import re, os
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import uuid

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

# Separate tables for documents and chunks
documents_table = db.table("documents")
chunks_table = db.table("chunks")

def chunk_text_intelligently(text: str, page_num: int, doc_id: str, max_chunk_size: int = 500) -> List[Dict[str, Any]]:
    """
    Chunk text intelligently for research papers:
    - Preserve paragraph boundaries
    - Track page numbers and positions
    - Create citation-ready chunks
    """
    chunks = []
    
    # Split by double newlines (paragraphs) first
    paragraphs = re.split(r"\n\s*\n+", text)
    
    current_chunk = ""
    chunk_start_pos = 0
    chunk_id = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        # If adding this paragraph would exceed max size, save current chunk
        if current_chunk and len(current_chunk) + len(para) > max_chunk_size:
            chunk_id += 1
            chunk_identifier = f"{doc_id}_p{page_num}_c{chunk_id}"
            chunks.append({
                "chunk_id": chunk_identifier,
                "document_id": doc_id,
                "text": current_chunk.strip(),
                "page_num": page_num,
                "char_start": chunk_start_pos,
                "char_end": chunk_start_pos + len(current_chunk),
                "chunk_index": chunk_id
            })
            chunk_start_pos += len(current_chunk)
            current_chunk = para + "\n\n"
        else:
            current_chunk += para + "\n\n"
    
    # Add the last chunk
    if current_chunk.strip():
        chunk_id += 1
        chunk_identifier = f"{doc_id}_p{page_num}_c{chunk_id}"
        chunks.append({
            "chunk_id": chunk_identifier,
            "document_id": doc_id,
            "text": current_chunk.strip(),
            "page_num": page_num,
            "char_start": chunk_start_pos,
            "char_end": chunk_start_pos + len(current_chunk),
            "chunk_index": chunk_id
        })
    
    return chunks

# --- 1️⃣  Ingest Route: upload & store PDF text with chunking ---
@app.post("/mcp/ingest")
async def ingest(file: UploadFile = File(...)):
    try:
        # Generate document ID
        doc_id = str(uuid.uuid4())
        
        # Save uploaded PDF to /tmp
        pdf_path = f"/tmp/{doc_id}_{file.filename}"
        with open(pdf_path, "wb") as f:
            f.write(await file.read())

        # Extract text from PDF with page-level tracking
        doc = fitz.open(pdf_path)
        all_chunks = []
        total_pages = len(doc)
        
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if not text.strip():
                continue
                
            # Chunk this page's text
            page_chunks = chunk_text_intelligently(text, page_num, doc_id)
            all_chunks.extend(page_chunks)
        
        doc.close()
        
        # Store document metadata
        documents_table.insert({
            "document_id": doc_id,
            "filename": file.filename,
            "total_pages": total_pages,
            "total_chunks": len(all_chunks),
            "pdf_path": pdf_path
        })
        
        # Store all chunks with metadata
        if all_chunks:
            chunks_table.insert_multiple(all_chunks)
        
        print(f"✅ Stored {file.filename} ({len(all_chunks)} chunks across {total_pages} pages)")

        return JSONResponse({
            "mcp_document_id": doc_id,
            "chunks_created": len(all_chunks),
            "total_pages": total_pages
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# --- 2️⃣  Query Route: retrieve relevant text chunks with citation metadata ---
@app.post("/mcp/query_collection")
async def query_collection(request: Request):
    try:
        data = await request.json()
        question = data.get("question", "").lower()
        max_results = data.get("max_results", 5)

        # Simple keyword-based retrieval
        all_chunks = chunks_table.all()
        results = []
        
        question_words = question.split()
        
        for chunk in all_chunks:
            chunk_text = chunk.get("text", "").lower()
            # Count keyword matches for relevance scoring
            score = sum(1 for word in question_words if word in chunk_text)
            
            if score > 0:
                doc_id = chunk.get("document_id")
                # Get document info
                Doc = Query()
                doc_info = documents_table.get(Doc.document_id == doc_id) or {}
                
                results.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "text": chunk.get("text"),
                    "document_id": doc_id,
                    "page_num": chunk.get("page_num"),
                    "char_start": chunk.get("char_start"),
                    "char_end": chunk.get("char_end"),
                    "relevance_score": score,
                    "citation": {
                        "document_id": doc_id,
                        "filename": doc_info.get("filename", "Unknown"),
                        "page": chunk.get("page_num"),
                        "location": f"Page {chunk.get('page_num')}, Chunk {chunk.get('chunk_index')}",
                        "chunk_id": chunk.get("chunk_id")
                    }
                })
        
        # Sort by relevance score
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        # Format results with citation-ready metadata
        formatted_results = []
        for r in results[:max_results]:
            formatted_results.append({
                "chunk_id": r["chunk_id"],
                "text": r["text"],
                "citation": r["citation"],
                "relevance_score": r["relevance_score"]
            })

        if not formatted_results:
            return JSONResponse({"chunks": [], "citations": {}})

        # Create a citations map for easy lookup
        citations_map = {r["chunk_id"]: r["citation"] for r in formatted_results}

        return JSONResponse({
            "chunks": formatted_results,
            "citations": citations_map,
            "total_matches": len(results)
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

