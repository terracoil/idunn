"""Render anything as a fully-qualified ``module.QualName`` string, for reports and errors."""

from __future__ import annotations

from typing import get_origin


class QualifiedName:
  """Stateless helper that turns a class (or function) into ``module.QualName``.
  Strings rather than class objects keep ``ReportMap`` a plain dict and ``describe()`` readable.
  It accepts any object because error messages are built from whatever the user handed over, and
  an error message that raises ``AttributeError`` on ``Port(5)`` is a second bug, not a message.
  Parameterized aliases (``Repo[User]``, ``list[str]``, ``User | None``) fall back to ``repr``
  too: they lend out their origin's name, and "not marked with @Port: app.Repo" about a ``Repo``
  that is marked would send you looking in the wrong place.
  """

  @staticmethod
  def of(obj: object) -> str:
    """Return ``obj``'s module-qualified name, or its ``repr`` when it has no such name."""
    module: object = getattr(obj, '__module__', None)
    qualname: object = getattr(obj, '__qualname__', None)
    named: bool = isinstance(module, str) and isinstance(qualname, str) and get_origin(obj) is None
    return f'{module}.{qualname}' if named else repr(obj)
