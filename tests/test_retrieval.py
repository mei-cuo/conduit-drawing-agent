import pytest

from drawflow.chunking import chunk_markdown
from drawflow.embeddings import CachedEmbeddings, HashEmbeddings
from drawflow.retrieval import KnowledgeIndex


def test_heading_parent_child_boundaries(tmp_path):
    p = tmp_path / "rule.md"
    p.write_text(
        "# 桩号\n## 主线\n" + "读取引线对应桩号。" * 300 + "\n## 匝道\n匝道采用 AK 前缀。",
        encoding="utf-8",
    )
    chunks = chunk_markdown(p, "rule.md", child_size=120, overlap=20)
    assert all(len(c["text"]) <= 120 and len(c["parent_text"]) <= 1800 for c in chunks)
    assert any(c["heading"] == "桩号 / 匝道" for c in chunks)
    assert len({c["id"] for c in chunks}) == len(chunks)
    assert chunks == chunk_markdown(p, "rule.md", child_size=120, overlap=20)


def test_embeddings_cache_survives_new_instance(tmp_path):
    class CounterEmbedding(HashEmbeddings):
        calls = 0

        def embed_documents(self, texts):
            self.calls += 1
            return super().embed_documents(texts)

    delegate = CounterEmbedding()
    first = CachedEmbeddings(delegate, tmp_path / "cache.sqlite")
    expected = first.embed_query("主线桩号")
    second = CachedEmbeddings(delegate, tmp_path / "cache.sqlite")
    assert second.embed_query("主线桩号") == expected
    assert delegate.calls == 1


def test_qdrant_persistence_rank_and_rebuild(settings, tmp_path):
    index = KnowledgeIndex(settings)
    stats = index.ingest()
    assert stats["chunks"] >= 9
    assert index.search("沿主线两个邻井分歧支路")[0]["source"] == "topology.md"
    index.close()
    index = KnowledgeIndex(settings)
    assert index.search("桩号引线")[0]["source"] == "chainage.md"
    source = tmp_path / "new"
    source.mkdir()
    (source / "replacement.md").write_text("# 替换规则\n新的唯一知识来源", encoding="utf-8")
    index.ingest(source)
    assert {x["source"] for x in index.search("新规则")} == {"replacement.md"}
    index.embedding.fingerprint = "other-space"
    with pytest.raises(ValueError, match="Embedding"):
        index.search("query")
    index.close()


def test_k_bounds(settings):
    index = KnowledgeIndex(settings)
    try:
        index.ingest()
        with pytest.raises(ValueError):
            index.search("query", 0)
    finally:
        index.close()
