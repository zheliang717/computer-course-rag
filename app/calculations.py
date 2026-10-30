"""Small deterministic teaching tools. No eval, names, calls, I/O or database writes.

A receipt proves arithmetic for the supplied inputs, not that model-selected
inputs match the question, that a source supports it, or that an answer is correct.
"""
from __future__ import annotations

import ast
import json
from decimal import Decimal, localcontext
from fractions import Fraction
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class CalculationStep(BaseModel):
    label: str
    expression: str
    result: str


class CalculationReceipt(BaseModel):
    id: str
    tool: Literal['calculate_expression', 'translate_page_address', 'trace_binary_search', 'simulate_page_replacement', 'unsupported']
    title: str
    origin: Literal['assistant', 'manual']
    status: Literal['completed', 'error']
    reference: str | None = Field(default=None, max_length=20)
    arguments: dict[str, str] = Field(default_factory=dict)
    steps: list[CalculationStep] = Field(default_factory=list)
    result: str | None = None
    exact_result: str | None = None
    error: str | None = None
    boundary: str = '仅按列出的参数计算；参数是否符合题意、资料依据与完整解法仍需核对。'


class ExpressionArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expression: str = Field(min_length=1, max_length=300)


class PageArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    virtual_address: str = Field(min_length=1, max_length=70)
    page_size_bytes: str = Field(min_length=1, max_length=70)
    physical_page_number: str = Field(min_length=1, max_length=70)

    @field_validator('*', mode='before')
    @classmethod
    def numeric_text(cls, value):
        if type(value) is int:
            return str(value)
        return value


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: Literal['calculate_expression', 'translate_page_address', 'trace_binary_search', 'simulate_page_replacement']
    arguments: dict = Field(max_length=4)


class BinarySearchArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    values: list[int] = Field(min_length=0, max_length=64)
    target: int


class ReplacementArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    algorithm: Literal['LRU', 'FIFO', 'OPT']
    frames: int = Field(ge=1, le=8)
    references: list[int] = Field(min_length=1, max_length=64)


