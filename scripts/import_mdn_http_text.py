"""Import a pinned, attributed Chinese excerpt of MDN's HTTP overview.

Only selected prose is copied. Images, examples, other linked pages and the
source's outdated connection/HTTP-version discussion are not imported.
The adapted excerpt remains CC BY-SA 2.5; external-model sharing stays off.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
from uuid import NAMESPACE_URL, uuid5

import httpx


REPOSITORY = "mdn/translated-content"
COMMIT = "13bc56a75ee7f979f3ceb36913b4366a63b6ac48"
SOURCE_PATH = "files/zh-cn/web/http/guides/overview/index.md"
SOURCE_SHA256 = "F05266E68CFF7455C6CD989D092E26262239F0CAFF4F4E58F1AA3FEDD54B85F9"
LICENSE_SHA256 = "57C0D7E200FADFDBADB04B9AB220297809BA7F2AC0ADAA6707A07FBA432B2EBE"
DOCUMENT_KEY = f"mdn-translated-content:{COMMIT}:{SOURCE_PATH}:selected-text"
TITLE = "MDN Web Docs：HTTP 概述（中文文字摘编）"
PUBLIC_URL = "https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Guides/Overview"
SOURCE_URL = f"https://github.com/{REPOSITORY}/blob/{COMMIT}/{SOURCE_PATH}"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/2.5/deed.zh"
LICENSE_SOURCE_URL = f"https://github.com/{REPOSITORY}/blob/{COMMIT}/LICENSE.md"


def _github_file(client: httpx.Client, path: str, expected_sha256: str) -> str:
    response = client.get(
        f"https://api.github.com/repos/{REPOSITORY}/contents/{path}",
        params={"ref": COMMIT}, headers={"User-Agent": "computer-course-rag-source-audit"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("encoding") != "base64":
        raise ValueError(f"MDN 来源编码不符合预期：{path}")
    data = base64.b64decode(payload["content"], validate=False)
    actual = hashlib.sha256(data).hexdigest().upper()
    if actual != expected_sha256:
        raise ValueError(f"固定 MDN 来源哈希不符：{path}，已停止导入")
    return data.decode("utf-8")


def _plain_lines(lines: list[str], *ranges: tuple[int, int]) -> str:
    selected: list[str] = []
    for first, last in ranges:
        if first < 1 or last > len(lines) or first > last:
            raise ValueError("MDN 摘编行号超出固定来源范围")
        selected.extend(lines[first - 1:last])
    readable: list[str] = []
    for raw in selected:
        line = raw.strip()
        if not line or line.startswith("!["):
            continue
        if line.startswith("```") or "<script" in line.lower():
            raise ValueError("MDN 摘编意外包含代码或脚本")

        def macro_label(match: re.Match[str]) -> str:
            labels = re.findall(r'"([^"]*)"', match.group(0))
            if not labels:
                raise ValueError("MDN 摘编出现未知模板宏")
            return labels[1] if len(labels) > 1 and labels[1] else labels[0]

        line = re.sub(r"\{\{[^{}]+\}\}", macro_label, line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = line.lstrip("# ").replace("**", "").replace("*", "").replace("`", "")
        if "{{" in line or "![" in line or "](" in line:
            raise ValueError("MDN 摘编仍含未处理的模板、图片或链接")
        if line:
            readable.append(line)
    return "\n".join(readable)


def build_pages(source: str, license_text: str) -> list[dict]:
    lines = source.splitlines()
    if len(lines) < 166 or lines[1].strip() != "title: HTTP 概述" or "CC-BY-SA 2.5" not in license_text:
        raise ValueError("MDN 正文或许可与固定审核范围不符")
    attribution = (
        f"原文：《HTTP 概述》，MDN Web Docs / Mozilla 贡献者。\n"
        f"公开页面：{PUBLIC_URL}\n固定版本：{SOURCE_URL}\n"
        f"本系统为中文文字摘编，按主题重排页码；省略图片、代码示例、站外链接和原页的部分旧版本传输说明。"
    )
    return [
        {"page_number": 1, "chapter": "客户端、服务端与应用层", "text": attribution + "\n\n" +
         _plain_lines(lines, (8, 8), (12, 12), (20, 22), (26, 26), (30, 30), (34, 36), (40, 40))},
        {"page_number": 2, "chapter": "代理的作用", "text": _plain_lines(lines, (44, 52))},
        {"page_number": 3, "chapter": "HTTP 的简洁与扩展", "text": _plain_lines(lines, (56, 62))},
        {"page_number": 4, "chapter": "HTTP 无状态与会话", "text": _plain_lines(lines, (64, 66))},
        {"page_number": 5, "chapter": "请求与响应报文", "text": _plain_lines(lines, (122, 126), (128, 140), (142, 154))},
        {"page_number": 6, "chapter": "来源、改编与许可", "text":
         f"{attribution}\n\n本摘编文字与原文同按 CC BY-SA 2.5 许可提供，须保留 MDN Web Docs / Mozilla 贡献者署名、来源、许可和改编说明。\n"
         f"许可条款：{LICENSE_URL}\n原仓库许可文件：{LICENSE_SOURCE_URL}\n"
         "本资料仅作站内课程辅助阅读；向外部模型传送片段另须按当前服务商和用途逐文档审核，本次未批准外发。"},
    ]


def _json(response: httpx.Response):
    if response.is_error:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.status_code} {response.text[:500]}")
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--force", action="store_true", help="重新导入并撤销已有外发批准")
    parser.add_argument("--dry-run", action="store_true", help="仅核对来源和生成主题页，不写入知识库")
    args = parser.parse_args()

    with httpx.Client(timeout=90) as client:
        source = _github_file(client, SOURCE_PATH, SOURCE_SHA256)
        license_text = _github_file(client, "LICENSE.md", LICENSE_SHA256)
        pages = build_pages(source, license_text)
    if args.dry_run:
        for page in pages:
            print(f"第 {page['page_number']} 页 · {page['chapter']} · {len(page['text'])} 字符")
        return 0

    username = os.environ.get("RAG_ADMIN_USERNAME", "admin")
    password = os.environ.get("RAG_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("请先设置 RAG_ADMIN_PASSWORD 环境变量。")
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180) as client:
        login = _json(client.post("/api/v1/auth/login", json={"username": username, "password": password}))
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        bases = _json(client.get("/api/v1/knowledge-bases"))
        base = next((item for item in bases if item["name"] == "计算机网络开放教材"), None)
        if base is None:
            raise RuntimeError("找不到计算机网络开放教材资料库，未进行导入")
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
            "license_name": "CC BY-SA 2.5（中文文字摘编，同许可）",
            "license_url": LICENSE_URL,
            "version_label": f"固定提交 {COMMIT[:12]}",
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
