"""Persistent Qdrant vectors plus lexical ranking, fused with reciprocal rank."""

from __future__ import annotations

import os
import uuid
from collections import Counter

from langsmith import traceable
from qdrant_client import QdrantClient, models

from .chunking import chunk_markdown
from .config import ASSETS
from .embeddings import CachedEmbeddings, create_embeddings, tokens
from .storage import write_json


class KnowledgeIndex:
    def __init__(self, settings):
        self.settings = settings
        self.embedding = CachedEmbeddings(
            create_embeddings(settings.embedding_backend),
            settings.runtime / "embeddings.sqlite",
        )
        self.client = (
            QdrantClient(url=settings.qdrant_url, api_key=os.getenv("QDRANT_API_KEY") or None)
            if settings.qdrant_url
            else QdrantClient(path=str(settings.runtime / "qdrant"))
        )
        self.collection = settings.collection
        self.manifest = settings.runtime / f"{self.collection}-manifest.json"

    def close(self):
        self.client.close()

    @traceable(name="knowledge.ingest")
    def ingest(self, directory=None):
        directory = directory or ASSETS / "knowledge"
        chunks = []
        for path in sorted(directory.rglob("*.md")):
            chunks.extend(chunk_markdown(path, path.relative_to(directory).as_posix()))
        if not chunks:
            raise ValueError("知识目录中没有可索引的 Markdown")
        vectors = self.embedding.embed_documents([f"{c['heading']}\n{c['text']}" for c in chunks])
        stale_ids = []
        current_ids = {str(uuid.uuid5(uuid.NAMESPACE_URL, c["id"])) for c in chunks}
        if self.client.collection_exists(self.collection):
            size = self.client.get_collection(self.collection).config.params.vectors.size
            if size != len(vectors[0]):
                raise ValueError("向量维度改变，请设置新的 QDRANT_COLLECTION 后重建")
            # Delete stale points after upsert; avoid removing an open local SQLite collection.
            points, cursor = self.client.scroll(self.collection, limit=256, with_vectors=False)
            stale_ids.extend(str(p.id) for p in points if str(p.id) not in current_ids)
            while cursor is not None:
                points, cursor = self.client.scroll(
                    self.collection, limit=256, offset=cursor, with_vectors=False
                )
                stale_ids.extend(str(p.id) for p in points if str(p.id) not in current_ids)
        else:
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(
                    size=len(vectors[0]), distance=models.Distance.COSINE
                ),
            )
        for offset in range(0, len(chunks), 128):
            self.client.upsert(
                self.collection,
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, c["id"])),
                        vector=v,
                        payload={
                            **c,
                            "embedding_fingerprint": self.embedding.fingerprint,
                        },
                    )
                    for c, v in zip(chunks[offset : offset + 128], vectors[offset : offset + 128])
                ],
                wait=True,
            )
        if stale_ids:
            self.client.delete(
                self.collection,
                points_selector=models.PointIdsList(points=stale_ids),
                wait=True,
            )
        write_json(
            self.manifest,
            {
                "fingerprint": self.embedding.fingerprint,
                "chunks": len(chunks),
                "dimension": len(vectors[0]),
            },
        )
        return {
            "chunks": len(chunks),
            "dimension": len(vectors[0]),
            "fingerprint": self.embedding.fingerprint,
        }

    def _chunks(self):
        points, cursor = self.client.scroll(self.collection, limit=256, with_vectors=False)
        while cursor is not None:
            more, cursor = self.client.scroll(
                self.collection, limit=256, offset=cursor, with_vectors=False
            )
            points.extend(more)
        return {p.payload["id"]: p.payload for p in points}

    @traceable(name="knowledge.hybrid_search")
    def search(self, query, k=4):
        if not self.client.collection_exists(self.collection):
            raise ValueError("知识库尚未建立；执行 drawflow ingest")
        if not 1 <= k <= 20:
            raise ValueError("k 必须在 1–20 之间")
        chunks = self._chunks()
        if any(
            c.get("embedding_fingerprint") != self.embedding.fingerprint for c in chunks.values()
        ):
            raise ValueError("Embedding 配置与索引不一致；请重新 ingest")
        vector = self.embedding.embed_query(query)
        dense = self.client.query_points(self.collection, query=vector, limit=max(k * 3, 12)).points
        query_counts = Counter(tokens(query))

        def score(c):
            words = Counter(tokens(c["heading"] + c["text"]))
            return sum(min(count, words[token]) for token, count in query_counts.items()) / (
                len(words) ** 0.5 or 1
            )

        lexical = sorted(chunks.values(), key=score, reverse=True)
        ranks = {}
        for ranking in (
            [p.payload["id"] for p in dense],
            [c["id"] for c in lexical if score(c) > 0][: max(k * 3, 12)],
        ):
            for rank, key in enumerate(ranking, 1):
                ranks[key] = ranks.get(key, 0) + 1 / (60 + rank)
        result, parents = [], set()
        for key in sorted(ranks, key=ranks.get, reverse=True):
            c = chunks[key]
            if c["parent_id"] in parents:
                continue
            parents.add(c["parent_id"])
            result.append({**c, "score": ranks[key], "citation": f"{c['source']}#{c['heading']}"})
            if len(result) >= k:
                break
        return result


def context_text(documents):
    return "\n\n".join(f"[{d['citation']}]\n{d['parent_text']}" for d in documents)
