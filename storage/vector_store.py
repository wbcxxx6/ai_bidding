import os
from abc import ABC, abstractmethod

import chromadb
from openai import OpenAI


EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
VECTOR_COLLECTION = os.getenv("VECTOR_COLLECTION", "document_embeddings")


def embedding_client():
    return OpenAI(
        api_key=os.getenv("EMBEDDING_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )


def embed_texts(texts, batch_size=10):
    client = embedding_client()
    vectors = []
    for i in range(0, len(texts), batch_size):
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts[i : i + batch_size])
        vectors.extend(item.embedding for item in response.data)
    return vectors


class VectorStore(ABC):
    @abstractmethod
    def upsert_chunks(self, chunks):
        pass

    @abstractmethod
    def query(self, query_text, filters=None, limit=5):
        pass

    @abstractmethod
    def delete(self, ids):
        pass


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_directory="./chroma_db", collection_name=VECTOR_COLLECTION):
        self.collection_name = collection_name
        self.collection = chromadb.PersistentClient(path=persist_directory).get_or_create_collection(name=collection_name)

    def upsert_chunks(self, chunks):
        if not chunks:
            return
        embeddings = embed_texts([item["text"] for item in chunks])
        self.collection.upsert(
            ids=[item["id"] for item in chunks],
            documents=[item["text"] for item in chunks],
            embeddings=embeddings,
            metadatas=[item.get("metadata", {}) for item in chunks],
        )

    def query(self, query_text, filters=None, limit=5):
        where = {key: value for key, value in (filters or {}).items() if value is not None}
        result = self.collection.query(
            query_embeddings=embed_texts([query_text]),
            n_results=limit,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        items = []
        for index, item_id in enumerate(result.get("ids", [[]])[0]):
            distance = result["distances"][0][index]
            items.append(
                {
                    "id": item_id,
                    "content": result["documents"][0][index],
                    "metadata": result["metadatas"][0][index],
                    "distance": distance,
                    "similarity": 1 - distance,
                    "vector_collection": self.collection_name,
                }
            )
        return items

    def delete(self, ids):
        if ids:
            self.collection.delete(ids=ids)


class MilvusVectorStore(VectorStore):
    def __init__(self, collection_name=VECTOR_COLLECTION):
        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
        except ImportError as exc:
            raise RuntimeError("pymilvus is not installed. Install pymilvus or set VECTOR_STORE=chroma.") from exc

        self.collection_name = collection_name
        self.metric_type = os.getenv("MILVUS_METRIC_TYPE", "COSINE")
        connections.connect(
            alias="default",
            host=os.getenv("MILVUS_HOST", "127.0.0.1"),
            port=os.getenv("MILVUS_PORT", "19530"),
            timeout=5,
        )
        if not utility.has_collection(collection_name):
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=128, is_primary=True, auto_id=False),
                FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="project_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="knowledge_base_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=int(os.getenv("EMBEDDING_DIM", "1024"))),
            ]
            collection = Collection(collection_name, CollectionSchema(fields, description="AI bidding document embeddings"))
            collection.create_index(
                field_name="embedding",
                index_params={
                    "metric_type": self.metric_type,
                    "index_type": os.getenv("MILVUS_INDEX_TYPE", "AUTOINDEX"),
                    "params": {},
                },
            )
        self.collection = Collection(collection_name)
        self.collection.load()

    def upsert_chunks(self, chunks):
        if not chunks:
            return
        embeddings = embed_texts([item["text"] for item in chunks])
        rows = [
            [item["id"] for item in chunks],
            [str(item.get("metadata", {}).get("tenant_id", "")) for item in chunks],
            [str(item.get("metadata", {}).get("project_id", "")) for item in chunks],
            [str(item.get("metadata", {}).get("knowledge_base_id", "")) for item in chunks],
            [str(item.get("metadata", {}).get("file_id", "")) for item in chunks],
            [str(item.get("metadata", {}).get("doc_type", "")) for item in chunks],
            embeddings,
        ]
        self.collection.upsert(rows)
        self.collection.flush()

    def query(self, query_text, filters=None, limit=5):
        expr_parts = []
        for key, value in (filters or {}).items():
            if value is not None:
                expr_parts.append(f'{key} == "{value}"')
        result = self.collection.search(
            data=embed_texts([query_text]),
            anns_field="embedding",
            param={"metric_type": self.metric_type, "params": {"nprobe": 10}},
            limit=limit,
            expr=" and ".join(expr_parts) if expr_parts else None,
            output_fields=["tenant_id", "project_id", "knowledge_base_id", "file_id", "doc_type"],
        )
        items = []
        for hit in result[0]:
            items.append(
                {
                    "id": hit.id,
                    "content": "",
                    "metadata": dict(hit.entity),
                    "distance": hit.distance,
                    "similarity": hit.score,
                    "vector_collection": self.collection_name,
                }
            )
        return items

    def delete(self, ids):
        if ids:
            quoted = ", ".join(f'"{item}"' for item in ids)
            self.collection.delete(f"id in [{quoted}]")


def get_vector_store():
    backend = os.getenv("VECTOR_STORE", "chroma").lower()
    if backend == "milvus":
        try:
            return MilvusVectorStore()
        except Exception:
            return ChromaVectorStore()
    return ChromaVectorStore()
