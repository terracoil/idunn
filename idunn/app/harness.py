"""``Harness``: test wiring that cleans up after itself, published as ``idunn.testing.Harness``."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, ClassVar

from idunn.domain import EngineSnapshot

from .idunn import Idunn


class Harness:
  """Install adapters or stand in for a port for one ``with`` block, or one decorated test.
  The facade has no public register, so that business code cannot wire itself; tests still need
  to, and this is how they do it without the wiring outliving the test. Each block snapshots the
  engine on entry (catalog, singletons, overrides, bootstrap reports, environment) and restores it
  on exit, error or not. So a singleton built against a fake goes when the fake goes, and a
  ``bootstrap`` run inside an install cannot leave a report vouching for registrations that were
  rolled back. Blocks nest and unwind last in, first out, and an outer block exiting before an
  inner one raises ``RuntimeError`` instead of restoring a picture the inner block would then
  overwrite with its own. Both methods also work as decorators, re-entering for every call. Like
  the container, a harness is process-wide: fine for one test at a time per process (xdist
  included), not for threads running tests side by side.
  Parameters are typed ``type[Any]`` and ``object`` because strict mypy will not accept a
  Protocol for ``type[T]``, and a test helper that fights the type checker is not much help.
  """

  # The snapshots of the open blocks, outermost first, so a block's depth is its token; and the
  # depths of blocks that exited out of turn, for the block inside them to unwind through.
  # `reset()` leaves both alone: a block open across a reset still owes its own snapshot back on
  # exit, and a block a test entered and never left merely makes the next one a floor higher.
  _blocks: ClassVar[list[EngineSnapshot]] = []
  _abandoned: ClassVar[set[int]] = set()

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
    Harness._blocks.append(engine._snapshot())
    depth: int = len(Harness._blocks)
    try:
      yield engine
    finally:
      engine._restore(Harness._unwind(depth))

  @staticmethod
  def _unwind(depth: int) -> EngineSnapshot:
    # The snapshot the block at `depth` must restore, checked before anything is restored. An outer
    # block leaving first raises and leaves its depth behind; the inner block's exit then unwinds
    # through it to the outer block's own snapshot. Restoring the inner one's would reinstall the
    # outer block's wiring, which would then outlive both blocks.
    blocks: list[EngineSnapshot] = Harness._blocks
    if depth != len(blocks):
      Harness._abandoned.add(depth)
      message: str = (
        f'Harness block {depth} of {len(blocks)} exited before the blocks inside it; blocks unwind '
        'last in, first out. Nothing was restored: the innermost block restores this one too '
        'when it exits.'
      )
      raise RuntimeError(message)
    floor: int = depth
    while floor - 1 in Harness._abandoned:
      floor -= 1
      Harness._abandoned.discard(floor)
    target: EngineSnapshot = blocks[floor - 1]
    del blocks[floor - 1 :]
    return target
