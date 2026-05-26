from dotenv import load_dotenv

from storage.vector_store import get_vector_store


if __name__ == "__main__":
    load_dotenv()
    store = get_vector_store()
    print(f"vector store ok: {store.__class__.__name__}")
