import logging
from functools import lru_cache

import pandas as pd

from .config import cache_dir

log = logging.getLogger(__name__)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "products"
TOP_K = 20


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def product_text(p) -> str:
    return (
        f"{p['name']}. Category: {p['category']}. {p['description']}. "
        f"Tags: {p['tags'].replace('|', ', ')}. Goes well with: {p['pairs_with'].replace('|', ', ')}."
    )


class ProductIndex:
    def __init__(self, catalog: pd.DataFrame):
        self.collection = None
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(cache_dir() / "chroma"))
            try:
                client.delete_collection(COLLECTION)
            except Exception:
                pass
            collection = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
            rows = [row for _, row in catalog.iterrows()]
            texts = [product_text(row) for row in rows]
            collection.add(
                ids=[row["sku"] for row in rows],
                embeddings=_model().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist(),
                documents=texts,
                metadatas=[{"sku": row["sku"], "category": row["category"]} for row in rows],
            )
            self.collection = collection
        except Exception as exc:
            # ponytail: no embeddings (e.g. model download blocked) -> similarity is 0 and
            # ranking falls back to pairs_with + co-purchase. Pre-download the model to fix.
            log.warning("Vector index unavailable, continuing without embeddings: %s", exc)

    def related(self, trigger) -> dict[str, float]:
        """Top SKUs that go well with the trigger product, with cosine similarity (0-1)."""
        if self.collection is None:
            return {}
        query = f"products that go well with {trigger['name']} ({trigger['tags'].replace('|', ', ')})"
        result = self.collection.query(
            query_embeddings=_model().encode([query], normalize_embeddings=True, show_progress_bar=False).tolist(),
            n_results=min(TOP_K + 1, self.collection.count()),
        )
        pairs = zip(result["ids"][0], result["distances"][0])
        related = {sku: max(0.0, 1 - dist) for sku, dist in pairs if sku != trigger["sku"]}
        return dict(list(related.items())[:TOP_K])
