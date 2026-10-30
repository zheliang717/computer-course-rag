"""Atomically rebuild all stored chunk vectors with a multilingual model."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.embedding_bge import BgeEmbedder
from app.models import Chunk


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv(
        "DATABASE_URL", "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cache-dir", default=str(ROOT / "models-cache"))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dimensions", type=int, default=512)
    args = parser.parse_args()
    if args.batch_size < 1 or args.dimensions < 1:
        raise SystemExit("batch-size 和 dimensions 必须为正数。")

    embedder = BgeEmbedder(
        model_name=args.model,
        device="cpu",
        cache_folder=args.cache_dir,
        target_dimensions=args.dimensions,
    )
    if embedder.dimensions != args.dimensions:
        raise RuntimeError("模型与数据库向量维度不匹配。")
    engine = create_engine(args.database_url)
    with Session(engine) as session:
        rows = session.execute(select(Chunk.id, Chunk.content).order_by(Chunk.id)).all()
        print(f"准备重建 {len(rows)} 个文本块；所有更新将在最后一次性提交。", flush=True)
        for offset in range(0, len(rows), args.batch_size):
            batch = rows[offset:offset + args.batch_size]
            vectors = embedder.embed([row.content for row in batch])
            for row, vector in zip(batch, vectors, strict=True):
                session.execute(update(Chunk).where(Chunk.id == row.id).values(embedding=vector))
            print(f"已计算 {offset + len(batch)}/{len(rows)}", flush=True)
        session.commit()
    print(f"已提交全部 {len(rows)} 个多语种向量。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
