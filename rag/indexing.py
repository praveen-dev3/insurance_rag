"""PDF loading and the Chroma index lifecycle.

Embeddings are computed here rather than by Chroma's built-in embedding
function, because the retrieval encoders need asymmetric query/passage
prefixes that Chroma's wrapper cannot express. See rag/embeddings.py.

Two lifecycles live here and they are not interchangeable:

  sync_collection          reconciles the index against the folder,
                           touching only the documents that changed. This
                           is what the app and the CLI use.
  create_vector_database   drops the collection and rebuilds it from
                           scratch. This is what the chunking sweep uses,
                           because comparing two chunkers requires that
                           every chunk in the collection came from the
                           same one.

The earlier version of this module only had the second, and defended it on
the grounds that content-hash chunk ids make an edit rename every chunk
after it, so computing a delta costs more than starting over. That is true
per document and false across documents: renaming every chunk of
HO-0304 says nothing about the chunks of policy.pdf. Reconciling at file
granularity keeps the cheap property (no diffing within a document) and
drops the expensive one (re-embedding documents that did not change).
"""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

from rag.chunking import create_chunks
from rag.config import (
    CHROMA_PATH,
    COLLECTION_NAME,
    DOCUMENTS_FOLDER,
    HNSW_EF_CONSTRUCTION,
    HNSW_EF_SEARCH,
    HNSW_MAX_NEIGHBORS,
    HNSW_SPACE,
    index_signature,
)
from rag.embeddings import get_embedder
from rag.metadata import (
    UNSPECIFIED,
    extract_document_metadata,
    strip_page_furniture,
)


def log(message, callback=None):
    """
    Emit progress to stdout, and to the caller when one is listening.

    The web server passes a callback so indexing progress can be streamed
    to the browser instead of disappearing into the server console.
    """

    print(message)

    if callback is not None:
        callback(message)


# ============================================================
# 1. LOAD PDF DOCUMENTS
# ============================================================

def find_pdf_files(folder=None):
    """
    Return the sorted list of PDFs in the documents folder.
    """

    folder = Path(folder or DOCUMENTS_FOLDER)

    if not folder.exists():
        raise FileNotFoundError(
            f"Folder '{folder}' does not exist."
        )

    pdf_files = sorted(folder.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"No PDF files found inside '{folder}'."
        )

    return pdf_files


def compute_file_fingerprint(pdf_path):
    """
    Hash one document plus the settings that shape how it is indexed.

    Per file, not per corpus. A corpus-wide hash cannot answer "which
    documents changed?", only "did anything change?", and answering only
    the second question is what forces a full re-index when six new
    endorsements land next to an unchanged policy wording.

    index_signature() is folded in so that a chunking or embedding change
    invalidates every file, which is correct: those chunks really are no
    longer comparable with the ones the new settings would produce.
    """

    digest = hashlib.sha256()

    digest.update(index_signature().encode())
    digest.update(pdf_path.name.encode())

    with pdf_path.open("rb") as handle:

        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def compute_corpus_fingerprint(pdf_files):
    """
    A single hash over the whole corpus, for the collection-level record.

    Retained so an index can still report which corpus state it was built
    from. It is no longer used to decide whether to rebuild - that is
    sync_collection's job, and it works per file.
    """

    digest = hashlib.sha256()

    digest.update(index_signature().encode())

    for pdf_path in sorted(pdf_files, key=lambda path: path.name):
        digest.update(compute_file_fingerprint(pdf_path).encode())

    return digest.hexdigest()


