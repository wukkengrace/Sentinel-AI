"""
ingest_kb.py — Ingests disaster-management PDFs into ChromaDB using Ollama embeddings.
Documents are taken from metadata.txt. Only TVM-relevant docs are prioritised.

Run: python ingest_kb.py
Requirements: chromadb, ollama (running locally), PyMuPDF (fitz)
"""

import os
import json
import chromadb
from chromadb.utils import embedding_functions

# ── Config ────────────────────────────────────────────────────────────────────
PDF_DIR     = os.path.join(os.path.dirname(__file__), "pdfs")   # put PDFs here
CHROMA_DIR  = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION  = "sentinel_kb"
OLLAMA_MODEL = "nomic-embed-text"   # fast embedding model via Ollama
CHUNK_SIZE  = 500    # characters per chunk (tune based on your PDF density)
CHUNK_OVERLAP = 80

# ── Metadata from metadata.txt ────────────────────────────────────────────────
DEFAULT_METADATA = [
    {
        "mapped_filename": "Disaster-Bill-2024.pdf",
        "title": "Disaster Management (Amendment) Bill, 2024",
        "category": "Bill",
        "jurisdiction": "National",
        "tags": ["flood","disaster-management","bill","national"]
    },
    {
        "mapped_filename": "Thiruvananthapuram-Plan.pdf",
        "title": "Hospital Disaster Management Plan for Thiruvananthapuram",
        "category": "Hospital Plan",
        "jurisdiction": "Kerala (District)",
        "tags": ["flood","disaster-management","hospital-plan","thiruvananthapuram"]
    },
    {
        "mapped_filename": "Orange-Book-2025.pdf",
        "title": "Standard Operating Procedures for Disaster Management (Orange Book 2025)",
        "category": "SOP",
        "jurisdiction": "Kerala",
        "tags": ["flood","disaster-management","sop","kerala"]
    },
]

def load_metadata():
    """Attempt to load metadata from data/metadata.txt, which should be valid JSON array."""
    txt_path = os.path.join(os.path.dirname(__file__), "data", "metadata.txt")
    if not os.path.exists(txt_path):
        print(f"[WARN] {txt_path} not found. Using default mock metadata.")
        return DEFAULT_METADATA
    
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
            data = json.loads(content)
            print(f"[INFO] Loaded {len(data)} document definitions from metadata.txt.")
            return data
    except Exception as e:
        print(f"[ERROR] Failed to parse metadata.txt as JSON: {e}")
        print("[WARN] Using default mock metadata instead.")
        return DEFAULT_METADATA

RAW_METADATA = load_metadata()

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


def extract_text_from_pdf(path: str) -> str:
    """Extract all text from a PDF using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        return full_text
    except ImportError:
        print("[WARN] PyMuPDF not installed — using placeholder text.")
        return f"[Placeholder text for {os.path.basename(path)}]"
    except Exception as e:
        print(f"[ERROR] Could not read {path}: {e}")
        return ""


def ingest():
    """Main ingestion function."""
    # ── Setup ChromaDB with Ollama embeddings ─────────────────────────────
    try:
        ef = embedding_functions.OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name=OLLAMA_MODEL
        )
    except Exception:
        print("[WARN] Ollama embedding fn unavailable. Using default embeddings.")
        ef = embedding_functions.DefaultEmbeddingFunction()

    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Delete old collection for clean re-ingest
    try:
        client.delete_collection(COLLECTION)
        print(f"[INGEST] Cleared old collection '{COLLECTION}'")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}  # cosine similarity
    )

    total_chunks = 0

    for meta in RAW_METADATA:
        pdf_path = os.path.join(PDF_DIR, meta["mapped_filename"])

        if not os.path.exists(pdf_path):
            print(f"[SKIP] PDF not found: {pdf_path}")
            # Still register a stub so queries don't crash
            text = f"Document: {meta['title']}. Category: {meta['category']}. Jurisdiction: {meta['jurisdiction']}."
        else:
            print(f"[READ] {meta['mapped_filename']}")
            text = extract_text_from_pdf(pdf_path)

        if not text.strip():
            print(f"[SKIP] Empty text for {meta['mapped_filename']}")
            continue

        chunks = chunk_text(text)
        print(f"  → {len(chunks)} chunks")

        # Build ChromaDB metadata (STRICT filter fields: region + category)
        chroma_meta = {
            "source":       meta["mapped_filename"],
            "title":        meta["title"],
            "category":     meta["category"],
            "jurisdiction": meta["jurisdiction"],
            "region":       "TVM" if "thiruvananthapuram" in " ".join(meta["tags"]).lower()
                            else "Kerala",
            "tags":         ",".join(meta["tags"])
        }

        ids      = [f"{meta['mapped_filename']}__chunk_{i}" for i in range(len(chunks))]
        metas    = [chroma_meta] * len(chunks)

        # Upsert in batches of 50 to avoid memory spikes
        BATCH = 50
        for b_start in range(0, len(chunks), BATCH):
            b_end = b_start + BATCH
            collection.upsert(
                ids=ids[b_start:b_end],
                documents=chunks[b_start:b_end],
                metadatas=metas[b_start:b_end]
            )

        total_chunks += len(chunks)

    print(f"\n[INGEST] Done — {total_chunks} chunks across {len(RAW_METADATA)} documents.")
    return collection


def query_kb(question: str, region: str = "TVM", category: str = None, n: int = 4):
    """
    Query the knowledge base with strict metadata filtering.
    Args:
        question: Natural language query
        region:   'TVM' or 'Kerala' — strict filter
        category: Optional — 'SOP', 'Act', 'Hospital Plan', etc.
        n:        Number of results
    Returns:
        List of (document_text, metadata, distance) tuples
    """
    try:
        ef = embedding_functions.OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name=OLLAMA_MODEL
        )
    except Exception:
        ef = embedding_functions.DefaultEmbeddingFunction()

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION, embedding_function=ef)

    # Build where filter
    where = {"$or": [{"region": region}, {"region": "Kerala"}]}
    if category:
        where = {
            "$and": [
                {"$or": [{"region": region}, {"region": "Kerala"}]},
                {"category": category}
            ]
        }

    results = collection.query(
        query_texts=[question],
        n_results=n,
        where=where,
        include=["documents", "metadatas", "distances"]
    )

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        output.append({
            "text":     doc,
            "source":   meta.get("title", meta.get("source", "Unknown")),
            "category": meta.get("category"),
            "distance": round(dist, 4)
        })

    return output


if __name__ == "__main__":
    os.makedirs(PDF_DIR, exist_ok=True)
    ingest()