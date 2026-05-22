from chromadb import PersistentClient
from chromadb.utils import embedding_functions

from app.core.settings import settings


class VectorStore:
    def __init__(self) -> None:
        self.client = PersistentClient(path=settings.chroma_path)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
        self.collection = self.client.get_or_create_collection(
            name="commcoach_context",
            embedding_function=self.embedding_fn,
        )

    def index_session_docs(self, session_id: str, resume_text: str, jd_text: str) -> None:
        docs = [resume_text, jd_text]
        ids = [f"{session_id}_resume", f"{session_id}_jd"]
        metas = [{"session_id": session_id, "source": "resume"}, {"session_id": session_id, "source": "jd"}]
        self.collection.upsert(documents=docs, ids=ids, metadatas=metas)

    def retrieve_context(self, session_id: str, prompt: str, top_k: int = 2) -> list[str]:
        result = self.collection.query(
            query_texts=[prompt],
            n_results=top_k,
            where={"session_id": session_id},
        )
        return result.get("documents", [[]])[0]


vector_store = VectorStore()
