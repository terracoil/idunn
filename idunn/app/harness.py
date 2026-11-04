"""``Harness``: test wiring that cleans up after itself, published as ``idunn.testing.Harness``."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from idunn.domain import EngineSnapshot

from .idunn import Idunn


class Harness:
  """Install adapters or stand in for a port for one ``with`` block, or one decorated test.
  The facade has no public register, so that business code cannot wire itself; tests still need
  to, and this is how they do it without the wiring outliving the test. Each block snapshots the
  engine on entry (catalog, singletons, overrides, bootstrap reports, environment) and restores it
  on exit, error or not. So a singleton built against a fake goes when the fake goes, and a
  ``bootstrap`` run inside an install cannot leave a report vouching for registrations that were
  rolled back. Blocks nest and unwind last in, first out. Both methods also work as decorators,
  re-entering for every call. Like the container, a harness is process-wide: fine for one test
  at a time per process (xdist included), not for threads running tests side by side.
  Parameters are typed ``type[Any]`` and ``object`` because strict mypy will not accept a
  Protocol for ``type[T]``, and a test helper that fights the type checker is not much help.
  """

  @staticmethod
  @contextmanager
  def install(*adapters: type[Any]) -> Iterator[None]:
    """Register ``adapters`` for the block, as one atomic batch, then forget them.
    A collision raises :class:`~idunn.InvalidAdapterError` before the block runs, with nothing
    registered: the same all-or-nothing batch discovery uses, so a test sees the error a real
    discovery of those classes would.
    """
    with Harness._restoring() as engine:
      engine._install(adapters)
      yield

  @staticmethod
  @contextmanager
  def override(port: type[Any], instance: object, *, key: str | None = None) -> Iterator[None]:
    """Resolve ``port`` (with ``key``) to ``instance`` for the block, ahead of any adapter.
    Works in every environment and with no adapter registered at all, wherever the port is
    injected: an ``@Invert`` consumer, another adapter's constructor, an optional parameter. A
    caller-supplied argument still wins, as it always does. Raises
    :class:`~idunn.InvalidPortError` if ``port`` is not a ``@Port`` and
    :class:`~idunn.InvalidAdapterError` if ``instance`` does not satisfy it, before the block runs.
    """
    with Harness._restoring() as engine:
      engine._override(port, instance, key=key)
      yield

  @staticmethod
  @contextmanager
  def _restoring() -> Iterator[Idunn]:
    # The undo behind both methods. The restore sits in `finally`, so a failed install or override
    # also lands here; that is a harmless no-op, since neither writes anything before it checks.
    engine: Idunn = Idunn()
    snapshot: EngineSnapshot = engine._snapshot()
    try:
      yield engine
    finally:
      engine._restore(snapshot)
