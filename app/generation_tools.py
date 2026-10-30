"""Bounded, request-local tool loop for compatible teaching chat.

Protocol reference: https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling
Tool arguments never become executable code or user-visible answer deltas.
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from time import perf_counter

import httpx

from app.calculations import TOOL_DEFINITIONS, calculate
from app.model_usage import estimate_tokens


class CalculationGeneration:
    MAX_ROUNDS = 4  # Up to three bounded tool rounds, then a final answer with no tools.
    MAX_TOOLS = 4
    MAX_REQUESTS = 8  # One bounded user request includes drafting and review.

    def __init__(self, *, checkpoint, before_upstream, on_stage, on_reset, on_usage, timeout, output_format='text', require_calculation=False, tools_enabled=True):
        self.checkpoint = checkpoint
        self.before_upstream = before_upstream
        self.on_stage = on_stage
        self.on_reset = on_reset
        self.on_usage = on_usage
        self._last_usage_report = 0.0
        self.deadline = perf_counter() + timeout
        self.receipts = []
        self.calls = []
        self.output_format = output_format
        self.require_calculation = require_calculation
        self.tools_enabled = tools_enabled

    def check(self):
        self.checkpoint()
        if perf_counter() >= self.deadline:
            raise httpx.TimeoutException('本次多步骤回答已到时间限制。')
        self._report_usage()

    def _report_usage(self, *, force=False):
        if self.calls and (force or perf_counter() - self._last_usage_report >= 2):
            self.on_usage(self.usage_values())
            self._last_usage_report = perf_counter()

    @contextmanager
    def _response(self, client, *, url, headers, payload, remaining, call):
        try:
            self.check()
            call['dispatched'] = True
            self._report_usage(force=True)
            with client.stream('POST', url, headers=headers, json=payload, timeout=remaining) as response:
                yield response
        finally:
            self._report_usage(force=True)

    def _usage(self):
        values = []
        for call in self.calls:
            if not call.get('dispatched'):
                continue
            provider = call.get('provider_usage')
            values.append({'round': call['round'], 'completed': call.get('completed', False),
                'input_tokens': provider[0] if provider else estimate_tokens(call['input']),
                'output_tokens': provider[1] if provider else estimate_tokens(call['output']),
                'token_source': 'provider' if provider else 'estimated'})
        return values

    def usage_values(self):
        values = self._usage()
        sources = {item['token_source'] for item in values}
        return {'token_counts': {'input_tokens': sum(item['input_tokens'] for item in values),
                                'output_tokens': sum(item['output_tokens'] for item in values)},
            'usage_detail': {'version': 1, 'quota_unit': 'user_request',
                'upstream_requests': len(values), 'tool_attempts': len(self.receipts),
                'token_source': next(iter(sources)) if len(sources) == 1 else 'mixed' if sources else 'none',
                'rounds': values}}

    def stream(self, client, *, url, headers, payload, on_response=None):
        messages = list(payload['messages'])
        messages[0] = {**messages[0], 'content': messages[0]['content'] + (
            '\n涉及明确数字或自己设计的定量例子时，先使用提供的计算工具。'
            '分页地址换算若已给出三个输入，优先一次调用 translate_page_address，完整计算页号、偏移和物理地址；不要拆成重复单步心算。'
            '参数不明确先解释假设或提问；不要假定偏移为零，不要将页号当基址。'
            '工具只能核对给定参数的算术，不能核对题意、真实页表或资料依据；不得声称整道题已验证。'
            '计算回执的 reference（如计算1）是工具引用编号，正文可写[计算1]；不得用[证据N]冒充工具输出的编号，资料引用仅支撑资料中的概念和公式。'
            '计算成功后解释含义并引用工具结果；不要另改输入或凭心算重造结果。' +
            ('调用工具前的草稿不会显示给用户；最终回答须从结论开始独立完整，不要承接草稿的章节编号。'
             if self.output_format != 'json' else
             '最终只返回任务要求的 JSON 对象，不输出额外说明或代码围栏；summary须独立完整。工具回执由服务器单独保存，不要在JSON中伪造回执。') +
            '若工具失败或达到本次上限，明确说明未完成计算，不捏造成功回执。')}
        for round_index in range(self.MAX_ROUNDS):
            self.check()
            self.before_upstream()  # Current course grants/material approval before EVERY external request.
            request_payload = {**payload, 'messages': messages, 'stream': True,
                               'stream_options': {'include_usage': True}}
            if len(self.calls) >= self.MAX_REQUESTS:
                raise RuntimeError('本次回答与复核已达到模型请求上限。')
            tools_allowed = self.tools_enabled and round_index < self.MAX_ROUNDS - 1 and len(self.receipts) < self.MAX_TOOLS
            if tools_allowed:
                request_payload.update(tools=TOOL_DEFINITIONS, tool_choice='auto', parallel_tool_calls=True)
                if self.require_calculation and round_index == 0:
                    request_payload['tool_choice'] = 'required'
            elif self.tools_enabled:
                messages = [*messages, {'role': 'system', 'content': '本次计算工具轮数已用完。仅解释已有结果；未计算的部分明确说明，不再设计新的数值例子。'}]
                request_payload['messages'] = messages
            if self.output_format == 'json' and not tools_allowed:
                request_payload['response_format'] = {'type': 'json_object'}
            encoded_input = json.dumps(request_payload, ensure_ascii=False)
            if len(encoded_input) > 400000:
                raise RuntimeError('本次回答上下文过长，请缩小问题范围。')
            call = {'round': len(self.calls) + 1, 'input': encoded_input, 'output': '', 'completed': False, 'dispatched': False}
            self.calls.append(call)
            self.on_stage('AI 正在结合计算结果组织解答…' if self.receipts else 'AI 正在组织解答…')
            collected = {}
            content_parts = []
            complete = False
            reset_emitted = False
            remaining = max(.1, self.deadline - perf_counter())
            with self._response(client, url=url, headers=headers, payload=request_payload, remaining=remaining, call=call) as response:
                response.raise_for_status()
                if on_response:
                    on_response(response)
                for line in response.iter_lines():
                    self.check()
                    if not line.startswith('data:'):
                        continue
                    raw = line[5:].strip()
                    if raw == '[DONE]':
                        complete = True
                        break
                    try:
                        data = json.loads(raw)
                        if not isinstance(data, dict) or data.get('error'):
                            raise RuntimeError('模型服务未能完成回答。')
                        usage = data.get('usage')
                        if isinstance(usage, dict) and all(type(usage.get(key)) is int and 0 <= usage[key] <= 10000000
                                                          for key in ('prompt_tokens', 'completion_tokens')):
                            call['provider_usage'] = (usage['prompt_tokens'], usage['completion_tokens'])
                        choices = data.get('choices') or []
                        if not choices:
                            continue
                        choice = choices[0]
                        reason = choice.get('finish_reason')
                        if reason not in (None, 'stop', 'tool_calls'):
                            raise RuntimeError('模型回答未完整生成，请缩小范围后重试。')
                        complete = complete or reason in ('stop', 'tool_calls')
                        delta = choice.get('delta') or {}
                        tool_deltas = delta.get('tool_calls') or []
                        if tool_deltas:
                            if not tools_allowed:
                                raise RuntimeError('模型超出本次工具调用限制，未执行额外工具。')
                            if not reset_emitted:
                                self.on_reset()
                                self.on_stage('正在核对计算参数并复算…')
                                reset_emitted = True
                            for item in tool_deltas:
                                index = item.get('index')
                                if type(index) is not int or not 0 <= index < self.MAX_TOOLS:
                                    raise RuntimeError('模型计算调用数量或格式超出限制。')
                                entry = collected.setdefault(index, {'id': '', 'type': 'function',
                                    'function': {'name': '', 'arguments': ''}})
                                identifier = item.get('id')
                                if identifier:
                                    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identifier):
                                        raise RuntimeError('模型工具编号格式不完整。')
                                    if entry['id'] and entry['id'] != identifier:
                                        raise RuntimeError('模型工具编号发生变化，未执行。')
                                    entry['id'] = identifier
                                if item.get('type') not in (None, 'function'):
                                    raise RuntimeError('模型请求了未开放的工具类型。')
                                function = item.get('function') or {}
                                for field, limit in (('name', 64), ('arguments', 8192)):
                                    piece = function.get(field)
                                    if piece is not None:
                                        if not isinstance(piece, str):
                                            raise RuntimeError('模型计算参数格式不完整。')
                                        if field != 'name' or entry['function'][field] != piece:
                                            entry['function'][field] += piece
                                        if len(entry['function'][field]) > limit:
                                            raise RuntimeError('模型计算参数超出长度限制。')
                                        call['output'] += piece
                        content = delta.get('content')
                        if isinstance(content, str) and content:
                            call['output'] += content
                            content_parts.append(content)
                            if len(call['output']) > 100000:
                                raise RuntimeError('模型回答超出长度限制。')
                            if not collected:
                                yield content
                    except (ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
                        raise RuntimeError('模型计算或流式数据格式无法解析。') from exc
            self.check()
            if not complete:
                raise RuntimeError('回答连接中断，未保存不完整内容。')
            call['completed'] = True
            self._report_usage(force=True)
            if not collected:
                if self.require_calculation and not any(item['status'] == 'completed' for item in self.receipts):
                    raise RuntimeError('本题要求计算核对，但未取得成功的工具回执。')
                if not ''.join(content_parts).strip():
                    raise RuntimeError('模型未返回完整解答。')
                return
            calls = [collected[key] for key in sorted(collected)]
            if len(calls) + len(self.receipts) > self.MAX_TOOLS or any(not entry['id'] for entry in calls):
                raise RuntimeError('模型计算调用超出数量限制或缺少编号。')
            if len({entry['id'] for entry in calls}) != len(calls):
                raise RuntimeError('模型重复使用了工具编号，未执行。')
            # The pre-tool draft was reset on the client. Do not tell the next
            # model round that this hidden draft has already been delivered.
            # Keep its tokens in accounting, but send only the tool-call envelope.
            messages.append({'role': 'assistant', 'content': '', 'tool_calls': calls})
            for entry in calls:
                self.check()
                try:
                    arguments = json.loads(entry['function']['arguments'],
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite')))
                except (ValueError, TypeError, RecursionError):
                    arguments = None
                receipt = calculate(entry['function']['name'], arguments, origin='assistant').model_dump(mode='json')
                receipt['reference'] = f'计算{len(self.receipts) + 1}'
                self.receipts.append(receipt)
                messages.append({'role': 'tool', 'tool_call_id': entry['id'],
                                 'content': json.dumps(receipt, ensure_ascii=False)})
        raise RuntimeError('计算轮数已达上限，本次未获得完整解答。')
