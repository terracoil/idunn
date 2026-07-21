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


@Port
class AnvilPort(Protocol):
  def clang(self) -> str: ...


@Adapter(AnvilPort, envs={'test', 'prod'})
class RemoteAnvil(AnvilPort):
  def clang(self) -> str:
    return 'clang'


@Port
class BellPort(Protocol):
  def ring(self) -> str: ...


@Adapter(BellPort)
class PlainBell(BellPort):
  def ring(self) -> str:
    return 'ding'


@Adapter(BellPort, key='silver')
class SilverBell(BellPort):
  def ring(self) -> str:
    return 'ting'


@Port
class LampPort(Protocol):
  def glow(self) -> str: ...


@Adapter(LampPort, envs={'prod'})
class ProdLamp(LampPort):
  def glow(self) -> str:
    return 'prod'


@Adapter(LampPort, envs={'local'})
class LocalLamp(LampPort):
  def glow(self) -> str:
    return 'local'


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


def test_describe_empty_registry_is_header_only() -> None:
  assert Idunn().describe() == 'Environment: local'


def test_describe_renders_concrete_env_label_sorted() -> None:
  Container.install(RemoteAnvil)
  text = Idunn().describe()
  assert 'envs=prod,test' in text


def test_describe_lists_all_adapters_for_a_port_in_order() -> None:
  Container.install(PlainBell, SilverBell)
  text = Idunn().describe()
  assert f'  selected: {PlainBell.__module__}.PlainBell' in text
  assert f'- {PlainBell.__module__}.PlainBell' in text
  assert f'- {SilverBell.__module__}.SilverBell' in text
  assert text.index('.PlainBell key=') < text.index('.SilverBell key=')


def test_describe_sorts_multiple_ports_by_qualified_name() -> None:
  # Install reverse-alphabetically to prove the output is sorted, not registration-ordered.
  Container.install(PlainBell, RemoteAnvil)
  text = Idunn().describe()
  assert text.index('AnvilPort') < text.index('BellPort')


def test_describe_reflects_active_environment_selection() -> None:
  Container.install(ProdLamp, LocalLamp)
  text = Idunn().describe()
  assert f'  selected: {LocalLamp.__module__}.LocalLamp' in text
  assert f'  selected: {ProdLamp.__module__}.ProdLamp' not in text
