"""One generation of singletons: what ``InversionResolver.clear`` throws away whole."""

from __future__ import annotations

from typing import Any, NamedTuple

from idunn.util import KeyedLocks


class SingletonGeneration(NamedTuple):
  """The built ``SINGLETON`` instances and the per-adapter locks guarding their first builds.
  Swapped whole by ``clear()`` and ``restore()``, never emptied: a resolve captures one at entry
  and hands it down the recursion, so a build racing a reset lands in a generation nobody reads.
  A tuple because swapping one reference is atomic and swapping two is a race with extra steps.
  """

  instances: dict[type[Any], Any]  # built singletons, per adapter class
  locks: KeyedLocks[type[Any]]  # one RLock per adapter class, for its first build
