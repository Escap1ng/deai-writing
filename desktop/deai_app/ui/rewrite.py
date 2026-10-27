"""rewrite — 把改写闭环放到 QThread；主线程只通过信号收增量。

流式调用是阻塞的，直接放界面线程会让窗口在整轮生成期间无响应；
取消用 Event 传递给 llm.stream_chat 的 should_cancel。
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from deai_app.bridge import EngineError
from deai_app.core import llm, pipeline, translate as translator
from deai_app.core.config import ConfigError, Provider, Settings


class RewriteWorker(QThread):
    delta = Signal(str)
    round_started = Signal(int)
    round_done = Signal(int, object)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, text: str, provider: Provider, settings: Settings,
                 parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self._provider = provider
        self._settings = settings
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # noqa: D401 - QThread 入口
        try:
            result = pipeline.rewrite(
                self._text,
                self._provider,
                self._settings,
                emit=self.delta.emit,
                should_cancel=self._cancel.is_set,
                on_round_start=self.round_started.emit,
                on_round_done=self.round_done.emit,
            )
        except llm.Cancelled:
            self.cancelled.emit()
        except (llm.LLMError, EngineError, ConfigError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - 线程边界不能把异常吞成静默退出
            self.failed.emit(f"改写意外中断：{exc}")
        else:
            self.done.emit(result)


class TranslationWorker(QThread):
    delta = Signal(str)
    stage_started = Signal(str, int)
    round_done = Signal(int, object)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, text: str, provider: Provider, settings: Settings,
                 parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self._provider = provider
        self._settings = settings
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # noqa: D401 - QThread 入口
        try:
            result = translator.translate(
                self._text,
                self._provider,
                self._settings,
                emit=self.delta.emit,
                should_cancel=self._cancel.is_set,
                on_stage=self.stage_started.emit,
                on_round_done=self.round_done.emit,
            )
        except llm.Cancelled:
            self.cancelled.emit()
        except (llm.LLMError, EngineError, ConfigError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - 线程边界不能把异常吞成静默退出
            self.failed.emit(f"翻译意外中断：{exc}")
        else:
            self.done.emit(result)
