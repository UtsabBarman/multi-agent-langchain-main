from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings


def create_chroma_retriever(
    persist_directory: str | Path,
    collection_name: str = "default",
    embedding_function: Embeddings | None = None,
    k: int = 5,
) -> Any:
    """Create a LangChain retriever over Chroma. Uses OpenAI embeddings if none provided."""
    path = Path(persist_directory)
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    if embedding_function is None:
        embedding_function = OpenAIEmbeddings()
    vectorstore = Chroma(
        client=client,
        collection_name=collection_name,
        embedding_function=embedding_function,
    )
    return vectorstore.as_retriever(search_kwargs={"k": k})
