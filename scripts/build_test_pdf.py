"""Build an original three-page PDF fixture without external fonts or downloads."""
from pathlib import Path
import pymupdf as fitz

OUTPUT = Path(__file__).resolve().parents[1] / 'materials/test-data/computer-course-rag-test-data.pdf'
PAGES = [
    ('栈与队列', '栈按后进先出顺序访问元素，适合保存函数调用和撤销步骤。队列按先进先出顺序处理元素，适合按到达顺序安排任务。\n\n设栈依次压入 A、B、C，连续弹出时得到 C、B、A。设队列依次加入 A、B、C，连续取出时得到 A、B、C。\n\n练习：编辑器撤销最近一次操作时，为什么可以使用栈？'),
    ('二叉搜索树', '二叉搜索树在每个节点上区分较小与较大的关键字。查找时比较目标和当前关键字，再选择下一棵子树。\n\n若树保持平衡，访问路径随节点数按对数增长；若树退化成长链，查找可能访问全部节点。中序遍历依次访问左子树、当前节点和右子树。\n\n练习：在根节点为 8、左孩子为 3、右孩子为 12 的树中查找 12，需要怎样比较？'),
    ('排序与复杂度', '排序把记录按指定关键字组织成有序序列。评价排序算法时，可以分别考虑比较次数、额外空间和相等关键字的顺序。\n\n快速排序通过划分缩小后续问题；归并排序先拆分，再合并有序子序列。两者的性能需要结合输入分布和具体实现分析。\n\n练习：当两条记录关键字相同时，为什么有些业务希望保留它们原来的先后顺序？'),
]

def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as document:
        for number, (title, text) in enumerate(PAGES, 1):
            page = document.new_page()
            body = f'智学助手原创演示资料\n\n{title}\n\n{text}\n\n第 {number} 页 · 原创测试文本 · AGPL-3.0-only'
            remaining = page.insert_textbox(fitz.Rect(54, 54, 540, 760), body, fontsize=13, fontname='china-s', lineheight=1.7)
            if remaining < 0:
                raise RuntimeError('Demo text exceeded the page area.')
        document.set_metadata({'title': '智学助手原创演示资料', 'author': 'zheliang717', 'subject': 'Original synthetic teaching fixture; AGPL-3.0-only'})
        document.save(OUTPUT, garbage=4, deflate=True)
    print(OUTPUT)

if __name__ == '__main__':
    build()
