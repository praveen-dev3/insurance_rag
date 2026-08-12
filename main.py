import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pypdf import PdfReader
from sentence_transformers import CrossEncoder
import tiktoken

# Load environment variables from .env file
load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY environment variable is not set."
    )

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# LLM used for final answer
LLM_MODEL = "llama-3.3-70b-versatile"

# Chunk configuration (in tokens)
# Kept well under the 256 word-piece truncation limit of Chroma's
# default embedder (all-MiniLM-L6-v2), so no chunk is embedded partially.
CHUNK_SIZE = 150
CHUNK_OVERLAP = 30

# Number of chunks retrieved by Bi-Encoder (Chroma)
BI_ENCODER_TOP_K = 10

# Final number of chunks selected by Cross-Encoder for the LLM
TOP_K = 3

DOCUMENTS_FOLDER = "insurance_docs"
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "insurance_documents"

# Bumped whenever the chunking or embedding strategy changes, so an
# index built by an older version of this script is not silently reused.
INDEX_SCHEMA_VERSION = "2"


# ============================================================
# GROQ CLIENT
# ============================================================

client = OpenAI(
    base_url=GROQ_BASE_URL,
    api_key=GROQ_API_KEY,
    timeout=60.0,
    max_retries=3
)


# ============================================================
# CROSS-ENCODER MODEL (RERANKER)
# ============================================================

print("Loading local Cross-Encoder model...")
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")



# ============================================================
# 1. LOAD PDF DOCUMENTS
# ============================================================

def find_pdf_files():
    """
    Return the sorted list of PDFs in the documents folder.
    """

    folder = Path(DOCUMENTS_FOLDER)

    if not folder.exists():
        raise FileNotFoundError(
            f"Folder '{DOCUMENTS_FOLDER}' does not exist."
        )

    pdf_files = sorted(folder.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"No PDF files found inside '{DOCUMENTS_FOLDER}'."
        )

    return pdf_files


def compute_corpus_fingerprint(pdf_files):
    """
    Hash the corpus contents plus the settings that shape the index.

    Any change to a PDF, an added/removed file, or a change to the
    chunking configuration produces a different fingerprint, which is
    what tells us the stored index is stale.
    """

    digest = hashlib.sha256()

    # Settings that would invalidate existing chunks.
    digest.update(
        f"v{INDEX_SCHEMA_VERSION}|{CHUNK_SIZE}|{CHUNK_OVERLAP}".encode()
    )

    for pdf_path in pdf_files:

        digest.update(pdf_path.name.encode())

        with pdf_path.open("rb") as handle:

            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)

    return digest.hexdigest()


def load_documents(pdf_files):
    """
    Read the text of every page of every PDF.
    """

    documents = []

    for pdf_path in pdf_files:

        print(f"Loading: {pdf_path.name}")

        try:
            reader = PdfReader(str(pdf_path))
        except Exception as error:
            print(f"  Skipped (unreadable PDF): {error}")
            continue

        page_count = 0

        for page_number, page in enumerate(reader.pages):

            try:
                text = page.extract_text()
            except Exception as error:
                print(f"  Page {page_number + 1} failed to parse: {error}")
                continue

            if not text or not text.strip():
                continue

            page_count += 1

            documents.append({
                "text": text,
                "source": pdf_path.name,
                "page": page_number + 1
            })

        if page_count == 0:
            print(
                f"  Warning: no extractable text in {pdf_path.name}. "
                "It may be a scanned PDF that needs OCR."
            )

    if not documents:
        raise ValueError(
            "No text could be extracted from any PDF. "
            "Scanned documents require OCR before indexing."
        )

    print(f"\nLoaded {len(documents)} pages.")

    return documents


# ============================================================
# 2. CHUNKING
# ============================================================

def create_chunks(documents):
    """
    Split each document into overlapping token-based chunks.

    Tokens are streamed across the whole document rather than restarting
    at every page, so a clause interrupted by a page break stays intact.
    Each chunk records the page range it spans, which keeps citations exact.
    """

    encoding = tiktoken.get_encoding("cl100k_base")

    pages_by_source = defaultdict(list)

    for document in documents:
        pages_by_source[document["source"]].append(document)

    chunks = []

    for source in sorted(pages_by_source):

        pages = sorted(
            pages_by_source[source],
            key=lambda page: page["page"]
        )

        # One continuous token stream per document, plus a parallel
        # array remembering which page each token came from.
        tokens = []
        token_pages = []

        for page in pages:

            page_tokens = encoding.encode(page["text"] + "\n")

            tokens.extend(page_tokens)
            token_pages.extend([page["page"]] * len(page_tokens))

        start = 0

        while start < len(tokens):

            end = min(start + CHUNK_SIZE, len(tokens))

            chunk_text = encoding.decode(tokens[start:end])

            if chunk_text.strip():

                chunk_pages = token_pages[start:end]

                chunks.append({
                    "text": chunk_text,
                    "source": source,
                    "page_start": chunk_pages[0],
                    "page_end": chunk_pages[-1]
                })

            if end == len(tokens):
                # Final window; stepping forward again would emit a
                # duplicate tail chunk.
                break

            # Move forward while keeping overlap
            start += CHUNK_SIZE - CHUNK_OVERLAP

    print(f"Created {len(chunks)} chunks.")

    return chunks


