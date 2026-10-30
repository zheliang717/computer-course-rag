"""Bounded, cancellable bridge between synchronous retrieval/LLM code and SSE."""
from __future__ import annotations

import asyncio
import json
from queue import Empty, Full, Queue
from threading import Event, Lock


class GenerationCancelled(Exception):
    pass


class AnswerStream:
    def __init__(self) -> None:
        self.cancelled = Event()
        self._events: Queue[tuple[str, dict]] = Queue(maxsize=128)
        self._response = None
        self._response_lock = Lock()

    def attach_upstream(self, response) -> None:
        with self._response_lock:
            self._response = response
        if self.cancelled.is_set():
            response.close()
            self.check()

    def cancel(self) -> None:
        self.cancelled.set()
        with self._response_lock:
            response = self._response
            self._response = None
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def check(self) -> None:
        if self.cancelled.is_set():
            raise GenerationCancelled()

    def emit(self, event: str, data: dict) -> None:
        while True:
            self.check()
            try:
                self._events.put((event, data), timeout=0.2)
                return
            except Full:
                continue

    async def events(self):
        try:
            while True:
                if self.cancelled.is_set():
                    yield 'event: cancelled\ndata: {"detail":"请求已停止，请核对最终状态。"}\n\n'
                    return
                try:
                    event, data = await asyncio.to_thread(self._events.get, True, 3)
                except Empty:
                    yield ": heartbeat\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if event in {"done", "error"}:
                    return
        finally:
            self.cancelled.set()
