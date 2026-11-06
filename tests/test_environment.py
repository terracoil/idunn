"""Environment resolution and validation: the legitimate-but-wrong env-name surface.
``Environment.normalize`` is where a user's bad ``reset(environment=...)`` / ``IDUNN_ENV``
input is caught. The ``_VALID_PATTERN`` already turns away path separators, so the only
traversal left for the extra guard is a ``..`` substring (e.g. ``a..b``).
"""

from __future__ import annotations

import time
from typing import Protocol

import pytest

from idunn import Adapter, Idunn, Port
from idunn.testing import Harness
from idunn.util import Environment, MetaSingleton

from _support import Racer, Resolve


@Port
class BasketPort(Protocol):
  def take(self) -> str: ...


@pytest.mark.parametrize(
  ('raw', 'normalized'),
  [('Prod_East', 'prod-east'), (' Prod_East ', 'prod-east'), ('1prod', '1prod')],
)
def test_normalize_strips_lowercases_and_hyphenates(raw: str, normalized: str) -> None:
  assert Environment.normalize(raw) == normalized


def test_blank_environment_falls_back_to_default() -> None:
  assert Environment.normalize('') == Environment.DEFAULT
  assert Environment.normalize('   ') == Environment.DEFAULT


@pytest.mark.parametrize('bad', ['bad name!', 'a/b', 'a\\b', '.leading', '_prod'])
def test_invalid_characters_raise_value_error(bad: str) -> None:
  # '_prod' becomes '-prod' first, and a name may not start with punctuation.
  with pytest.raises(ValueError, match='Unsupported Idunn environment'):
    Environment.normalize(bad)


def test_dot_dot_traversal_is_rejected() -> None:
  # 'a..b' passes the character pattern but trips the traversal guard.
  with pytest.raises(ValueError, match=r"Unsupported Idunn environment 'a\.\.b'\.$"):
    Environment.normalize('a..b')


def test_a_name_that_is_not_a_str_raises_value_error_through_every_door() -> None:
  # Not an AttributeError about `strip`: the docs promise ValueError for a bad name, and mean it.
  with pytest.raises(ValueError, match='Unsupported Idunn environment 5; a name must be a str'):
    Environment.normalize(5)  # type: ignore[arg-type]
  with pytest.raises(ValueError, match='a name must be a str'):
    Idunn().reset(environment=5)  # type: ignore[arg-type]
  with pytest.raises(ValueError, match='a name must be a str'):
    Adapter(BasketPort, envs={5})  # type: ignore[arg-type]


def test_a_bad_idunn_env_raises_at_reset(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv(Environment.ENV_VAR, 'BAD NAME')

  with pytest.raises(ValueError, match="Unsupported Idunn environment 'BAD NAME'"):
    Idunn().reset()


def test_adapter_envs_are_normalised_like_the_active_environment() -> None:
  # Otherwise envs={'Prod'} would never be active anywhere, and say nothing about it.
  @Adapter(BasketPort, envs={' Prod_East '})
  class EastBasket(BasketPort):
    def take(self) -> str:
      return 'east'

  Idunn().reset(environment='PROD-east')

  with Harness.install(EastBasket):
    assert Resolve.port(BasketPort).take() == 'east'


def test_current_reads_explicit_then_env_var_then_default(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  monkeypatch.delenv(Environment.ENV_VAR, raising=False)
  assert Environment.current().name == Environment.DEFAULT

  monkeypatch.setenv(Environment.ENV_VAR, '')
  assert Environment.current().name == Environment.DEFAULT

  monkeypatch.setenv(Environment.ENV_VAR, 'Staging')
  assert Environment.current().name == 'staging'

  # An explicit argument always wins over the environment variable.
  assert Environment.current('Explicit').name == 'explicit'


def test_idunn_takes_no_arguments_even_once_it_exists() -> None:
  # An argument honored on first construction and ignored ever after is worse than none at all.
  assert Idunn() is Idunn()

  with pytest.raises(TypeError):
    Idunn(environment='prod')  # type: ignore[call-arg]
  with pytest.raises(TypeError):
    Idunn('prod')  # type: ignore[call-arg]

  assert Idunn().environment == 'local'


@pytest.mark.usefixtures('eager_switching')
def test_racing_first_calls_build_one_singleton() -> None:
  built: list[object] = []

  class Slow(metaclass=MetaSingleton):
    def __init__(self) -> None:
      time.sleep(0.01)  # holds the lock long enough for every other thread to queue behind it
      built.append(self)

  seen: list[Slow] = []
  racer = Racer(timeout=10)

  racer.run(*(lambda: seen.append(Slow()) for _ in range(8)))

  assert racer.errors == []
  assert len(built) == 1
  assert all(instance is built[0] for instance in seen)
