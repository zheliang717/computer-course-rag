"""Import an audited, text-only edition of one pinned LearningOS lecture.

Images, external linked pages, hidden slide notes and image-only slides are
intentionally excluded. The original MIT notice is kept as a catalog page.
No source is approved for external-model sharing by this script.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
from uuid import NAMESPACE_URL, uuid5

import httpx


REPOSITORY = "LearningOS/os-lectures"
COMMIT = "61be90c7839b64849410a806e28534e79979a5fb"
SOURCE_PATH = "lec5/p1-memintro.md"
SOURCE_SHA256 = "4806EC697268373E76B344DF68CAD452C2F660FF61E0F04DB6CD0CE63A5242B3"
LICENSE_SHA256 = "D6919DC32F681A8F11682D687FCCB891F38E31FE813B4938A2B3B89C1692A658"
DOCUMENT_KEY = f"learningos-os-lectures:{COMMIT}:{SOURCE_PATH}:text-only"
TITLE = "清华大学操作系统课程：物理内存管理·地址空间（文字摘编）"
SOURCE_URL = f"https://github.com/{REPOSITORY}/blob/{COMMIT}/{SOURCE_PATH}"
LICENSE_URL = f"https://github.com/{REPOSITORY}/blob/{COMMIT}/LICENSE"


def _github_file(client: httpx.Client, path: str, expected_sha256: str) -> str:
    response = client.get(
        f"https://api.github.com/repos/{REPOSITORY}/contents/{path}",
        params={"ref": COMMIT}, headers={"User-Agent": "computer-course-rag-source-audit"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("encoding") != "base64":
        raise ValueError(f"GitHub 来源编码不符合预期：{path}")
    data = base64.b64decode(payload["content"], validate=False)
    actual = hashlib.sha256(data).hexdigest().upper()
    if actual != expected_sha256:
        raise ValueError(f"固定来源哈希不符：{path}，已停止导入")
    return data.decode("utf-8")


def _slide_lines(source_lines: list[str], *ranges: tuple[int, int]) -> str:
    selected: list[str] = []
    for first, last in ranges:
        selected.extend(source_lines[first - 1:last])
    text = "\n".join(selected).strip()
    if "![" in text or "<!--" in text or "http://" in text or "https://" in text:
        raise ValueError("文字摘编意外包含图片、隐藏注释或外部链接")
    readable: list[str] = []
    for raw_line in selected:
        line = raw_line.strip().lstrip("#").strip()
        if not line or line == "---":
            continue
        line = line.lstrip("- ").replace("**", "").strip()
        if line and not line.endswith(("。", "！", "？", "；", "：", ":")):
            line += "。"
        readable.append(line)
    return "\n".join(readable)


def build_pages(source: str, license_text: str) -> list[dict]:
    lines = source.splitlines()
    if "2026年秋季" not in source or "## 第一节 地址空间" not in source:
        raise ValueError("固定来源的学期或标题与审核记录不符")
    attribution = (
        f"原资料：《第五讲 物理内存管理》第一节《地址空间》；向勇、陈渝、李国良、任炬；2026 年秋季。\n"
        f"来源：{SOURCE_URL}\n"
        f"本版为文字摘编：省略原课件图片、外部链接目标、隐藏注释及纯图片页；本系统页码按主题重排，不对应原幻灯片页码。"
    )
    return [
        {"page_number": 1, "chapter": "地址类型与转换", "text": attribution + "\n\n" + _slide_lines(lines, (46, 65), (131, 140))},
        {"page_number": 2, "chapter": "内存管理与地址生成", "text": _slide_lines(lines, (111, 120), (149, 159), (163, 164), (166, 172))},
        {"page_number": 3, "chapter": "虚拟存储与保护", "text": _slide_lines(lines, (189, 195), (201, 207), (212, 217), (222, 228))},
        {"page_number": 4, "chapter": "来源与 MIT 许可", "text": f"资料来源与授权记录\n{attribution}\n\n"
         f"仓库许可证原文（{LICENSE_URL}）：\n{license_text.strip()}"},
    ]


def _json(response: httpx.Response):
    if response.is_error:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.status_code} {response.text[:500]}")
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--force", action="store_true", help="重新导入固定资料并撤销既有外发批准")
    args = parser.parse_args()
    username = os.environ.get("RAG_ADMIN_USERNAME", "admin")
    password = os.environ.get("RAG_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("请先设置 RAG_ADMIN_PASSWORD 环境变量。")
    with httpx.Client(timeout=90) as client:
        source = _github_file(client, SOURCE_PATH, SOURCE_SHA256)
        license_text = _github_file(client, "LICENSE", LICENSE_SHA256)
        pages = build_pages(source, license_text)
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180) as client:
        login = _json(client.post("/api/v1/auth/login", json={"username": username, "password": password}))
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        bases = _json(client.get("/api/v1/knowledge-bases"))
        base = next((item for item in bases if item["name"] == "操作系统开放教材"), None)
        if base is None:
            raise RuntimeError("找不到操作系统开放教材资料库，未进行导入")
        documents = _json(client.get(f"/api/v1/knowledge-bases/{base['id']}/documents"))
        stable_id = str(uuid5(NAMESPACE_URL, f"computer-course-rag/document/{DOCUMENT_KEY}"))
        existing = next((item for item in documents if item["id"] == stable_id), None)
        if existing and not args.force:
            if existing["status"] != "ready":
                raise RuntimeError("固定资料已有非就绪记录，请检查后使用 --force 重试")
            print(f"已存在，跳过：{existing['name']} · {existing['chunk_count']} 个片段")
            return 0
        response = _json(client.post(f"/api/v1/knowledge-bases/{base['id']}/text-documents", json={
            "document_id": DOCUMENT_KEY,
            "title": TITLE,
            "source_url": SOURCE_URL,
            "license_name": "MIT（文字摘编，不含原课件图片和外链目标）",
            "license_url": LICENSE_URL,
            "version_label": f"2026 秋季 · {COMMIT[:12]}",
            "publication_status": "published",
            "pages": pages,
        }))
        document = response["document"]
        if document["external_model_allowed"] or document["status"] != "ready":
            raise RuntimeError("导入结果未达到就绪且禁止外发的预期，请检查数据库")
        print(f"已导入：{document['name']} · {document['page_count']} 个主题页 · {document['chunk_count']} 个片段；外发未核准")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
