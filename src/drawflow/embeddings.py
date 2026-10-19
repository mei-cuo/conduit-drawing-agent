"""LangChain Embeddings implementations and reproducible index fingerprints."""

from __future__ import annotations

import hashlib
import math
import os
import re

from langchain_core.embeddings import Embeddings


def tokens(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    return [
        normalized[i : i + size] for size in (1, 2, 3) for i in range(len(normalized) - size + 1)
    ]


class HashEmbeddings(Embeddings):
    dimension = 384
    fingerprint = "char-ngram-sha256-v1-384"

    def embed_query(self, text):
        values = [0.0] * self.dimension
        for token in tokens(text):
            key = hashlib.sha256(token.encode()).digest()
            values[int.from_bytes(key[:4], "big") % self.dimension] += 1 if key[4] % 2 else -1
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


def create_embeddings(backend: str):
    if backend == "hash":
        return HashEmbeddings()
    if backend != "openai":
        raise ValueError("EMBEDDING_BACKEND 必须为 hash 或 openai")
    from langchain_openai import OpenAIEmbeddings

    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    endpoint = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("请配置 EMBEDDING_API_KEY")
    embedding = OpenAIEmbeddings(model=model, api_key=key, base_url=endpoint, max_retries=2)
    # Include endpoint identity: equal dimensions do not imply compatible vector spaces.
    fingerprint = hashlib.sha256(f"openai:{endpoint}:{model}".encode()).hexdigest()
    return EmbeddingAdapter(embedding, fingerprint)


class EmbeddingAdapter(Embeddings):
    def __init__(self, model, fingerprint):
        self.model, self.fingerprint = model, fingerprint

    def embed_query(self, text):
        return self.model.embed_query(text)

    def embed_documents(self, texts):
        return self.model.embed_documents(texts)


class CachedEmbeddings(Embeddings):
    """Persist vectors by embedding fingerprint and exact text hash."""

    def __init__(self, delegate, path):
        import sqlite3

        self.delegate = delegate
        self.fingerprint = delegate.fingerprint
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector TEXT NOT NULL)"
            )

    def embed_documents(self, texts):
        import json
        import sqlite3

        keys = [
            hashlib.sha256((self.fingerprint + ":" + text).encode()).hexdigest() for text in texts
        ]
        with sqlite3.connect(self.path) as db:
            cached = {
                key: json.loads(row[0])
                for key in keys
                if (
                    row := db.execute(
                        "SELECT vector FROM embeddings WHERE key=?", (key,)
                    ).fetchone()
                )
            }
            missing = list(dict.fromkeys(key for key in keys if key not in cached))
            if missing:
                lookup = dict(zip(keys, texts))
                values = self.delegate.embed_documents([lookup[key] for key in missing])
                for key, vector in zip(missing, values):
                    db.execute(
                        "INSERT OR REPLACE INTO embeddings VALUES (?,?)",
                        (key, json.dumps(vector)),
                    )
                    cached[key] = vector
        return [cached[key] for key in keys]

    def embed_query(self, text):
        return self.embed_documents([text])[0]
