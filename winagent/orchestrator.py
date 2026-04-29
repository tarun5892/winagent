"""Worker-thread loop: perceive -> plan -> validate -> confirm -> execute -> remember."""
from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .executor import Executor
from .logger import get_logger
from .memory import MemoryManager
from .safety import SafetyLayer
from .schema import AgentResponse

log = get_logger("orchestrator")


@dataclass
class Job:
    command: str


class Orchestrator(threading.Thread):
    """Single worker thread. Public API: :meth:`submit`, :meth:`stop`."""

    def __init__(
        self,
        confirm_fn: Callable[[str], bool],
        confirmation_mode: bool = True,
        client: Any | None = None,
        capture_fn: Callable[[], tuple[bytes, tuple[int, int]]] | None = None,
        executor: Executor | None = None,
        memory: MemoryManager | None = None,
        on_busy: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(daemon=True, name="winagent-orch")
        self.queue: queue.Queue[Job | None] = queue.Queue()
        self.memory = memory or MemoryManager()
        self.safety = SafetyLayer(confirm_fn, confirmation_mode)
        self.executor = executor or Executor()
        self._client = client
        self._capture = capture_fn
        self._stop_event = threading.Event()
        self._on_busy = on_busy

    @property
    def client(self) -> Any:
        if self._client is None:
            from .llm_base import make_client

            self._client = make_client()
        return self._client

    @property
    def capture(self) -> Callable[[], tuple[bytes, tuple[int, int]]]:
        if self._capture is None:
            from .vision import capture_screen

            self._capture = capture_screen
        return self._capture

    def submit(self, command: str) -> None:
        self.queue.put(Job(command=command))

    def stop(self) -> None:
        self._stop_event.set()
        self.queue.put(None)

    def run(self) -> None:
        log.info("orchestrator started")
        while not self._stop_event.is_set():
            job = self.queue.get()
            if job is None:
                break
            self._notify_busy(True)
            try:
                self.run_cycle(job)
            except Exception:
                log.exception("cycle failed")
            finally:
                self._notify_busy(False)
        log.info("orchestrator stopped")

    def _notify_busy(self, busy: bool) -> None:
        if self._on_busy is None:
            return
        try:
            self._on_busy(busy)
        except Exception:  # noqa: BLE001
            log.exception("on_busy callback raised")

    def run_cycle(self, job: Job) -> None:
        """Single perceive-plan-act cycle. Public for testability."""
        log.info("command: %s", job.command)
        self.memory.add_command(job.command)

        try:
            img, size = self.capture()
            log.info("screenshot %dx%d, %d KB", size[0], size[1], len(img) // 1024)
        except Exception as e:  # noqa: BLE001
            # Coding tasks may run on machines without a display server.
            # We still proceed — the LLM gets a 0x0 hint and (presumably)
            # picks coding-agent actions instead of clicks.
            log.warning("screenshot unavailable (%s); proceeding without one", e)
            img, size = b"", (0, 0)

        try:
            raw = self.client.plan(job.command, img, size, self.memory.snapshot())
        except Exception as e:  # noqa: BLE001
            log.error("plan failed: %s", e)
            return

        try:
            parsed = AgentResponse.model_validate(raw)
        except ValidationError as e:
            log.error("schema validation failed: %s", e)
            return

        allowed, rejects = self.safety.filter(parsed.actions)
        for reason in rejects:
            log.warning(reason)

        mem_update = parsed.memory_update.model_dump() if parsed.memory_update else None

        if not allowed:
            log.warning("no actions to execute")
            self.memory.update(mem_update)
            return

        if not self.safety.confirm_plan(allowed):
            log.info("user declined plan")
            return

        results = self.executor.run(allowed)
        for r in results:
            log.info("result: %s", r)

        self.memory.add_actions([a.model_dump() for a in allowed])
        self.memory.update(mem_update)
