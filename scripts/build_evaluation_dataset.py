"""Build the versioned 150-case Chinese retrieval benchmark."""

import json
from pathlib import Path

from app.catalog import DEFAULT_KNOWLEDGE_BASE_ID, stable_document_uuid


TOPICS = [
    ("data-structure-elements", "数据结构由哪些基本要素构成", "tsinghua-dsa-introduction", ["逻辑结构", "存储结构", "操作"]),
    ("algorithm-complexity", "算法的时间复杂度和空间复杂度如何衡量", "tsinghua-dsa-introduction", ["时间复杂度", "空间复杂度", "复杂度"]),
    ("tree-concepts", "树结构中的根、结点和子树是什么关系", "tsinghua-dsa-trees", ["根", "结点", "子树"]),
    ("binary-tree-traversal", "二叉树的先序、中序和后序遍历有何区别", "tsinghua-dsa-trees", ["先序", "中序", "后序", "遍历"]),
    ("bst-definition", "二叉查找树对左右子树关键字有什么约束", "tsinghua-dsa-bst", ["左子树", "右子树", "关键字"]),
    ("bst-operations", "二叉查找树如何执行查找、插入和删除", "tsinghua-dsa-bst", ["查找", "插入", "删除"]),
    ("avl-balance", "AVL 树怎样利用平衡因子保持平衡", "tsinghua-dsa-bst", ["AVL", "平衡因子", "旋转"]),
    ("greedy-method", "贪心算法为什么每一步选择局部最优", "tsinghua-dsa-greedy-dp", ["贪心", "局部", "最优"]),
    ("dynamic-programming", "动态规划中的最优子结构和递推关系是什么", "tsinghua-dsa-greedy-dp", ["最优子结构", "递推关系", "动态规划"]),
    ("knapsack", "0-1 背包问题怎样用动态规划描述状态", "tsinghua-dsa-greedy-dp", ["背包", "状态", "动态规划"]),
]

PREFIXES = ["请解释", "从课程资料看", "请用定义说明", "复习时应如何理解"]
SUFFIXES = ["？", "，并指出核心概念。", "，其判断依据是什么？"]

NEGATIVE_QUESTIONS = [
    "光合作用的暗反应在哪里进行？", "法国大革命发生在哪一年？", "如何制作意大利提拉米苏？", "量子纠缠是否允许超光速通信？",
    "人体血液循环有哪些主要路径？", "如何为猫咪选择日常猫粮？", "莫扎特创作了哪些著名歌剧？", "太阳系中质量最大的行星是什么？",
    "明代瓷器有哪些典型纹样？", "个人所得税专项附加扣除如何申报？", "篮球比赛的三秒违例是什么？", "英语虚拟语气有哪些基本形式？",
    "咖啡豆浅烘和深烘有什么区别？", "地震震级和烈度有什么区别？", "如何修剪月季促进开花？", "古希腊城邦制度有什么特点？",
    "人体免疫系统如何识别病毒？", "新能源汽车电池冬季为何衰减？", "油画颜料与水彩颜料有什么区别？", "如何制定马拉松训练计划？",
    "海洋潮汐主要由什么引起？", "合同违约责任通常包括哪些形式？", "交响乐团有哪些主要声部？", "茶叶发酵程度如何影响口感？",
    "台风是如何形成并增强的？", "为什么北极会出现极昼和极夜？", "摄影中的光圈如何影响景深？", "细胞有丝分裂包括哪些阶段？",
    "中国古代科举制度如何演变？", "家用空调制冷循环是什么原理？",
]


def main() -> None:
    source_registry = {
        source["id"]: source
        for source in json.loads(Path("materials/sources.json").read_text(encoding="utf-8"))["sources"]
    }
    cases = []
    for topic_id, prompt, source_id, terms in TOPICS:
        source = source_registry[source_id]
        for prefix in PREFIXES:
            for suffix in SUFFIXES:
                cases.append({"id": f"{topic_id}-{len(cases) + 1:03d}", "kind": "positive", "topic": topic_id,
                              "question": f"{prefix}{prompt}{suffix}",
                              "expected_documents": [source["title"]],
                              "expected_document_ids": [str(stable_document_uuid(source_id))],
                              "expected_terms_any": terms})
    for index, question in enumerate(NEGATIVE_QUESTIONS, start=1):
        cases.append({"id": f"out-of-scope-{index:03d}", "kind": "negative", "topic": "out-of-scope",
                      "question": question, "expected_documents": [], "expected_terms_any": []})
    output = {"schema_version": 3, "dataset_version": "dsa-zh-150-v2",
              "knowledge_base_id": str(DEFAULT_KNOWLEDGE_BASE_ID),
              "description": "120 条课程内标注检索问题和 30 条资料外拒答问题；v2 用来源稳定 ID 标注目标资料，并按第 13 讲封面更正《基础算法》书名。",
              "source_correction": {
                  "source_id": "tsinghua-dsa-greedy-dp",
                  "official_title": source_registry["tsinghua-dsa-greedy-dp"]["title"],
                  "source_url": source_registry["tsinghua-dsa-greedy-dp"]["document_url"],
                  "sha256": source_registry["tsinghua-dsa-greedy-dp"]["sha256"],
                  "note": "v1 的《贪心与动态规划》是旧展示名；原 PDF 封面为第 13 讲《基础算法》，正文覆盖贪心法、动态规划与 0-1 背包。"},
              "case_count": len(cases), "cases": cases}
    target = Path("materials/eval/questions-150-v2.json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {target}")


if __name__ == "__main__":
    main()
