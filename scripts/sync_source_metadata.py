"""Reconcile registered source metadata without reimporting or replacing document content."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.catalog import KnowledgeCatalog
from app.database import get_engine, get_session_factory


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "materials" / "sources.json"


def registered_changes(source: dict) -> dict:
    return {
        "name": source["title"],
        "source_url": source["document_url"],
        "license_name": source["license"],
        "license_url": source["license_url"],
        "version_label": source.get("version", "原文件未标注版次"),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="提交更改；默认只预览")
    args = parser.parse_args()

    url = get_engine().url
    print(f"目标数据库：{url.host}:{url.port}/{url.database}")
    sources = json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]
    catalog = KnowledgeCatalog(get_session_factory())
    changed = 0
    missing = 0
    for source in sources:
        found = catalog.get_document(source["id"])
        if found is None:
            print(f"未入库，跳过：{source['id']}")
            missing += 1
            continue
        document = found[0]
        desired = registered_changes(source)
        differences = {
            key: value for key, value in desired.items()
            if getattr(document, "filename" if key == "name" else key) != value
        }
        if not differences:
            continue
        print(f"{source['id']}：待更新 {', '.join(differences)}")
        changed += 1
        if args.apply:
            catalog.update_document(source["id"], actor_name="system:source-audit-sync", **differences)
    print(f"结果：待更新/已更新 {changed} 份，未入库 {missing} 份；模式={'提交' if args.apply else '预览'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
