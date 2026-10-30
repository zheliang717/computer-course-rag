import pytest

from app.config import Settings
from app.embedding import HashingEmbedder
from app.embedding_bge import BgeEmbedder
from app.embedding_factory import create_embedder


def test_factory_defaults_to_offline_embedder() -> None:
    embedder = create_embedder(Settings())
    assert isinstance(embedder, HashingEmbedder)
    assert embedder.dimensions == 512


def test_factory_selects_bge_lazily() -> None:
    embedder = create_embedder(Settings(embedding_provider="bge"))
    assert isinstance(embedder, BgeEmbedder)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported embedding provider"):
        create_embedder(Settings(embedding_provider="unknown"))
