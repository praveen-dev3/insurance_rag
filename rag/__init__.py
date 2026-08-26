"""Insurance document RAG pipeline.

The package is split so that the CLI (`main.py`) and the web server
(`server.py`) drive the exact same retrieval and generation code.
"""

from rag.engine import RagEngine, RetrievedChunk, format_pages

__all__ = ["RagEngine", "RetrievedChunk", "format_pages"]
