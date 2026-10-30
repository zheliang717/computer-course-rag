import pytest

from app.domain import SearchHit, TextChunk
from app.generation import OpenAICompatibleGenerator, UnavailableGenerator, create_generator, practice_question_only


class Settings:
    llm_provider = "openai"
    llm_api_key = None
    llm_api_base = "https://example.invalid/v1"
    llm_model = "demo-model"
    llm_timeout_seconds = 1


def test_unconfigured_online_model_is_deferred_to_api_fallback() -> None:
    generator = create_generator(Settings())
    assert isinstance(generator, UnavailableGenerator)
    with pytest.raises(RuntimeError):
        generator.generate("问题", [])


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "基于证据的模型回答"}}]}


class FakeClient:
    def __init__(self) -> None:
        self.url = ""
        self.headers = {}
        self.payload = {}

    def post(self, url, *, headers, json):
        self.url = url
        self.headers = headers
        self.payload = json
        return FakeResponse()


def test_openai_compatible_generator_sends_retrieved_evidence() -> None:
    client = FakeClient()
    generator = OpenAICompatibleGenerator(
        api_base="https://example.test/v1",
        api_key="secret",
        model="course-model",
        client=client,
    )
    hit = SearchHit(
        chunk=TextChunk(
            chunk_id="1",
            document_id="doc",
            document_name="数据结构与算法：概论",
            page_number=8,
            text="数据结构包含逻辑结构、存储结构和支持的操作。",
        ),
        score=0.9,
    )
    assert generator.generate("数据结构的三个要素是什么？", [hit]) == "基于证据的模型回答"
    assert client.url.endswith("/chat/completions")
    assert client.headers["Authorization"] == "Bearer secret"
    assert "逻辑结构" in client.payload["messages"][1]["content"]


def test_openai_compatible_generator_can_answer_without_course_evidence() -> None:
    client = FakeClient()
    generator = OpenAICompatibleGenerator(
        api_base="https://example.test/v1",
        api_key="secret",
        model="general-model",
        client=client,
    )

    assert generator.generate("人工智能和机器学习有什么区别？", [], grounded=False) == "基于证据的模型回答"
    assert "通用知识" in client.payload["messages"][0]["content"]
    assert "证据：" not in client.payload["messages"][1]["content"]


def test_dashscope_generator_disables_slow_reasoning_for_teaching_content() -> None:
    client = FakeClient()
    generator = OpenAICompatibleGenerator(
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="secret",
        model="qwen-model",
        client=client,
    )

    generator.generate("生成教学计划", [], grounded=False)
    assert client.payload["enable_thinking"] is False
    assert client.payload["max_tokens"] == 2400


def test_embedded_assistant_uses_compact_teaching_style_without_affecting_drafts() -> None:
    client = FakeClient()
    generator = OpenAICompatibleGenerator(
        api_base="https://example.test/v1", api_key="secret", model="course-model", client=client,
    )
    generator.generate("解释进程和线程", [], grounded=False, task="assistant_chat")
    assert "嵌入式助手" in client.payload["messages"][0]["content"]
    assert "三百至六百字" in client.payload["messages"][0]["content"]
    assert "这不代表课程没有教材" in client.payload["messages"][0]["content"]
    assert "不要扩展未经核对的实现条件" in client.payload["messages"][0]["content"]
    assert client.payload["max_tokens"] == 1200
    generator.generate("生成完整教案", [], task="teaching_draft")
    assert client.payload["max_tokens"] == 2400
    assert "嵌入式助手" not in client.payload["messages"][0]["content"]


def test_teaching_draft_uses_course_evidence_without_answer_layout_instruction() -> None:
    client = FakeClient()
    generator = OpenAICompatibleGenerator(
        api_base="https://example.test/v1", api_key="secret", model="course-model", client=client,
    )
    hit = SearchHit(
        chunk=TextChunk(chunk_id="chunk-1", document_id="doc", document_name="数据结构教材",
                        page_number=12, text="中序遍历依次访问左子树、根结点、右子树。"),
        score=0.9,
    )
    generator.generate("只输出严格 JSON 题目草稿", [hit], task="teaching_draft")
    assert "供教师审核" in client.payload["messages"][0]["content"]
    assert "中序遍历" in client.payload["messages"][1]["content"]
    assert "严格 JSON" in client.payload["messages"][1]["content"]
    assert "使用 Markdown 排版" not in client.payload["messages"][1]["content"]


def test_practice_question_discards_model_answer_and_rejects_unstructured_text() -> None:
    question = practice_question_only('{"question":"请解释栈与队列的区别。","answer":"栈后进先出"}')
    assert "请解释栈与队列的区别" in question
    assert "栈后进先出" not in question
    with pytest.raises(RuntimeError, match="格式"):
        practice_question_only("练习：什么是栈？答案：后进先出")
    with pytest.raises(RuntimeError, match="无答案"):
        practice_question_only('{"question":"什么是栈？答案：后进先出"}')


def test_practice_generation_requests_question_only_json() -> None:
    client = FakeClient()
    generator = OpenAICompatibleGenerator(
        api_base="https://example.test/v1", api_key="secret", model="course-model", client=client,
    )
    generator.generate("生成本章练习", [], task="practice_question")
    assert '"question"' in client.payload["messages"][0]["content"]
    assert "不得给出答案" in client.payload["messages"][0]["content"]