def load_documents(pdf_files, on_progress=None):
    """
    Read the text of every page of every PDF, with provenance attached.

    Document metadata is parsed once from the first page and stamped onto
    every page of that document, so it survives into every chunk no matter
    which strategy does the chunking. Page furniture is stripped here, for
    every strategy alike, because a running header repeated on forty pages
    is not content and being retrievable on it is not a win.
    """

    documents = []

    for pdf_path in pdf_files:

        log(f"Loading: {pdf_path.name}", on_progress)

        try:
            reader = PdfReader(str(pdf_path))
        except Exception as error:
            log(f"  Skipped (unreadable PDF): {error}", on_progress)
            continue

        raw_pages = []

        for page_number, page in enumerate(reader.pages):

            try:
                text = page.extract_text()
            except Exception as error:
                log(
                    f"  Page {page_number + 1} failed to parse: {error}",
                    on_progress
                )
                continue

            if not text or not text.strip():
                continue

            raw_pages.append((page_number + 1, text))

        if not raw_pages:
            log(
                f"  Warning: no extractable text in {pdf_path.name}. "
                "It may be a scanned PDF that needs OCR.",
                on_progress
            )
            continue

        metadata = extract_document_metadata(pdf_path.name, raw_pages[0][1])

        log(
            f"  {metadata.form_number} ed. {metadata.edition_date} "
            f"[{metadata.policy_line}] - {len(raw_pages)} pages",
            on_progress
        )

        for page_number, text in raw_pages:

            body = strip_page_furniture(text)

            if not body.strip():
                continue

            documents.append({
                "text": body,
                "source": pdf_path.name,
                "page": page_number,
                "metadata": metadata.as_dict(),
            })

    if not documents:
        raise ValueError(
            "No text could be extracted from any PDF. "
            "Scanned documents require OCR before indexing."
        )

    log(f"Loaded {len(documents)} pages.", on_progress)

    return documents


# ============================================================
# 2. CHUNK IDENTITY AND METADATA
# ============================================================

