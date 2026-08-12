import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI
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
CHUNK_SIZE = 150
CHUNK_OVERLAP = 30

# Number of chunks retrieved by Bi-Encoder (Chroma)
BI_ENCODER_TOP_K = 10

# Final number of chunks selected by Cross-Encoder for the LLM
TOP_K = 3

DOCUMENTS_FOLDER = "insurance_docs"
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "insurance_documents"


# ============================================================
# GROQ CLIENT
# ============================================================

client = OpenAI(
    base_url=GROQ_BASE_URL,
    api_key=GROQ_API_KEY
)


# ============================================================
# CROSS-ENCODER MODEL (RERANKER)
# ============================================================

print("Loading local Cross-Encoder model...")
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")



# ============================================================
# 1. LOAD PDF DOCUMENTS
# ============================================================

def load_documents():
    """
    Read all PDF files from insurance_docs/
    """

    documents = []

    folder = Path(DOCUMENTS_FOLDER)

    if not folder.exists():
        raise FileNotFoundError(
            f"Folder '{DOCUMENTS_FOLDER}' does not exist."
        )

    pdf_files = list(folder.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"No PDF files found inside '{DOCUMENTS_FOLDER}'."
        )

    for pdf_path in pdf_files:

        print(f"Loading: {pdf_path.name}")

        reader = PdfReader(str(pdf_path))

        for page_number, page in enumerate(reader.pages):

            text = page.extract_text()

            if not text:
                continue

            documents.append({
                "text": text,
                "source": pdf_path.name,
                "page": page_number + 1
            })

    print(f"\nLoaded {len(documents)} pages.")

    return documents


# ============================================================
# 2. CHUNKING
# ============================================================

def create_chunks(documents):
    """
    Split pages into overlapping token-based chunks.
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks = []

    for document in documents:

        text = document["text"]

        # Convert text into token IDs
        tokens = encoding.encode(text)

        start = 0

        while start < len(tokens):

            end = start + CHUNK_SIZE

            chunk_tokens = tokens[start:end]

            # Decode token IDs back to a string
            chunk_text = encoding.decode(chunk_tokens)

            if chunk_text.strip():

                chunks.append({
                    "text": chunk_text,
                    "source": document["source"],
                    "page": document["page"]
                })

            # Move forward while keeping overlap
            start += CHUNK_SIZE - CHUNK_OVERLAP

    print(f"Created {len(chunks)} chunks.")

    return chunks


# ============================================================
# 3. CREATE / CONNECT TO CHROMA
# ============================================================

def create_vector_database(chunks):

    chroma_client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    # Delete old collection so every run starts clean.
    # This is useful while learning.
    try:
        chroma_client.delete_collection(
            COLLECTION_NAME
        )
    except Exception:
        pass

    # Use Chroma's default local embedding function (all-MiniLM-L6-v2)
    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "Insurance claim documents"
        }
    )

    print("\nCreating local embeddings and storing chunks in Chroma...")

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    ids = [
        f"chunk-{index}"
        for index in range(len(chunks))
    ]

    metadatas = [
        {
            "source": chunk["source"],
            "page": chunk["page"]
        }
        for chunk in chunks
    ]

    # Chroma will automatically embed the documents locally using its default engine
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas
    )

    print(
        f"Stored {len(chunks)} chunks in Chroma."
    )

    return collection


# ============================================================
# 4. TOP-K SIMILARITY SEARCH
# ============================================================

def retrieve_chunks(collection, question):

    # 1. Retrieve top candidates using the Bi-Encoder (Chroma DB)
    results = collection.query(
        query_texts=[question],
        n_results=BI_ENCODER_TOP_K
    )

    retrieved_documents = results["documents"][0]
    retrieved_metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    candidates = []

    for document, metadata, distance in zip(
        retrieved_documents,
        retrieved_metadatas,
        distances
    ):

        candidates.append({
            "text": document,
            "source": metadata["source"],
            "page": metadata["page"],
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
Page: {chunk['page']}

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

    prompt = build_prompt(
        question,
        retrieved_chunks
    )

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

    for index, chunk in enumerate(
        retrieved_chunks,
        start=1
    ):

        print(f"\n--- Chunk {index} ---")

        print(
            f"Source: {chunk['source']}"
        )

        print(
            f"Page: {chunk['page']}"
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

    # Initialize Chroma client to check if collection already exists
    chroma_client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    collection = None
    try:
        # Try to retrieve the existing collection
        existing_collection = chroma_client.get_collection(
            name=COLLECTION_NAME
        )
        if existing_collection.count() > 0:
            collection = existing_collection
            print(f"\nUsing existing Chroma database from '{CHROMA_PATH}' with {collection.count()} chunks.")
    except Exception:
        # Collection does not exist or has an issue
        pass

    if collection is None:
        # -----------------------------------------
        # Load documents
        # -----------------------------------------
        documents = load_documents()

        # -----------------------------------------
        # Chunk documents
        # -----------------------------------------
        chunks = create_chunks(documents)

        # -----------------------------------------
        # Store embeddings in vector DB
        # -----------------------------------------
        collection = create_vector_database(
            chunks
        )

    print("\nRAG system is ready!")

    # -----------------------------------------
    # Interactive question loop
    # -----------------------------------------

    while True:

        question = input(
            "\nAsk an insurance question "
            "(type 'exit' to quit): "
        )

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