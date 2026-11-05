"""Tell whether the current thread is somewhere inside an ``import``."""

from __future__ import annotations

import inspect
from types import FrameType
from typing import Final


class ImportContext:
  """Answers "might this thread be holding a module import lock right now?".
  Whenever ``importlib`` holds a module's lock, an ``importlib._bootstrap`` frame sits on the stack,
  module bodies and loaders' ``exec_module`` alike (C-extension init included), so one frame walk
  answers it. The converse is looser, which only costs a spare discovery. A thread that says yes
  must never wait on another thread's import work: that other thread may need the very lock this
  one is sitting on, and Python's own deadlock detector cannot see a cycle that runs through
  somebody else's lock.
  """

  # The frozen bootstrap keeps this filename even under ``-X frozen_modules=off``.
  BOOTSTRAP_FILENAME: Final[str] = '<frozen importlib._bootstrap>'

  @classmethod
  def active(cls) -> bool:
    """Return ``True`` if an import is in progress on this thread's stack.
    An interpreter without frame support gets ``True``: wrongly saying yes costs a duplicate
    discovery, while wrongly saying no can cost the process.
    """
    frame: FrameType | None = inspect.currentframe()
    found: bool = frame is None
    while frame is not None and not found:
      found = frame.f_code.co_filename == cls.BOOTSTRAP_FILENAME
      frame = frame.f_back
    return found
