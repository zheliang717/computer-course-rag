from collections.abc import Callable
from typing import Any


class BgeEmbedder:
    """Lazy SentenceTransformer adapter, including multilingual models."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        *,
        device: str | None = None,
        cache_folder: str | None = None,
        target_dimensions: int | None = None,
        model_loader: Callable[..., Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.cache_folder = cache_folder
        self.target_dimensions = target_dimensions
        self._model_loader = model_loader
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        loader = self._model_loader
        if loader is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "BGE模型需要可选依赖，请运行 pip install -e '.[embedding]'"
                ) from exc
            loader = SentenceTransformer
        kwargs = {"device": self.device} if self.device else {}
        if self.cache_folder:
            kwargs["cache_folder"] = self.cache_folder
        self._model = loader(self.model_name, **kwargs)
        return self._model

    @property
    def dimensions(self) -> int:
        model = self._load()
        dimension_method = getattr(model, "get_embedding_dimension", None)
        if dimension_method is None:
            dimension_method = model.get_sentence_embedding_dimension
        model_dimensions = int(dimension_method())
        if self.target_dimensions is not None and model_dimensions > self.target_dimensions:
            raise ValueError("Embedding model exceeds the database vector dimensions.")
        return self.target_dimensions or model_dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        result = vectors.tolist() if hasattr(vectors, "tolist") else vectors
        dimensions = self.dimensions
        return [
            list(vector) + [0.0] * (dimensions - len(vector))
            for vector in result
        ]
