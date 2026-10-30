"""Import immutable, attributed Chinese readings through the normal catalog API.

Dry-run is the default. --apply adds only new document IDs; existing material is
never resegmented/replaced. Every remote byte is checked against the manifest.
External sharing requires a separate explicit --approve-external confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.chunking import chunk_document
from app.domain import SourceDocument

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "materials/flagship-readings.json"
CHUNK_SIZE = 180
CHUNK_OVERLAP = 40


def stable_id(pack: dict) -> str:
    return str(uuid5(NAMESPACE_URL, f"computer-course-rag/document/{pack['id']}"))


def source_url(pack: dict, path: str = "") -> str:
    return f"https://github.com/{pack['repository']}/blob/{pack['commit']}/{path}" if path else (
        f"https://github.com/{pack['repository']}/tree/{pack['commit']}")


def checked_text(data: bytes, expected_hash: str) -> str:
    if hashlib.sha256(data).hexdigest().lower() != expected_hash.lower():
        raise ValueError("来源哈希不符，未进行导入")
    return data.decode("utf-8", errors="strict")


def selected_text(source: str, ranges: list[list[int]]) -> str:
    lines = source.splitlines()
    selected = []
    for first, last in ranges:
        if not 1 <= first <= last <= len(lines):
            raise ValueError("选读行号超出固定来源")
        selected.extend(lines[first - 1:last])
    text = "\n".join(selected)
    # Fail closed: additions to the manifest must not accidentally include
    # images, executable HTML, embedded code, slide notes or transclusions.
    if re.search(r"!\[|<!--|```|<\s*(?:script|style|iframe)|^\s*(?:===|\?\?\?|\[file\])", text, re.I | re.M):
        raise ValueError("选读中出现未审核的图片、代码嵌入或隐藏内容")

    def macro(match: re.Match) -> str:
        values = re.findall(r'''["']([^"']+)["']''', match.group(0))
        if not values:
            raise ValueError("未知 MDN 宏")
        return values[-1]

    text = re.sub(r"\{\{(?:glossary)\([^{}]*\)\}\}", macro, text, flags=re.I)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"</?(?:u|id)>|<p\b[^>]*>|</p>", "", text, flags=re.I)
    text = re.sub(r"^\s*!!! question\s*$", "", text, flags=re.M)
    if "{{" in text or re.search(r"<[/a-zA-Z]", text):
        raise ValueError("选读中仍有未处理的模板或 HTML")
    # The source reader is plain text, unlike AI answers. Do not expose Markdown
    # control characters or table delimiters as if they were textbook prose.
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.M).replace("**", "").replace("`", "")
    readable = []
    for line in text.splitlines():
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]+", cell) for cell in cells):
                continue
            line = " · ".join(cells)
        readable.append(line)
    return html.unescape("\n".join(readable)).strip()


def fetch_pages(client: httpx.Client, pack: dict) -> tuple[list[dict], str]:
    def fetch(path: str, digest: str) -> str:
        response = client.get(f"https://raw.githubusercontent.com/{pack['repository']}/{pack['commit']}/{path}")
        response.raise_for_status()
        return checked_text(response.content, digest)

    license_text = fetch(pack["license_file"], pack["license_sha256"])
    sources = {key: fetch(value["path"], value["sha256"]) for key, value in pack["files"].items()}
    pages = []
    attribution = [f"《{pack['title']}》；{pack['author']}。", f"本版采用 {pack['license_name']}；{pack['license_url']}。",
        "本版按主题重排页码，页号不是原书/幻灯片页码；省略图片、代码嵌入、隐藏注释、外链目标与其他未选段落。"]
    for number, page in enumerate(pack["pages"], 1):
        text = selected_text(sources[page["file"]], page["ranges"])
        if not all(word in text for word in page["keywords"]):
            raise ValueError(f"选读主题校验失败：{page['chapter']}")
        pages.append({"page_number": number, "chapter": page["chapter"], "text": f"{page['chapter']}\n\n{text}", "index_for_retrieval": True})
        attribution.append(f"主题页 {number}《{page['chapter']}》：{source_url(pack, pack['files'][page['file']]['path'])}；原文行 {page['ranges']}。")
    pages.append({"page_number": len(pages) + 1, "chapter": "来源、选读说明与许可", "text": ("\n\n".join(attribution) + "\n\n原仓库许可证：\n" + license_text).strip(), "index_for_retrieval": False})
    digest = hashlib.sha256(json.dumps(pages, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return pages, digest


def require_ok(response: httpx.Response):
    response.raise_for_status()
    return response.json()


def import_pack(client: httpx.Client, pack: dict, pages: list[dict], *, approve_external: bool) -> dict:
    bases = require_ok(client.get("/api/v1/knowledge-bases"))
    matches = [base for base in bases if base["name"] == pack["knowledge_base_name"]]
    if len(matches) != 1:
        raise ValueError("必须存在唯一的已审核课程资料库；未自动新建或修改课程归属")
    base = matches[0]
    courses = require_ok(client.get("/api/v1/courses"))
    matched_courses = []
    for code in pack["course_codes"]:
        course = next((item for item in courses if item["code"] == code), None)
        if not course:
            raise ValueError(f"主打课程不存在：{code}")
        linked = require_ok(client.get(f"/api/v1/courses/{course['id']}/knowledge-bases"))
        if not any(item["id"] == base["id"] for item in linked):
            raise ValueError(f"{code} 未关联目标资料库，停止自动导入")
        matched_courses.append(code)
    documents = require_ok(client.get(f"/api/v1/knowledge-bases/{base['id']}/documents"))
    document = next((item for item in documents if item["id"] == stable_id(pack)), None)
    created = document is None
    if document is None:
        document = require_ok(client.post(f"/api/v1/knowledge-bases/{base['id']}/text-documents", json={
            "document_id": pack["id"], "title": pack["title"], "source_url": source_url(pack),
            "license_name": pack["license_name"], "license_url": pack["license_url"],
            "version_label": "R2-20261028-v1", "publication_status": "published", "pages": pages,
            "chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP,
        }, timeout=300))["document"]
    if document["status"] != "ready" or document["page_count"] != len(pages) or document["name"] != pack["title"]:
        raise ValueError("已有记录与固定版本不符；未覆盖旧记录，请人工核查")
    # A replay checks every stored page, rather than trusting a title/count match.
    content = require_ok(client.get(f"/api/v1/documents/{document['id']}/content"))
    actual = [{"page_number": p["page_number"], "chapter": p["chapter"], "text": p["content"],
               "index_for_retrieval": bool(p["chunks"])} for p in content["pages"]]
    if actual != pages:
        raise ValueError("已入库正文与固定版本不符；未重写历史页码")
    for expected, stored in zip(pages, content["pages"], strict=True):
        expected_chunks = chunk_document(SourceDocument(pack["id"], pack["title"], expected["page_number"],
            expected["text"], expected["chapter"]), chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) if expected["index_for_retrieval"] else []
        if [c.text for c in expected_chunks] != [c["content"] for c in stored["chunks"]]:
            raise ValueError("片段策略与固定版本不符；未覆盖历史索引")
    if approve_external and not document["external_model_allowed"]:
        document = require_ok(client.put(f"/api/v1/admin/documents/{document['id']}/external-sharing", json={
            "allowed": True, "confirmed": True,
            "reason": "2026-10-28 用户明确允许本轮新增资料的检索片段用于当前 AI 模型讲解；非整本上传。固定来源、逐文件哈希、署名与许可见旗舰课程选读登记。",
        }))
    return {"document_id": document["id"], "title": document["name"], "created": created,
            "pages": document["page_count"], "chunks": document["chunk_count"],
            "external_model_allowed": document["external_model_allowed"], "course_codes": matched_courses}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve-external", action="store_true", help="仅在用户明确批准本轮新增资料后使用")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with httpx.Client(timeout=60, follow_redirects=True) as remote:
        prepared = [(pack, *fetch_pages(remote, pack)) for pack in manifest["packs"]]
    report = {"edition": manifest["edition"], "mode": "apply" if args.apply else "dry-run", "documents": []}
    if args.apply:
        password = os.environ.get("RAG_ADMIN_PASSWORD")
        if not password:
            raise ValueError("请设置 RAG_ADMIN_PASSWORD；不会打印密码")
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60, trust_env=False) as client:
            login = require_ok(client.post("/api/v1/auth/login", json={"username": os.environ.get("RAG_ADMIN_USERNAME", "admin"), "password": password}))
            client.headers["Authorization"] = f"Bearer {login['access_token']}"
            for pack, pages, digest in prepared:
                report["documents"].append({**import_pack(client, pack, pages, approve_external=args.approve_external), "content_sha256": digest})
    else:
        report["documents"] = [{"document_id": stable_id(pack), "title": pack["title"], "pages": len(pages),
            "content_sha256": digest, "chapters": [p["chapter"] for p in pages]} for pack, pages, digest in prepared]
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
