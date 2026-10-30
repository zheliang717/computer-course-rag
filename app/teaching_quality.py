"""Small explicit concept guardrails, never a general teaching approval engine."""
import re

RULES=[
 ('stack_heap_scope',r'栈(?:内存)?(?:由|是由)系统自动分配[，,；;、\s]*(?:而)?堆(?:内存)?(?:需|需要|必须)(?:由程序员)?手动管理',
  '这里讨论数据结构栈的后进先出规则。运行时栈内存与堆内存是另一话题；分配和回收方式取决于语言与运行时，不能笼统认为堆都由程序员手动管理。',
  '区分数据结构栈与内存栈；堆的回收须说明C/C++、Python/Java等语言和运行时条件。'),
 ('lifo_recent_push',r'核心(?:思想|规则)[：:：\s]*最近使用的数据优先处理',
  '核心规则：最后入栈的元素最先出栈（LIFO）。','LIFO指最后入栈，不能笼统换成最近访问或最近使用。')]

def findings(text):
    out=[]
    for key,pattern,_,message in RULES:
        for match in re.finditer(pattern,text):
            prefix=text[max(0,match.start()-16):match.start()]
            if re.search(r'不能|不可|并非|错误(?:说法)?|不应',prefix):continue
            out.append(dict(rule=key,severity='warning',quote=match.group(),message=message,start=match.start(),end=match.end()))
    return out

def repair_generated(text):
    corrections=[]
    for key,pattern,replacement,message in RULES:
        matches=[f for f in findings(text) if f['rule']==key]
        for f in reversed(matches):text=text[:f['start']]+replacement+text[f['end']:]
        if matches:corrections.append(dict(rule=key,message=message))
    return text,corrections
