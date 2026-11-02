"""``ImportContext``: is an ``import`` in progress on this thread's stack?
The bootstrap gate bets the process on the answer: a thread mid-import that waits for another
thread's discovery can deadlock, so these pin both the yes cases and the no cases.
"""

import importlib
from pathlib import Path
from threading import Thread

import pytest
from idunn.util import ImportContext

from _support import ImportingCall, PackageWriter


def test_inactive_in_a_plain_call() -> None:
  assert ImportContext.active() is False


def test_inactive_in_a_thread_target() -> None:
  seen: list[bool] = []
  thread = Thread(target=lambda: seen.append(ImportContext.active()), daemon=True)

  thread.start()
  thread.join(timeout=10)

  assert seen == [False]


def test_active_in_a_module_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  PackageWriter(tmp_path=tmp_path, monkeypatch=monkeypatch).module(
    'import_context_body',
    """
    from idunn.util import ImportContext

    SEEN = ImportContext.active()
    """,
  )

  module = importlib.import_module('import_context_body')

  assert module.SEEN is True


def test_active_in_a_loaders_exec_module_with_no_module_body_frame() -> None:
  with ImportingCall('import_context_loader', ImportContext.active).installed() as call:
    assert call.run() is True


def test_active_in_a_thread_that_is_importing() -> None:
  seen: list[object] = []
  with ImportingCall('import_context_thread', ImportContext.active).installed() as call:
    thread = Thread(target=lambda: seen.append(call.run()), daemon=True)
    thread.start()
    thread.join(timeout=10)

  assert seen == [True]
