# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


from __future__ import annotations

from collections.abc import Callable
import pytest
import json
import logging
import time

from forktex.log import HumanFormatter, setup_logging, shutdown_logging


def test_setup_logging_debug_uses_human_formatter(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(service="test", debug=True)
    log = logging.getLogger("test.human")
    log.debug("debug message")
    captured = capsys.readouterr()
    try:
        json.loads(captured.out.strip())
        valid_json = True
    except json.JSONDecodeError, ValueError:
        valid_json = False
    assert not valid_json or captured.out == ""


def test_setup_logging_json_forced_in_debug(capture_json: Callable[..., tuple[logging.Logger, list[dict]]]) -> None:
    setup_logging(service="test", debug=True, json=True)
    log, captured = capture_json()
    log.info("forced json")
    assert captured[0]["level"] == "INFO"


def test_setup_logging_custom_handlers() -> None:
    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    setup_logging(service="test", handlers=[CaptureHandler()], json=True)
    log = logging.getLogger("test.custom_handlers")
    log.info("via custom handler")
    assert captured == ["via custom handler"]


def test_setup_logging_queue_mode_delivers_records() -> None:
    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    setup_logging(service="test", queue=True, handlers=[CaptureHandler()], json=True)
    log = logging.getLogger("test.queue")
    log.info("queued message")

    deadline = time.monotonic() + 2
    while not captured and time.monotonic() < deadline:
        time.sleep(0.01)

    assert captured == ["queued message"]


def test_setup_logging_env_level_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORKTEX_LOG_LEVEL", "DEBUG")
    setup_logging(service="test")
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_env_debug_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORKTEX_LOG_DEBUG", "true")
    setup_logging(service="test")
    assert logging.getLogger().level == logging.DEBUG
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, HumanFormatter)


def test_setup_logging_env_json_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORKTEX_LOG_JSON", "0")
    setup_logging(service="test", debug=False)
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, HumanFormatter)


def test_setup_logging_explicit_arg_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORKTEX_LOG_DEBUG", "true")
    setup_logging(service="test", debug=False)
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_quiet_defaults_opt_out() -> None:
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    setup_logging(service="test", quiet_defaults=False)
    assert logging.getLogger("httpx").level == logging.NOTSET


def test_setup_logging_quiet_defaults_applied_by_default() -> None:
    setup_logging(service="test")
    assert logging.getLogger("httpx").level == logging.WARNING


def test_setup_logging_custom_quiet_loggers() -> None:
    logging.getLogger("some.noisy.thing").setLevel(logging.NOTSET)
    setup_logging(service="test", quiet=["some.noisy.thing"], quiet_level=logging.ERROR)
    assert logging.getLogger("some.noisy.thing").level == logging.ERROR


def test_setup_logging_fmt_datefmt_passthrough() -> None:
    setup_logging(service="test", debug=True, fmt="%(message)s", datefmt="%H:%M")
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, HumanFormatter)
    record = logging.LogRecord("x", logging.INFO, "path", 1, "hi", None, None)
    assert handler.formatter.format(record) == "hi"


def test_setup_logging_level_filters_records() -> None:
    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    setup_logging(service="test", level=logging.WARNING, handlers=[CaptureHandler()], json=True)
    log = logging.getLogger("test.level_filter")
    log.info("should be filtered out")
    log.warning("should pass through")
    assert captured == ["should pass through"]


def test_setup_logging_repeated_calls_with_different_configs() -> None:
    first_captured: list[str] = []
    second_captured: list[str] = []

    class FirstHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            first_captured.append(record.getMessage())

    class SecondHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            second_captured.append(record.getMessage())

    setup_logging(service="a", handlers=[FirstHandler()], json=True, level=logging.INFO)
    setup_logging(service="b", handlers=[SecondHandler()], debug=True)

    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, HumanFormatter)

    logging.getLogger("test.repeated").info("only second handler should see this")
    assert first_captured == []
    assert second_captured == ["only second handler should see this"]


def test_repeated_queue_setup_does_not_accumulate_listener_threads() -> None:
    import threading

    import forktex.log as log_module

    before = threading.active_count()
    for _ in range(5):
        setup_logging(service="test", queue=True, handlers=[logging.NullHandler()])
    assert log_module._queue_listener is not None

    assert threading.active_count() <= before + 1, "listener threads accumulated across setup_logging calls"

    shutdown_logging()
    assert log_module._queue_listener is None


def test_shutdown_logging_flushes_queued_records() -> None:
    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    setup_logging(service="test", queue=True, handlers=[CaptureHandler()], json=True)
    logging.getLogger("test.flush").info("must survive shutdown")

    shutdown_logging()
    assert "must survive shutdown" in captured


def test_shutdown_logging_is_idempotent_and_safe_without_queue_mode() -> None:
    setup_logging(service="test")
    shutdown_logging()
    shutdown_logging()


def test_the_forktex_logger_carries_a_null_handler() -> None:
    handlers = logging.getLogger("forktex").handlers
    assert any(isinstance(h, logging.NullHandler) for h in handlers)


def test_importing_the_library_does_not_touch_the_root_logger() -> None:
    import importlib

    root = logging.getLogger()
    root.handlers.clear()
    importlib.reload(importlib.import_module("forktex.log"))
    assert root.handlers == []


def test_context_filter_is_public_and_populates_records_without_setup_logging() -> None:
    from forktex.log import ContextFilter, trace_context

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    handler.addFilter(ContextFilter(service="embedded"))
    logger = logging.getLogger("embedder.test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        with trace_context("EMB-1"):
            logger.info("hello")
    finally:
        logger.removeHandler(handler)

    assert records[0].trace_id == "EMB-1"
    assert records[0].service == "embedded"
    assert records[0].run_id
