"""Render a class as a fully-qualified ``module.QualName`` string."""

from __future__ import annotations

from typing import Any


class QualifiedName:
  """Stateless helper that turns a class into ``module.QualName``.
  Strings rather than class objects keep ``ReportMap`` a plain dict and ``describe()`` readable.
  """

  @staticmethod
  def of(obj: type[Any]) -> str:
    """Return ``obj``'s module-qualified name."""
    return f'{obj.__module__}.{obj.__qualname__}'
