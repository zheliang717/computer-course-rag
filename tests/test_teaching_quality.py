from app.teaching_quality import repair_generated,findings

def test_observed_stack_heap_generalization_and_lifo_are_corrected():
    bad='栈由系统自动分配，堆需手动管理。\n核心思想：最近使用的数据优先处理。'
    repaired,changes=repair_generated(bad)
    assert len(changes)==2 and not findings(repaired)
    assert '最后入栈' in repaired and '语言与运行时' in repaired

def test_qualified_or_negated_explanation_is_not_rewritten():
    text='不能笼统说栈由系统自动分配，堆需手动管理。Java堆通常由垃圾回收器回收。'
    assert not findings(text)
    assert repair_generated(text)==(text,[])
