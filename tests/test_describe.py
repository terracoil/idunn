"""Idunn.describe() renders the structured binding snapshot from the mapper."""

from typing import Protocol

from idunn import Adapter, Idunn, LifecycleEnum, Port

from _support import Container


@Port
class HornPort(Protocol):
  def blow(self) -> str: ...


@Adapter(HornPort, lifecycle=LifecycleEnum.SINGLETON)
class BrassHorn(HornPort):
  def blow(self) -> str:
    return 'parp'


@Port
class GongPort(Protocol):
  def strike(self) -> str: ...


@Adapter(GongPort, key='bronze')
class BronzeGong(GongPort):
  def strike(self) -> str:
    return 'bong'


def test_describe_shows_environment_selected_adapter_and_singleton_flag() -> None:
  Container.install(BrassHorn)
  text = Idunn().describe()
  assert 'Environment: local' in text
  assert 'HornPort' in text
  assert 'selected: ' in text and 'BrassHorn' in text
  assert 'singleton' in text


def test_describe_marks_a_keyed_only_port_as_none_selected() -> None:
  Container.install(BronzeGong)
  text = Idunn().describe()
  assert 'GongPort' in text
  assert 'selected: <none>' in text
  assert "key='bronze'" in text
