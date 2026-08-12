# Insurance Claim RAG (Retrieval-Augmented Generation)

A lightweight, high-performance RAG pipeline that allows you to ask questions about your insurance documents and get accurate, grounded answers.

It uses **local embeddings** for private and cost-free document indexing, combined with **Groq's high-speed API** for generating answers using the state-of-the-art `llama-3.3-70b-versatile` model.

---

## Features

- **Two-Stage Retrieval (Bi-Encoder + Cross-Encoder Reranking)**:
  * **Bi-Encoder**: Chroma's built-in local embedding engine (`all-MiniLM-L6-v2` ONNX) acts as a Bi-Encoder, quickly retrieving the top 10 candidate chunks.
  * **Cross-Encoder**: Uses a local `cross-encoder/ms-marco-MiniLM-L-6-v2` model to rerank the candidates and select the top 3 most relevant chunks to send to the LLM, significantly improving retrieval precision.
- **Ultra-Fast Generation**: Powered by **Groq** (`llama-3.3-70b-versatile`) for extremely low-latency completions.
- **Strict Grounding Rules**: The LLM is strictly constrained to only answer from the provided documents and always cite the source file and page number. If the answer isn't in the documents, it will output *"I don't know based on the provided documents."*

---

## Setup Instructions

### 1. Install Dependencies
Make sure you have Python 3 installed. Install the required libraries via `pip3`:
```bash
pip3 install -r requirements.txt
```

### 2. Configure Environment Variables
Create a file named `.env` in the root of the project directory and add your Groq API key:
```env
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Add Your Documents
Create a folder named `insurance_docs/` in the root directory (if it doesn't already exist) and place your insurance policy PDF documents inside it (e.g., `policy.pdf`).

---

## Usage

Run the main interactive script:
```bash
python3 main.py
```

### Flow of Execution:
1. **Load**: The script extracts text page-by-page from all PDF files inside `insurance_docs/`.
2. **Chunk**: Text is split into overlapping token-based chunks (150 tokens with 30-token overlap) using `tiktoken`.
3. **Embed & Index**: The chunks are embedded locally and stored in a persistent directory (`./chroma_db`).
4. **Query Loop**: Enter your question. The system:
   * Retrieves the top 10 candidate chunks using the local Bi-Encoder (Chroma).
   * Reranks them using the local Cross-Encoder.
   * Prompts the Groq LLM with the top 3 most relevant chunks to generate the grounded answer.
5. **Exit**: Type `exit` to quit the program.
