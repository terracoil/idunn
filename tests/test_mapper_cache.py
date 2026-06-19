"""InversionMapper selection cache: per-environment scoping and invalidation on mutation."""

from typing import Protocol

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
