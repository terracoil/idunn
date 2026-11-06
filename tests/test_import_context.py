"""``ImportContext``: is an ``import`` in progress on this thread's stack?
The bootstrap gate bets the process on the answer: a thread mid-import that waits for another
thread's discovery can deadlock, so these pin both the yes cases and the no cases.
"""

import importlib
import inspect

import pytest

from idunn.util import ImportContext

from _support import ImportingCall, PackageWriter, Racer


def test_inactive_in_a_plain_call() -> None:
  assert ImportContext.active() is False


def test_inactive_in_a_thread_target() -> None:
  assert Racer(timeout=10).call(ImportContext.active) is False


def test_active_in_a_module_body(writer: PackageWriter) -> None:
  writer.module(
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
  with ImportingCall('import_context_thread', ImportContext.active).installed() as call:
    assert Racer(timeout=10).call(call.run) is True


def test_active_when_the_interpreter_has_no_frames_to_walk(monkeypatch: pytest.MonkeyPatch) -> None:
  # The one monkeypatch there is: a frameless interpreter cannot be had any other way. Saying
  # yes costs a spare discovery; saying no could cost the process, so yes it is.
  monkeypatch.setattr(inspect, 'currentframe', lambda: None)

  assert ImportContext.active() is True
