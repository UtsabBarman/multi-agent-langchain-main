"""Shared Chroma indexing: chunk text, embed with OpenAI, add to collection."""
from __future__ import annotations

import chromadb
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_SEPARATORS = ["\n\n", "\n", " "]


def get_default_splitter() -> RecursiveCharacterTextSplitter:
    """Return the standard text splitter used for indexing."""
    return RecursiveCharacterTextSplitter(
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
        separators=DEFAULT_SEPARATORS,
    )


def index_text_to_chroma(
    chroma_path: str,
    collection_name: str,
    text: str,
    source: str = "upload",
) -> int:
    """
    Chunk text, embed with OpenAI, add to Chroma. Returns number of chunks added.
    Used by the index_doc tool and the Doc Store upload API.
    """
    if not (text or "").strip():
        return 0
    splitter = get_default_splitter()
    chunks = splitter.split_text(text.strip())
    if not chunks:
        return 0
    client = chromadb.PersistentClient(path=chroma_path)
    embeddings = OpenAIEmbeddings()
    vectorstore = Chroma(
        client=client,
        collection_name=collection_name,
        embedding_function=embeddings,
    )
    vectorstore.add_texts(chunks, metadatas=[{"source": source}] * len(chunks))
    return len(chunks)
