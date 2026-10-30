from types import SimpleNamespace

from app.embedding_bge import BgeEmbedder


class FakeModel:
    def get_sentence_embedding_dimension(self) -> int:
        return 512

    def encode(self, texts, **kwargs):
        assert kwargs["normalize_embeddings"] is True
        return [[1.0] * 512 for _ in texts]


def test_bge_adapter_is_lazy_and_normalizes_embeddings() -> None:
    calls = []

    def loader(name, **kwargs):
        calls.append((name, kwargs))
        return FakeModel()

    embedder = BgeEmbedder(model_loader=loader)
    assert calls == []
    assert embedder.dimensions == 512
    vectors = embedder.embed(["树是什么？"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 512
    assert len(calls) == 1


def test_bge_adapter_pads_multilingual_vectors_to_database_dimensions() -> None:
    class SmallerModel:
        def get_sentence_embedding_dimension(self) -> int:
            return 384

        def encode(self, texts, **kwargs):
            return [[0.5] * 384 for _ in texts]

    embedder = BgeEmbedder(target_dimensions=512, model_loader=lambda name, **kwargs: SmallerModel())
    assert embedder.dimensions == 512
    vector = embedder.embed(["什么是虚拟内存？"])[0]
    assert len(vector) == 512
    assert vector[383] == 0.5
    assert vector[384:] == [0.0] * 128
