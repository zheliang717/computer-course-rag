"""Pinned MDN excerpt excludes unsupported material and retains attribution."""

import base64
import hashlib

import pytest

from scripts import import_mdn_http_text as mdn


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, *, params, headers):
        self.calls.append((url, params, headers))
        return _Response(self.payload)


def test_pinned_source_refuses_changed_bytes_or_encoding() -> None:
    data = "固定中文来源".encode()
    encoded = base64.b64encode(data).decode()
    client = _Client({"encoding": "base64", "content": encoded})
    actual = hashlib.sha256(data).hexdigest().upper()
    assert mdn._github_file(client, mdn.SOURCE_PATH, actual) == "固定中文来源"
    assert client.calls[0][1] == {"ref": mdn.COMMIT}
    with pytest.raises(ValueError, match="哈希不符"):
        mdn._github_file(client, mdn.SOURCE_PATH, "0" * 64)
    with pytest.raises(ValueError, match="编码不符合预期"):
        mdn._github_file(_Client({"encoding": "plain", "content": encoded}), mdn.SOURCE_PATH, actual)


def test_excerpt_has_six_attributed_pages_without_images_or_old_transport_section() -> None:
    lines = ["课程正文。"] * 166
    lines[1] = "title: HTTP 概述"
    lines[7] = 'HTTP 是一种{{glossary("protocol","协议")}}。'
    lines[47] = "![图片](https://example.org/image.svg)"
    lines[61] = "[HTTP 标头](/zh-CN/docs/Web/HTTP/Reference/Headers)可扩展。"
    lines[65] = "HTTP 无状态，但 Cookie 可以建立会话。"
    lines[67] = "旧版连接段落不应入库。"
    lines[135] = '方法包括 {{HTTPMethod("GET")}}。'
    pages = mdn.build_pages("\n".join(lines), "All prose content is available under CC-BY-SA 2.5")
    assert [item["page_number"] for item in pages] == [1, 2, 3, 4, 5, 6]
    joined = "\n".join(item["text"] for item in pages)
    assert "HTTP 是一种协议" in joined and "HTTP 标头可扩展" in joined and "方法包括 GET" in joined
    assert "https://example.org/image.svg" not in joined and "旧版连接段落不应入库" not in joined
    assert mdn.SOURCE_URL in pages[0]["text"] and mdn.LICENSE_URL in pages[-1]["text"]
    assert "Cookie" not in pages[2]["text"] and "Cookie" in pages[3]["text"]
    assert "Mozilla 贡献者" in pages[-1]["text"] and "外发" in pages[-1]["text"]
    with pytest.raises(ValueError, match="许可"):
        mdn.build_pages("\n".join(lines), "许可不明")
