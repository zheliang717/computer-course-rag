"""Import the legacy data-structures reference PDFs into the default knowledge base."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = PROJECT_ROOT / "materials" / "sources.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    registry = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    # Course-specific textbooks have their own importer and knowledge bases.
    sources = [item for item in registry.get("sources", []) if not item.get("course_code")]
    if not sources:
        raise SystemExit("sources.json 中没有登记资料。")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout) as client:
        health = client.get("/health")
        health.raise_for_status()
        print(f"导入前已有 {health.json().get('indexed_chunks', 0)} 个文本块。")

        for source in sources:
            path = PROJECT_ROOT / source["local_file"]
            if not path.is_file():
                raise SystemExit(f"找不到登记的资料文件：{path}")
            with path.open("rb") as handle:
                response = client.post(
                    "/api/v1/knowledge/pdf",
                    data={"document_id": source["id"]},
                    # Use the registered book title as the knowledge-base label;
                    # the local filename remains only the storage artifact.
                    files={"file": (source["title"], handle, "application/pdf")},
                )
            response.raise_for_status()
            result = response.json()
            print(
                f"{source['title']}：导入 {result['imported_chunks']} 个文本块，"
                f"当前共 {result['total_chunks']} 个。"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
