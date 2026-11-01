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
    #: 降 AI 段失败/取消后仍持有译文草稿：(原因, 草稿, 源语言, 目标语言)
    deai_failed = Signal(str, str, str, str)
    deai_cancelled = Signal(str, str, str)

    def __init__(self, text: str, provider: Provider, settings: Settings,
                 parent=None, *, resume: tuple[str, str] | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._provider = provider
        self._settings = settings
        self._resume = resume
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # noqa: D401 - QThread 入口
        try:
            if self._resume is None:
                result = translator.translate(
                    self._text,
                    self._provider,
                    self._settings,
                    emit=self.delta.emit,
                    should_cancel=self._cancel.is_set,
                    on_stage=self.stage_started.emit,
                    on_round_done=self.round_done.emit,
                )
            else:
                result = translator.deai_stage(
                    self._text,
                    self._provider,
                    self._settings,
                    self._resume[0],
                    self._resume[1],
                    emit=self.delta.emit,
                    should_cancel=self._cancel.is_set,
                    on_stage=self.stage_started.emit,
                    on_round_done=self.round_done.emit,
                )
        except translator.DeaiDraftError as exc:
            if exc.cancelled:
                self.deai_cancelled.emit(exc.draft, exc.source_lang, exc.target_lang)
            else:
                self.deai_failed.emit(exc.reason, exc.draft, exc.source_lang, exc.target_lang)
        except llm.Cancelled:
            if self._resume is not None:
                self.deai_cancelled.emit(self._text, self._resume[0], self._resume[1])
            else:
                self.cancelled.emit()
        except (llm.LLMError, EngineError, ConfigError) as exc:
            if self._resume is not None:
                self.deai_failed.emit(str(exc), self._text, self._resume[0], self._resume[1])
            else:
                self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - 线程边界不能把异常吞成静默退出
            self.failed.emit(f"翻译意外中断：{exc}")
        else:
            self.done.emit(result)