def build_chunk_ids(chunks):
    """
    Derive a stable ID from the chunk's document and its content.

    Content-derived IDs mean a chunk keeps its identity when unrelated
    parts of the corpus change, instead of being reassigned to different
    text the way positional 'chunk-0, chunk-1, ...' IDs are.
    """

    ids = []
    seen = defaultdict(int)

    for chunk in chunks:

        content_hash = hashlib.sha1(
            chunk["text"].encode("utf-8")
        ).hexdigest()[:16]

        base_id = f"{chunk['source']}#{content_hash}"

        # Identical text can legitimately appear twice (headers, footers,
        # boilerplate clauses); disambiguate rather than drop one.
        occurrence = seen[base_id]
        seen[base_id] += 1

        ids.append(
            base_id if occurrence == 0 else f"{base_id}-{occurrence}"
        )

    return ids


# ============================================================
# 3. CREATE / CONNECT TO CHROMA
# ============================================================

def format_pages(chunk):
    """
    Human-readable page reference for a chunk.
    """

    if chunk["page_start"] == chunk["page_end"]:
        return str(chunk["page_start"])

    return f"{chunk['page_start']}-{chunk['page_end']}"


def create_vector_database(chroma_client, chunks, fingerprint):

    # Drop any previous index; the caller only gets here when the stored
    # one is missing, empty, or stale.
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    # Use Chroma's default local embedding function (all-MiniLM-L6-v2)
    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "Insurance claim documents",
            "fingerprint": fingerprint
        }
    )

    print("\nCreating local embeddings and storing chunks in Chroma...")

    ids = build_chunk_ids(chunks)

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    metadatas = [
        {
            "source": chunk["source"],
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"]
        }
        for chunk in chunks
    ]

    # Chroma rejects a single add() larger than its max batch size.
    try:
        batch_size = chroma_client.get_max_batch_size()
    except Exception:
        batch_size = 1000

    for offset in range(0, len(chunks), batch_size):

        upper = offset + batch_size

        # Chroma embeds the documents locally using its default engine
        collection.add(
            ids=ids[offset:upper],
            documents=texts[offset:upper],
            metadatas=metadatas[offset:upper]
        )

        if len(chunks) > batch_size:
            print(f"  Indexed {min(upper, len(chunks))}/{len(chunks)} chunks")

    print(
        f"Stored {len(chunks)} chunks in Chroma."
    )

    return collection


def load_or_build_collection(chroma_client, force_reindex=False):
    """
    Reuse the persisted index only when it matches the documents on disk.
    """

    pdf_files = find_pdf_files()
    fingerprint = compute_corpus_fingerprint(pdf_files)

    if not force_reindex:

        try:
            collection = chroma_client.get_collection(COLLECTION_NAME)
        except Exception:
            collection = None

        if collection is not None:

            metadata = collection.metadata or {}
            stored_fingerprint = metadata.get("fingerprint")

            if collection.count() == 0:
                print("\nStored index is empty. Rebuilding...")

            elif stored_fingerprint != fingerprint:
                print(
                    "\nDocuments or chunking settings changed since the "
                    "index was built. Rebuilding..."
                )

            else:
                print(
                    f"\nUsing existing Chroma database from '{CHROMA_PATH}' "
                    f"with {collection.count()} chunks."
                )
                return collection

    documents = load_documents(pdf_files)

    chunks = create_chunks(documents)

    return create_vector_database(
        chroma_client,
        chunks,
        fingerprint
    )


# ============================================================
# 4. TOP-K SIMILARITY SEARCH
# ============================================================

