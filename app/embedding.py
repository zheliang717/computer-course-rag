import math
import re
from hashlib import blake2b
from typing import Protocol


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Deterministic offline baseline; replace with BGE in production."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    @staticmethod
    def _tokens(text: str) -> list[str]:
        lowered = text.lower()
        words = re.findall(r"[a-z0-9_]+", lowered)
        chinese = re.findall(r"[\u4e00-\u9fff]", lowered)
        chinese_bigrams = ["".join(chinese[i : i + 2]) for i in range(len(chinese) - 1)]
        return words + chinese + chinese_bigrams

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little")
            index = value % self.dimensions
            vector[index] += 1.0 if value & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]