def build_chunk_ids(chunks):
    """
    Derive a stable ID from the chunk's document and its content.

    Content-derived IDs mean a chunk keeps its identity when unrelated
    parts of the corpus change, instead of being reassigned to different
    text the way positional 'chunk-0, chunk-1, ...' IDs are. That property
    is what lets a citation printed in an answer still resolve to the same
    text after an unrelated document is re-ingested.
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


def chunk_metadata(chunk, fingerprint=""):
    """
    The flat record Chroma stores alongside a chunk.

    Chroma metadata values must be scalars, so the exclusion code list is
    joined rather than nested. `source_file` is written unconditionally -
    the brief's failure condition is a chunk without one, and the only way
    to guarantee that is to derive it from the chunk's own source rather
    than from parsed metadata that could come back empty.
    """

    document = chunk.get("metadata") or {}

    codes = chunk.get("exclusion_codes") or []

    return {
        # Required by the brief.
        "source_file": document.get("source_file") or chunk["source"],
        "form_number": document.get("form_number", UNSPECIFIED),
        "policy_line": document.get("policy_line", UNSPECIFIED),
        "edition_date": document.get("edition_date", UNSPECIFIED),

        # Retained from the previous schema; the evaluator labels ground
        # truth at page level and needs these.
        "source": chunk["source"],
        "page_start": chunk["page_start"],
        "page_end": chunk["page_end"],

        # Citation support.
        "clause": chunk.get("clause", UNSPECIFIED),
        "clause_label": chunk.get("clause_label", UNSPECIFIED),
        "document_title": document.get("title", UNSPECIFIED),
        "exclusion_codes": ",".join(codes),

        # Incremental ingest bookkeeping.
        "file_fingerprint": fingerprint,
    }


def verify_ingest(chunks):
    """
    Refuse to write a chunk that has no source_file.

    The brief calls that a failed ingest, so it is enforced rather than
    reported: a silently unattributed chunk is a citation that cannot be
    checked, which is the specific failure this whole exercise is about.
    """

    orphans = [
        index
        for index, chunk in enumerate(chunks)
        if not (chunk.get("metadata") or {}).get("source_file")
        and not chunk.get("source")
    ]

    if orphans:
        raise ValueError(
            f"{len(orphans)} chunk(s) have no source_file and would be "
            f"unattributable. First offender at index {orphans[0]}."
        )

    return True


# ============================================================
# 3. CREATE / CONNECT TO CHROMA
# ============================================================

def collection_configuration():
    """
    HNSW settings for the vector index.

    HNSW is an approximate index: it trades exactness for speed, and
    these three numbers control that trade. ef_construction spends build
    time on a better graph; ef_search widens the beam at query time;
    max_neighbors (the 'M' of the paper) spends memory on more edges.
    All three raise recall.
    """

    return {
        "hnsw": {
            "space": HNSW_SPACE,
            "ef_construction": HNSW_EF_CONSTRUCTION,
            "ef_search": HNSW_EF_SEARCH,
            "max_neighbors": HNSW_MAX_NEIGHBORS,
        }
    }


def open_collection(chroma_client, name=None):
    """
    Fetch an existing collection without an embedding function.

    Every call site supplies vectors explicitly, so Chroma must not try
    to embed anything itself.
    """

    return chroma_client.get_collection(
        name or COLLECTION_NAME,
        embedding_function=None
    )


def add_chunks(collection, chunks, fingerprints=None, on_progress=None):
    """
    Embed a batch of chunks and write them to an existing collection.

    Shared by the full rebuild and the incremental sync so there is one
    place where a chunk becomes a row, and therefore one place where the
    metadata schema is decided.
    """

    if not chunks:
        return 0

    verify_ingest(chunks)

    embedder = get_embedder()
    fingerprints = fingerprints or {}

    log(
        f"Embedding {len(chunks)} chunks with {embedder.model_id}...",
        on_progress
    )

    ids = build_chunk_ids(chunks)
    texts = [chunk["text"] for chunk in chunks]

    metadatas = [
        chunk_metadata(chunk, fingerprints.get(chunk["source"], ""))
        for chunk in chunks
    ]

    # Encoded in one call so sentence-transformers can batch on the GPU
    # (or across cores) instead of paying per-chunk overhead.
    vectors = embedder.embed_passages(texts)

    # Chroma rejects a single add() larger than its max batch size, and
    # that limit depends on the build, so ask rather than assume.
    try:
        batch_size = collection._client.get_max_batch_size()
    except Exception:
        batch_size = 1000

    for offset in range(0, len(chunks), batch_size):

        upper = offset + batch_size

        # upsert rather than add: an incremental re-ingest of an unchanged
        # document would otherwise collide on the content-hash id.
        collection.upsert(
            ids=ids[offset:upper],
            documents=texts[offset:upper],
            metadatas=metadatas[offset:upper],
            embeddings=vectors[offset:upper].tolist()
        )

        if len(chunks) > batch_size:
            log(
                f"  Indexed {min(upper, len(chunks))}/{len(chunks)} chunks",
                on_progress
            )

    return len(chunks)


def create_vector_database(chroma_client, chunks, fingerprint,
                           name=None, on_progress=None, fingerprints=None):
    """
    Drop the collection and rebuild it from the supplied chunks.

    Used by the chunking sweep, where a collection holding chunks from two
    different strategies would make the comparison meaningless.
    """

    name = name or COLLECTION_NAME

    try:
        chroma_client.delete_collection(name)
    except Exception:
        pass

    embedder = get_embedder()

    collection = chroma_client.create_collection(
        name=name,
        configuration=collection_configuration(),
        embedding_function=None,
        metadata={
            "description": "Insurance claim documents",
            "fingerprint": fingerprint,
            "embedding_model": embedder.model_id,
            "index_signature": index_signature(),
        }
    )

    add_chunks(collection, chunks, fingerprints, on_progress)

    log(f"Stored {len(chunks)} chunks in Chroma.", on_progress)

    return collection


def build_collection(chroma_client, name=None, on_progress=None,
                     strategy=None, chunk_size=None, overlap=None,
                     pdf_files=None):
    """
    Index the corpus from scratch. Used by reindex and by eval sweeps.
    """

    pdf_files = pdf_files if pdf_files is not None else find_pdf_files()
    fingerprint = compute_corpus_fingerprint(pdf_files)

    fingerprints = {
        path.name: compute_file_fingerprint(path)
        for path in pdf_files
    }

    documents = load_documents(pdf_files, on_progress=on_progress)

    chunks = create_chunks(
        documents,
        strategy=strategy,
        chunk_size=chunk_size,
        overlap=overlap,
        on_progress=on_progress
    )

    return create_vector_database(
        chroma_client,
        chunks,
        fingerprint,
        name=name,
        on_progress=on_progress,
        fingerprints=fingerprints,
    )


# ============================================================
# 4. INCREMENTAL SYNC
# ============================================================

def indexed_fingerprints(collection):
    """
    The fingerprint each document in the index was built from.

    Read off the chunks rather than off collection metadata: a collection
    metadata blob has to be rewritten atomically and can silently exceed
    the store's value limits, whereas the chunks are the thing whose
    staleness is actually in question.
    """

    try:
        payload = collection.get(include=["metadatas"])
    except Exception:
        return {}

    fingerprints = defaultdict(set)

    for metadata in payload.get("metadatas") or []:

        source = (metadata or {}).get("source_file")

        if source:
            fingerprints[source].add(metadata.get("file_fingerprint", ""))

    return fingerprints


def plan_sync(pdf_files, indexed):
    """
    Work out which documents need ingesting and which need dropping.

    Returned as a plan rather than acted on directly so the caller - and
    the write-up - can state exactly what was re-indexed and what was
    left alone.
    """

    on_disk = {path.name: path for path in pdf_files}

    fresh = {}
    stale = []

    for name, path in sorted(on_disk.items()):

        fingerprint = compute_file_fingerprint(path)
        fresh[name] = fingerprint

        stored = indexed.get(name)

        # A document whose chunks disagree about their own fingerprint was
        # written by two different runs; treat it as stale.
        if not stored or stored != {fingerprint}:
            stale.append(path)

    removed = sorted(set(indexed) - set(on_disk))

    return {
        "fingerprints": fresh,
        "to_ingest": stale,
        "to_remove": removed,
        "unchanged": sorted(set(on_disk) - {path.name for path in stale}),
    }


def sync_collection(chroma_client, name=None, on_progress=None,
                    strategy=None, chunk_size=None, overlap=None):
    """
    Reconcile the index with the documents folder, touching only deltas.

    Documents that have not changed are never opened, never chunked and
    never re-embedded. Adding six endorsements to a folder that already
    contains an indexed policy wording costs six documents of work.
    """

    name = name or COLLECTION_NAME

    pdf_files = find_pdf_files()

    try:
        collection = open_collection(chroma_client, name)
    except Exception:
        collection = None

    # A collection written under a different index signature cannot be
    # reconciled row by row: its chunks predate the current metadata
    # schema, so a delete keyed on source_file would not match them and
    # they would survive as unattributable duplicates that still answer
    # queries. Signature mismatch is therefore a full rebuild, not a sync.
    if collection is not None:

        stored_signature = (collection.metadata or {}).get("index_signature")

        if stored_signature != index_signature():

            log(
                f"Index signature changed "
                f"({stored_signature} -> {index_signature()}). "
                "Rebuilding the collection from scratch.",
                on_progress
            )

            collection = None

    if collection is None:

        try:
            chroma_client.delete_collection(name)
        except Exception:
            pass

        collection = chroma_client.create_collection(
            name=name,
            configuration=collection_configuration(),
            embedding_function=None,
            metadata={
                "description": "Insurance claim documents",
                "embedding_model": get_embedder().model_id,
                "index_signature": index_signature(),
            }
        )

    plan = plan_sync(pdf_files, indexed_fingerprints(collection))

    if not plan["to_ingest"] and not plan["to_remove"]:
        log(
            f"Index is up to date: {collection.count()} chunks, "
            f"{len(plan['unchanged'])} documents, nothing to do.",
            on_progress
        )
        return collection, plan

    for name_to_remove in plan["to_remove"]:

        log(f"Removing withdrawn document: {name_to_remove}", on_progress)

        collection.delete(where={"source_file": name_to_remove})

    if plan["unchanged"]:
        log(
            f"Leaving {len(plan['unchanged'])} unchanged document(s) in "
            f"place: {', '.join(plan['unchanged'])}",
            on_progress
        )

    if plan["to_ingest"]:

        log(
            f"Ingesting {len(plan['to_ingest'])} document(s): "
            f"{', '.join(path.name for path in plan['to_ingest'])}",
            on_progress
        )

        # Drop the previous chunks of each stale document first, or an
        # edit that produces fewer chunks would leave the surplus behind
        # as orphans that still answer queries.
        for path in plan["to_ingest"]:
            collection.delete(where={"source_file": path.name})

        documents = load_documents(plan["to_ingest"], on_progress=on_progress)

        chunks = create_chunks(
            documents,
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=overlap,
            on_progress=on_progress
        )

        add_chunks(collection, chunks, plan["fingerprints"], on_progress)

    log(
        f"Index now holds {collection.count()} chunks "
        f"across {len(plan['fingerprints'])} documents.",
        on_progress
    )

    return collection, plan


def load_or_build_collection(chroma_client, force_reindex=False,
                             on_progress=None):
    """
    Bring the index into line with the documents folder and return it.

    force_reindex drops everything and starts over; otherwise only the
    documents that actually changed are touched.
    """

    if force_reindex:
        log("Forced reindex: rebuilding the whole collection.", on_progress)
        return build_collection(chroma_client, on_progress=on_progress)

    collection, _ = sync_collection(chroma_client, on_progress=on_progress)

    return collection