TOOL_DEFINITIONS = [
    {'type': 'function', 'function': {
        'name': 'calculate_expression',
        'description': '按明确数字精确复算算式。支持 + - * / // % **、整数位运算与括号，不支持变量、函数、代码或单位。用于核对数值示例，不能核实题意。',
        'parameters': {'type': 'object', 'properties': {'expression': {'type': 'string',
            'description': '纯数字算式，十六进制用0x、二进制用0b；十进制小数按精确分数计算，最多300字符。'}},
            'required': ['expression'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {
        'name': 'translate_page_address',
        'description': '在已明确虚拟地址、页大小和映射后的物理页号时，计算虚拟页号、页内偏移及物理地址。不要将物理页号当成物理基址；不查询真实页表。',
        'parameters': {'type': 'object', 'properties': {
            'virtual_address': {'type': 'string', 'description': '无符号虚拟地址，十进制或0x/0b前缀整数，不得写VA等变量。'},
            'page_size_bytes': {'type': 'string', 'description': '以字节为单位的页大小，必须是2的幂，例如4096表示4KiB；单位未明确时先向用户说明假设。'},
            'physical_page_number': {'type': 'string', 'description': '虚拟页通过页表映射到的物理页号（不是物理基址），十进制或0x/0b前缀整数。'}},
            'required': ['virtual_address', 'page_size_bytes', 'physical_page_number'], 'additionalProperties': False}}},
]

TOOL_DEFINITIONS.extend([
    {'type': 'function', 'function': {'name': 'trace_binary_search',
     'description': '逐轮复算有序数组闭区间二分查找，返回区间、中点、比较和边界变化。自拟二分例子也须核对；不执行用户代码。',
     'parameters': {'type': 'object', 'properties': {'values': {'type': 'array', 'items': {'type': 'integer'}, 'maxItems': 64},
        'target': {'type': 'integer'}}, 'required': ['values', 'target'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'simulate_page_replacement',
     'description': '对明确的访问序列和页框数逐步模拟LRU、FIFO或OPT，返回命中/缺页、淘汰页和总缺页数；单个序列结果不能证明对所有序列最优。',
     'parameters': {'type': 'object', 'properties': {'algorithm': {'type': 'string', 'enum': ['LRU', 'FIFO', 'OPT']},
        'frames': {'type': 'integer', 'minimum': 1, 'maximum': 8},
        'references': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 1, 'maxItems': 64}},
        'required': ['algorithm', 'frames', 'references'], 'additionalProperties': False}}},
])


def _bounded(value: Fraction) -> Fraction:
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > 512:
        raise ValueError('数值超出计算工具的长度限制，请缩小输入。')
    return value


def _number(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f'{value.numerator}/{value.denominator}'


def _decimal(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    with localcontext() as context:
        context.prec = 18
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def _expression(text: str):
    try:
        tree = ast.parse(text.strip(), mode='eval')
    except (SyntaxError, RecursionError) as exc:
        raise ValueError('算式格式不正确，只能使用明确数字和支持的运算符。') from exc
    if len(list(ast.walk(tree))) > 80:
        raise ValueError('算式过于复杂，请拆成较短步骤。')
    steps = []

    def integer(value):
        if value.denominator != 1:
            raise ValueError('位运算和移位参数必须是整数。')
        return value.numerator

    def visit(node, depth=0):
        if depth > 16:
            raise ValueError('算式括号嵌套过深。')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(text.strip(), node).replace('_', '')
            if re.fullmatch(r'0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+', literal):
                return _bounded(Fraction(int(literal, 0)))
            if not re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,3})?', literal):
                raise ValueError('不支持这个数字格式。')
            exponent = re.search(r'[eE]([+-]?\d+)$', literal)
            if exponent and abs(int(exponent[1])) > 100:
                raise ValueError('科学计数法指数超出限制。')
            return _bounded(Fraction(literal))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Invert)):
            operand = visit(node.operand, depth + 1)
            return _bounded(operand if isinstance(node.op, ast.UAdd) else -operand if isinstance(node.op, ast.USub)
                            else Fraction(~integer(operand)))
        if not isinstance(node, ast.BinOp):
            raise ValueError('仅支持数字和白名单运算符；不支持变量、函数或代码。')
        left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
        op = node.op
        if isinstance(op, ast.Add): value = left + right
        elif isinstance(op, ast.Sub): value = left - right
        elif isinstance(op, ast.Mult): value = left * right
        elif isinstance(op, ast.Div): value = left / right
        elif isinstance(op, ast.FloorDiv): value = Fraction(left // right)
        elif isinstance(op, ast.Mod): value = left % right
        elif isinstance(op, ast.Pow):
            exponent = integer(right)
            if abs(exponent) > 64:
                raise ValueError('幂指数必须是 -64 至 64 的整数。')
            value = left ** exponent
        elif isinstance(op, (ast.BitAnd, ast.BitOr, ast.BitXor)):
            a, b = integer(left), integer(right)
            value = Fraction(a & b if isinstance(op, ast.BitAnd) else a | b if isinstance(op, ast.BitOr) else a ^ b)
        elif isinstance(op, (ast.LShift, ast.RShift)):
            shift = integer(right)
            if not 0 <= shift <= 128:
                raise ValueError('移位位数必须是 0 至 128 的整数。')
            value = Fraction(integer(left) << shift if isinstance(op, ast.LShift) else integer(left) >> shift)
        else:
            raise ValueError('这个运算符不在允许范围内。')
        value = _bounded(value)
        if len(steps) >= 20:
            raise ValueError('计算步骤过多，请拆分算式。')
        steps.append(CalculationStep(label=f'第 {len(steps) + 1} 步',
            expression=ast.get_source_segment(text.strip(), node), result=_number(value)))
        return value

    result = visit(tree.body)
    return result, steps


def _unsigned(text):
    value = text.strip()
    if not re.fullmatch(r'\d+|0[xX][0-9a-fA-F]+|0[bB][01]+', value):
        raise ValueError('地址、页号和页大小须为非负整数，十六进制需带0x前缀。')
    number = int(value, 0) if value.lower().startswith(('0x', '0b')) else int(value, 10)
    if number.bit_length() > 64:
        raise ValueError('本工具仅接收不超过64位的非负输入整数。')
    return number


def calculate(tool: str, arguments: dict, *, origin: Literal['assistant', 'manual']) -> CalculationReceipt:
    kind = tool if tool in ('calculate_expression', 'translate_page_address', 'trace_binary_search', 'simulate_page_replacement') else 'unsupported'
    receipt = CalculationReceipt(id=str(uuid4()), tool=kind, origin=origin, status='error',
        title={'calculate_expression': '算式复算', 'translate_page_address': '分页地址换算',
               'trace_binary_search': '二分查找逐轮核对', 'simulate_page_replacement': '页面置换逐步模拟'}.get(kind, '未开放的工具'))
    try:
        if kind == 'calculate_expression':
            args = ExpressionArguments.model_validate(arguments)
            receipt.arguments = args.model_dump()
            result, receipt.steps = _expression(args.expression)
            receipt.exact_result = _number(result)
            receipt.result = _decimal(result)
            if result.denominator != 1:
                receipt.boundary += ' 分数为精确值，小数最多18位有效数字，必要时已舍入。'
        elif kind == 'translate_page_address':
            args = PageArguments.model_validate(arguments)
            va, page, ppn = map(_unsigned, (args.virtual_address, args.page_size_bytes, args.physical_page_number))
            if page == 0 or page & (page - 1):
                raise ValueError('页大小须为正的2次幂，单位是字节。')
            vpn, offset = divmod(va, page)
            physical = ppn * page + offset
            receipt.arguments = {'virtual_address': str(va), 'page_size_bytes': str(page), 'physical_page_number': str(ppn)}
            receipt.steps = [
                CalculationStep(label='虚拟页号', expression=f'{va} // {page}', result=str(vpn)),
                CalculationStep(label='页内偏移', expression=f'{va} % {page}', result=str(offset)),
                CalculationStep(label='物理地址（十进制）', expression=f'{ppn} * {page} + {offset}', result=str(physical)),
                CalculationStep(label='物理地址（十六进制）', expression=f'十进制 {physical} 转十六进制', result=hex(physical)),
            ]
            receipt.exact_result = receipt.result = str(physical)
            receipt.boundary += ' 输入及十进制步骤以字节计；未查询真实页表、权限、缺页状态或目标硬件地址宽度。'
        elif kind == 'trace_binary_search':
            args = BinarySearchArguments.model_validate(arguments)
            if any(abs(v) > 10**12 for v in [*args.values, args.target]) or args.values != sorted(args.values):
                raise ValueError('请提供升序数组及不超过一万亿的整数。')
            receipt.arguments = {'values': json.dumps(args.values), 'target': str(args.target)}
            left, right, found = 0, len(args.values) - 1, -1
            while left <= right:
                middle = left + (right - left) // 2
                value = args.values[middle]
                expression = f'区间 [{left},{right}]；m={left}+({right}-{left})//2={middle}；a[m]={value}'
                if value == args.target:
                    found = middle
                    next_step = f'找到目标，索引 {middle}'
                elif value < args.target:
                    left = middle + 1
                    next_step = f'小于目标，下一闭区间 [{left},{right}]'
                else:
                    right = middle - 1
                    next_step = f'大于目标，下一闭区间 [{left},{right}]'
                receipt.steps.append(CalculationStep(label=f'第{len(receipt.steps)+1}轮', expression=expression, result=next_step))
                if found >= 0:
                    break
            receipt.result = receipt.exact_result = str(found)
            receipt.boundary += ' 采用升序数组、闭区间与向下取整中点；重复值返回其中一次命中的索引，不证明用户代码正确。'
        elif kind == 'simulate_page_replacement':
            args = ReplacementArguments.model_validate(arguments)
            if any(not 0 <= page <= 10**6 for page in args.references):
                raise ValueError('页号须为0至一百万的整数。')
            receipt.arguments = {'algorithm': args.algorithm, 'frames': str(args.frames), 'references': json.dumps(args.references)}
            resident, last_use, inserted, faults = [], {}, {}, 0
            for index, page in enumerate(args.references):
                victim = None
                is_fault = page not in resident
                if is_fault:
                    faults += 1
                    if len(resident) == args.frames:
                        if args.algorithm == 'LRU':
                            victim = min(resident, key=lambda p: last_use[p])
                        elif args.algorithm == 'FIFO':
                            victim = min(resident, key=lambda p: inserted[p])
                        else:
                            future = args.references[index+1:]
                            victim = max(resident, key=lambda p: future.index(p) if p in future else float('inf'))
                        resident.remove(victim)
                    resident.append(page)
                    inserted[page] = index
                last_use[page] = index
                receipt.steps.append(CalculationStep(label=f'访问{index+1}', expression=f'页{page}',
                    result=f'{"缺页" if is_fault else "命中"}；淘汰 {victim if victim is not None else "无"}；驻留 {resident}；累计缺页 {faults}'))
            receipt.result = receipt.exact_result = str(faults)
            receipt.boundary += ' 仅模拟该序列、初始为空的页框；OPT读取未来作对照，LRU/FIFO不预知未来，单个样例不证明普遍优劣。'
        else:
            raise ValueError('该工具未开放；仅能执行已列出的确定性计算。')
        receipt.status = 'completed'
    except ValidationError:
        receipt.error = '计算参数格式不正确，请按工具字段提供明确数字或算式。'
    except ZeroDivisionError:
        receipt.error = '除数不能为零。'
    except (ValueError, OverflowError, RecursionError) as exc:
        receipt.error = str(exc)[:250] or '这组参数无法计算，请核对后重试。'
    return receipt


def calculation_markdown(records: list[dict]) -> str:
    if not records:
        return ''
    parts = ['\n\n## 工具计算回执\n\n以下仅复算给定参数，不代表整道题或 AI 讲解已核实。']
    for data in records:
        receipt = CalculationReceipt.model_validate(data)
        parts.append(f'\n\n### {receipt.reference or "计算"} · {receipt.title}\n')
        if receipt.status != 'completed':
            parts.append('计算未完成，请重新核对参数。')
            continue
        parts.extend(f'- `{key}`：`{value}`' for key, value in receipt.arguments.items())
        parts.extend(f'- {step.label}：`{step.expression}` = `{step.result}`' for step in receipt.steps)
        parts.append(f'\n结果：`{receipt.result}`；精确值：`{receipt.exact_result}`。\n\n{receipt.boundary}')
    return '\n'.join(parts)
