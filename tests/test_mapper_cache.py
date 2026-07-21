"""InversionMapper selection cache: per-environment scoping and invalidation on mutation.

Note: ``_active_candidates`` sorts its matches by ``order``, but ``validate_registration``
forbids two adapters sharing ``(port, key)`` in overlapping environments, so any
``(port, key, environment)`` slot yields 0 or 1 candidate — the multi-candidate ``sorted``
is defensive and structurally unreachable, hence not exercised here.
"""

from typing import Protocol

import pytest
from idunn import AdapterNotFoundError, InvalidAdapterError
from idunn.app import Adapter, Port
from idunn.internal import InversionMapper


@Port
class GreeterPort(Protocol):
  def hello(self) -> str: ...


@Adapter(GreeterPort, envs={'prod'})
class ProdGreeter(GreeterPort):
  def hello(self) -> str:
    return 'prod'


@Adapter(GreeterPort, envs={'test'})
class SandboxGreeter(GreeterPort):
  def hello(self) -> str:
    return 'test'


@Adapter(GreeterPort, key='gold')
class GoldGreeter(GreeterPort):
  def hello(self) -> str:
    return 'gold'


@Adapter(GreeterPort)
class AnyGreeter(GreeterPort):
  def hello(self) -> str:
    return 'any'


class PlainGreeter:
  """An undecorated class — never marked with @Adapter."""

  def hello(self) -> str:
    return 'plain'


def test_selection_is_scoped_per_environment() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(ProdGreeter)
  mapper.register_adapter(SandboxGreeter)

  prod = mapper.select(port=GreeterPort, key=None, environment='prod')
  test = mapper.select(port=GreeterPort, key=None, environment='test')

  assert prod.adapter is ProdGreeter
  assert test.adapter is SandboxGreeter


def test_repeated_find_is_cached() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(ProdGreeter)

  first = mapper.find(port=GreeterPort, key=None, environment='prod')
  second = mapper.find(port=GreeterPort, key=None, environment='prod')

  assert first is second is not None


def test_registration_invalidates_a_cached_miss() -> None:
  mapper = InversionMapper()
  # Cache a miss for 'prod', then register an adapter and prove the miss was invalidated.
  assert mapper.find(port=GreeterPort, key=None, environment='prod') is None

  mapper.register_adapter(ProdGreeter)

  selected = mapper.select(port=GreeterPort, key=None, environment='prod')
  assert selected.adapter is ProdGreeter


def test_keyed_and_unkeyed_share_no_cache_slot() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)
  mapper.register_adapter(GoldGreeter)

  unkeyed = mapper.find(port=GreeterPort, key=None, environment='local')
  keyed = mapper.find(port=GreeterPort, key='gold', environment='local')

  assert unkeyed is not None and unkeyed.adapter is AnyGreeter
  assert keyed is not None and keyed.adapter is GoldGreeter
  # caching one key must not poison the other
  assert mapper.find(port=GreeterPort, key=None, environment='local') is unkeyed


def test_registration_invalidates_a_cached_hit() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)
  # Cache a successful unkeyed selection, then add a keyed adapter for the same port.
  hit = mapper.find(port=GreeterPort, key=None, environment='local')
  assert hit is not None and hit.adapter is AnyGreeter

  mapper.register_adapter(GoldGreeter)

  # The cache was rebuilt: the newly registered keyed adapter is now findable.
  keyed = mapper.find(port=GreeterPort, key='gold', environment='local')
  assert keyed is not None and keyed.adapter is GoldGreeter


def test_env_agnostic_adapter_cached_per_environment() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)

  local = mapper.find(port=GreeterPort, key=None, environment='local')
  prod = mapper.find(port=GreeterPort, key=None, environment='prod')
  test = mapper.find(port=GreeterPort, key=None, environment='test')

  # Each environment is a distinct cache entry pointing at the same metadata.
  assert local is not None
  assert local is prod is test
  assert local.adapter is AnyGreeter


def test_clear_empties_cache_and_resets_dirty() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)
  mapper.find(port=GreeterPort, key=None, environment='local')  # populate the cache

  mapper.clear()

  assert mapper._selection_cache == {}
  assert mapper.ports == frozenset()
  # A fresh registration after clear() resolves cleanly.
  mapper.register_adapter(ProdGreeter)
  again = mapper.find(port=GreeterPort, key=None, environment='prod')
  assert again is not None and again.adapter is ProdGreeter


def test_idempotent_reregistration_returns_false() -> None:
  mapper = InversionMapper()

  assert mapper.register_adapter(ProdGreeter) is True
  assert mapper.register_adapter(ProdGreeter) is False
  assert mapper.ports == frozenset({GreeterPort})


def test_select_raises_with_and_without_key_message() -> None:
  mapper = InversionMapper()

  with pytest.raises(AdapterNotFoundError) as unkeyed:
    mapper.select(port=GreeterPort, key=None, environment='local')
  with pytest.raises(AdapterNotFoundError) as keyed:
    mapper.select(port=GreeterPort, key='nope', environment='local')

  assert 'with key' not in str(unkeyed.value)
  assert "with key 'nope'" in str(keyed.value)


def test_register_adapter_on_undecorated_class_raises() -> None:
  mapper = InversionMapper()

  with pytest.raises(InvalidAdapterError):
    mapper.register_adapter(PlainGreeter)
