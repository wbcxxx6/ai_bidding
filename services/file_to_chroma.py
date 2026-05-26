import hashlib

from services.ingestion_service import extract_text, search_documents, split_text
from storage.vector_store import ChromaVectorStore, embed_texts


def read_file_content(file_path):
    return extract_text(file_path)


def init_chroma_client(persist_directory="./chroma_db"):
    return ChromaVectorStore(persist_directory=persist_directory).collection


def get_embeddings(client, texts, batch_size=10):
    return embed_texts(texts, batch_size=batch_size)


def file_to_chroma(file_path, collection=None):
    text = extract_text(file_path)
    chunks = split_text(text)
    store = ChromaVectorStore()
    payload = []
    for index, chunk in enumerate(chunks):
        digest = hashlib.md5(f"{file_path}:{index}:{chunk}".encode("utf-8")).hexdigest()
        chunk_id = f"legacy_{digest}"
        payload.append(
            {
                "id": chunk_id,
                "text": chunk,
                "metadata": {"file_name": file_path, "chunk_index": index, "doc_type": "legacy"},
            }
        )
    store.upsert_chunks(payload)
    return {"status": "success", "file_name": file_path, "total_chunks": len(payload), "chunks": payload}


def query_chroma(query_content, limit=3, collection=None):
    results = search_documents(query_content, limit=limit)
    return {
        "status": "success",
        "query": query_content,
        "results_count": len(results),
        "results": [
            {
                "document_id": item["chunk_uid"],
                "file_name": item["source_title"],
                "content": item["content"],
                "similarity": item["similarity"],
                "distance": item["distance"],
            }
            for item in results
        ],
    }
