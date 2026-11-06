"""``QualifiedName.of``: every error message names its culprit through it, whatever it was handed.
A class or function gets ``module.QualName``. Anything else gets its ``repr``, and so does a
parameterized alias, whose borrowed origin name would point at the wrong thing.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

import pytest

from idunn.util import QualifiedName

T_co = TypeVar('T_co', covariant=True)


class Repo(Protocol[T_co]):
  def get(self) -> T_co: ...


class User:
  """A plain class to parameterize ``Repo`` with."""

  def greet(self) -> str:
    """Say hello; a method's qualified name is as good as any class's."""
    return 'hello'


@pytest.mark.parametrize(
  ('obj', 'expected'),
  [
    (User, f'{__name__}.User'),
    (User.greet, f'{__name__}.User.greet'),
    (dict, 'builtins.dict'),
    (5, '5'),
    ('User', "'User'"),
    (None, 'None'),
    (list[str], 'list[str]'),
    (Repo[User], f'{__name__}.Repo[{__name__}.User]'),
    (User | None, f'{__name__}.User | None'),
  ],
)
def test_of_names_classes_in_full_and_everything_else_by_repr(obj: object, expected: str) -> None:
  assert QualifiedName.of(obj) == expected


def test_of_an_instance_uses_its_repr_not_its_class_name() -> None:
  # An instance inherits __module__ from its class but has no __qualname__ of its own.
  user = User()

  assert QualifiedName.of(user) == repr(user)
