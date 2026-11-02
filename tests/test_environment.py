"""Environment resolution and validation: the legitimate-but-wrong env-name surface.
``Environment.normalize`` is where a user's bad ``reset(environment=...)`` / ``IDUNN_ENV``
input is caught. The ``_VALID_PATTERN`` already turns away path separators, so the only
traversal left for the extra guard is a ``..`` substring (e.g. ``a..b``).
"""

from __future__ import annotations

import pytest
from idunn import Idunn
from idunn.util import Environment


def test_normalize_lowercases_and_hyphenates() -> None:
  assert Environment.normalize('Prod_East') == 'prod-east'


def test_blank_environment_falls_back_to_default() -> None:
  assert Environment.normalize('') == Environment.DEFAULT
  assert Environment.normalize('   ') == Environment.DEFAULT


def test_invalid_characters_raise_value_error() -> None:
  for bad in ('bad name!', 'a/b', 'a\\b', '.leading'):
    with pytest.raises(ValueError):
      Environment.normalize(bad)


def test_dot_dot_traversal_is_rejected() -> None:
  # 'a..b' passes the character pattern but trips the traversal guard.
  with pytest.raises(ValueError):
    Environment.normalize('a..b')


def test_current_reads_explicit_then_env_var_then_default(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  monkeypatch.delenv(Environment.ENV_VAR, raising=False)
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
