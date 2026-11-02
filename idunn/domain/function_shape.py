"""A function's parameter layout, read from its code object so no annotation is ever evaluated."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import CodeType, MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class FunctionShape:
  """Names, kinds and defaults of a function's parameters, and whether it is a constructor.
  Read from ``__code__``, ``__defaults__`` and ``__kwdefaults__`` only. ``inspect.signature``
  evaluates annotations on Python 3.14, so it raises ``NameError`` on a forward reference; the code
  object never does, which is what lets the shape rules run at decoration on every version.

  ``constructor`` is decided by the name in the function's own ``def`` (``co_name``, not the
  attribute it is stored under): ``__init__`` means the first positional slot is the instance, to
  be skipped and assigned to. Anything else (a plain function, a method, a static method) has no
  such slot that Idunn cares about.
  """

  constructor: bool
  positional: tuple[str, ...]  # positional-only first, then positional-or-keyword; self included
  positional_only: tuple[str, ...]
  keyword_only: tuple[str, ...]
  var_positional: bool
  defaults: Mapping[str, Any]

  @property
  def caller_positional(self) -> tuple[str, ...]:
    """The positional parameters a caller's positional arguments fill, in order."""
    return self.positional[1:] if self.constructor else self.positional

  @property
  def named(self) -> tuple[str, ...]:
    """Every parameter that could be a port: no instance slot, no ``*args``, no ``**kwargs``."""
    return (*self.caller_positional, *self.keyword_only)

  @classmethod
  def of(cls, function: Callable[..., Any]) -> FunctionShape | None:
    """Return ``function``'s shape, or ``None`` when it has no code object (a class, a builtin).
    ``functools.wraps`` chains are followed to the innermost function, as ``inspect`` does.
    """
    original: Any = inspect.unwrap(function)
    code: object = getattr(original, '__code__', None)
    return cls._from_code(code, original) if isinstance(code, CodeType) else None

  @property
  def positional_limit(self) -> int | None:
    """How many positional arguments a caller may pass, or ``None`` when ``*args`` takes any."""
    return None if self.var_positional else len(self.caller_positional)

  @classmethod
  def _from_code(cls, code: CodeType, original: Any) -> FunctionShape:
    positional: tuple[str, ...] = code.co_varnames[: code.co_argcount]
    keyword_only: tuple[str, ...] = code.co_varnames[
      code.co_argcount : code.co_argcount + code.co_kwonlyargcount
    ]
    # __defaults__ lines up with the *last* positional parameters; keyword-only ones have a dict.
    positional_defaults: tuple[Any, ...] = getattr(original, '__defaults__', None) or ()
    defaulted: tuple[str, ...] = positional[len(positional) - len(positional_defaults) :]
    return cls(
      constructor=code.co_name == '__init__',
      positional=positional,
      positional_only=positional[: code.co_posonlyargcount],
      keyword_only=keyword_only,
      var_positional=bool(code.co_flags & inspect.CO_VARARGS),
      defaults=MappingProxyType(
        {
          **dict(zip(defaulted, positional_defaults, strict=True)),
          **(getattr(original, '__kwdefaults__', None) or {}),
        }
      ),
    )