def retrieve_chunks(collection, question):

    # 1. Retrieve top candidates using the Bi-Encoder (Chroma DB)
    #    Asking for more rows than exist is fine, but keep it honest.
    n_results = min(BI_ENCODER_TOP_K, max(collection.count(), 1))

    results = collection.query(
        query_texts=[question],
        n_results=n_results
    )

    retrieved_documents = (results.get("documents") or [[]])[0]
    retrieved_metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    candidates = []

    for document, metadata, distance in zip(
        retrieved_documents,
        retrieved_metadatas,
        distances
    ):

        candidates.append({
            "text": document,
            "source": metadata.get("source", "unknown"),
            "page_start": metadata.get("page_start", 0),
            "page_end": metadata.get("page_end", 0),
            "distance": distance
        })

    if not candidates:
        return []

    # 2. Rerank the candidates using the Cross-Encoder
    pairs = [[question, chunk["text"]] for chunk in candidates]
    scores = cross_encoder.predict(pairs)

    for chunk, score in zip(candidates, scores):
        chunk["cross_score"] = float(score)

    # Sort descending by cross-encoder score (higher is more relevant)
    candidates.sort(key=lambda x: x["cross_score"], reverse=True)

    # 3. Select the top-K chunks to pass to the LLM
    retrieved_chunks = candidates[:TOP_K]

    return retrieved_chunks


# ============================================================
# 7. BUILD GROUNDED PROMPT
# ============================================================

def build_prompt(question, retrieved_chunks):

    context_parts = []

    for index, chunk in enumerate(
        retrieved_chunks,
        start=1
    ):

        context_parts.append(
            f"""
SOURCE {index}
Document: {chunk['source']}
Page: {format_pages(chunk)}

{chunk['text']}
"""
        )

    context = "\n".join(context_parts)

    prompt = f"""
You are an insurance document assistant.

You must answer the user's question ONLY using
the information contained in the provided documents.

IMPORTANT RULES:

1. Do not use outside knowledge.
2. Do not invent missing information.
3. If the documents do not contain enough information,
   say:

   "I don't know based on the provided documents."

4. If the document gives a conditional rule,
   preserve that condition in your answer.
5. Do not assume that a condition is satisfied unless
   the documents explicitly say so.
6. Always mention the source document and page.

DOCUMENTS:

{context}

USER QUESTION:

{question}

ANSWER:
"""

    return prompt


# ============================================================
# 8. GENERATE FINAL ANSWER
# ============================================================

def generate_answer(question, retrieved_chunks):

    if not retrieved_chunks:
        return "I don't know based on the provided documents."

    prompt = build_prompt(
        question,
        retrieved_chunks
    )

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,

            temperature=0,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict document-grounded "
                        "insurance assistant."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
    except OpenAIError as error:
        return f"The language model request failed: {error}"

    return response.choices[0].message.content


# ============================================================
# 9. ASK QUESTION
# ============================================================

def ask_question(collection, question):

    print("\n" + "=" * 70)
    print("QUESTION")
    print("=" * 70)

    print(question)

    # -----------------------------------------
    # Retrieval
    # -----------------------------------------

    retrieved_chunks = retrieve_chunks(
        collection,
        question
    )

    print("\n" + "=" * 70)
    print("RETRIEVED CHUNKS")
    print("=" * 70)

    if not retrieved_chunks:
        print("\nNo matching chunks found.")

    for index, chunk in enumerate(
        retrieved_chunks,
        start=1
    ):

        print(f"\n--- Chunk {index} ---")

        print(
            f"Source: {chunk['source']}"
        )

        print(
            f"Page: {format_pages(chunk)}"
        )

        print(
            f"Bi-Encoder Distance: {chunk['distance']:.4f}"
        )

        print(
            f"Cross-Encoder Score: {chunk['cross_score']:.4f}"
        )

        print(
            f"Text:\n{chunk['text'][:500]}"
        )

    # -----------------------------------------
    # Generation
    # -----------------------------------------

    answer = generate_answer(
        question,
        retrieved_chunks
    )

    print("\n" + "=" * 70)
    print("FINAL ANSWER")
    print("=" * 70)

    print(answer)

    return answer


# ============================================================
# 10. MAIN
# ============================================================

def main():

    print("=" * 70)
    print("INSURANCE CLAIM RAG")
    print("=" * 70)

    force_reindex = "--reindex" in sys.argv

    chroma_client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    collection = load_or_build_collection(
        chroma_client,
        force_reindex=force_reindex
    )

    print("\nRAG system is ready!")

    # -----------------------------------------
    # Interactive question loop
    # -----------------------------------------

    while True:

        try:
            question = input(
                "\nAsk an insurance question "
                "(type 'exit' to quit): "
            )
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if question.lower() == "exit":
            print("Goodbye!")
            break

        if not question.strip():
            continue

        ask_question(
            collection,
            question
        )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    main()
