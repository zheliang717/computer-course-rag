"""Import registered open textbooks into their matching course knowledge bases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "materials" / "sources.json"


def require_ok(response: httpx.Response) -> dict | list:
    if response.is_error:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.status_code} {response.text[:500]}")
    return response.json()


def find_registered_document(documents: list[dict], source: dict) -> dict | None:
    """Match the immutable import ID before the user-facing title, which may be corrected."""
    stable_id = str(uuid5(NAMESPACE_URL, f"computer-course-rag/document/{source['id']}"))
    return next((item for item in documents if item["id"] == stable_id), None) or next(
        (item for item in documents if item["name"] == source["title"]), None
    )


def wait_for_job(client: httpx.Client, job_id: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_status = None
    while time.monotonic() < deadline:
        job = require_ok(client.get(f"/api/v1/document-jobs/{job_id}"))
        status = (job["status"], job["progress_percent"])
        if status != last_status:
            print(f"  文档处理：{status[0]} {status[1]}%", flush=True)
            last_status = status
        if job["status"] == "completed":
            return
        if job["status"] == "failed":
            raise RuntimeError(f"文档处理失败：{job.get('error_message')}")
        time.sleep(5)
    raise TimeoutError(f"文档任务 {job_id} 超时；任务仍可能在后台继续，请先检查状态再重试。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--source-id", action="append", help="只导入指定来源；可重复使用")
    parser.add_argument("--job-timeout", type=float, default=1800)
    args = parser.parse_args()

    username = os.environ.get("RAG_ADMIN_USERNAME", "admin")
    password = os.environ.get("RAG_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("请先设置 RAG_ADMIN_PASSWORD 环境变量。")

    sources = json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]
    sources = [
        source for source in sources
        if source.get("course_code") and (not args.source_id or source["id"] in args.source_id)
    ]
    if not sources:
        raise SystemExit("没有匹配到带 course_code 的资料。")

    for source in sources:
        path = ROOT / source["local_file"]
        if not path.is_file():
            raise SystemExit(f"资料文件不存在：{path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        if digest != source["sha256"].upper():
            raise SystemExit(f"资料哈希不一致：{path}")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=120) as client:
        login = require_ok(client.post("/api/v1/auth/login", json={"username": username, "password": password}))
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        courses = {course["code"]: course for course in require_ok(client.get("/api/v1/courses"))}

        for source in sources:
            course = courses.get(source["course_code"])
            if course is None:
                raise RuntimeError(f"课程不存在：{source['course_code']}")
            print(f"准备：{course['title']} / {source['title']}", flush=True)
            bases = require_ok(client.get("/api/v1/knowledge-bases"))
            base = next((item for item in bases if item["name"] == source["knowledge_base_name"]), None)
            if base is None:
                base = require_ok(client.post("/api/v1/knowledge-bases", json={
                    "name": source["knowledge_base_name"],
                    "course": course["title"],
                    "description": "公开许可教材；来源、版本和校验值见 materials/sources.json。",
                }))
                print(f"  已创建资料库：{base['name']}", flush=True)

            documents = require_ok(client.get(f"/api/v1/knowledge-bases/{base['id']}/documents"))
            document = find_registered_document(documents, source)
            if document is None or document["status"] != "ready":
                path = ROOT / source["local_file"]
                with path.open("rb") as handle:
                    job = require_ok(client.post(
                        f"/api/v1/knowledge-bases/{base['id']}/document-jobs",
                        data={"document_id": source["id"]},
                        files={"file": (source["title"], handle, "application/pdf")},
                        timeout=180,
                    ))
                wait_for_job(client, job["id"], args.job_timeout)
                documents = require_ok(client.get(f"/api/v1/knowledge-bases/{base['id']}/documents"))
                document = find_registered_document(documents, source)
                if document is None or document["status"] != "ready":
                    raise RuntimeError(f"任务完成但资料未就绪：{source['title']}")
            else:
                print("  已存在就绪文档，跳过重复导入。", flush=True)

            updated = require_ok(client.patch(f"/api/v1/documents/{document['id']}", json={
                "name": source["title"],
                "source_url": source["document_url"],
                "license_name": source["license"],
                "license_url": source["license_url"],
                "version_label": source.get("version", "1.0"),
                "publication_status": "published",
            }))
            linked = require_ok(client.get(f"/api/v1/courses/{course['id']}/knowledge-bases"))
            if not any(item["id"] == base["id"] for item in linked):
                require_ok(client.post(f"/api/v1/courses/{course['id']}/knowledge-bases", json={
                    "knowledge_base_id": base["id"],
                }))
            print(f"  已入库并关联：{updated['page_count']} 页，{updated['chunk_count']} 个文本块。", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
