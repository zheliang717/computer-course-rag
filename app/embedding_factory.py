from app.config import Settings
from app.embedding import Embedder, HashingEmbedder
from app.embedding_bge import BgeEmbedder


def create_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider.strip().lower()
    if provider == "hashing":
        return HashingEmbedder(dimensions=settings.embedding_dimensions)
    if provider == "bge":
        device = "cpu"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
        except ImportError:
            pass
        return BgeEmbedder(
            model_name=settings.embedding_model,
            device=device,
            cache_folder=settings.embedding_cache_dir,
            target_dimensions=settings.embedding_dimensions,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
