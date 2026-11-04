"""Each thread's construction stack during a ``SINGLETON`` build, for consumers built inside."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import local
from typing import Any


class ConstructionStack(local):
  """The adapters a thread is in the middle of building, published so ``inject`` can start there.
  An ``@Invert()`` consumer built inside a constructor enters through the facade's door with no
  stack of its own, so a loop through it used to be invisible: ``RecursionError`` on one thread,
  a deadlock across two. Reading the published stack turns that loop into an ordinary edge, seen
  by the cycle walk and the stack check alike. It is a thread-local, so a worker thread a
  constructor starts begins empty. The class-level default is what a thread reads before it has
  published anything: a plain attribute hit, where ``getattr`` with a default on a bare ``local``
  raised internally on every read and added a third to a warm singleton resolve.
  """

  current: tuple[type[Any], ...] = ()

  @contextmanager
  def publishing(self, stack: tuple[type[Any], ...]) -> Iterator[None]:
    """Publish ``stack`` for the block, then restore whatever was published before, error or not."""
    outer: tuple[type[Any], ...] = self.current
    self.current = stack
    try:
      yield
    finally:
      self.current = outer
