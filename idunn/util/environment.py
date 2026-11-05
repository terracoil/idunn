"""Environment names: where they come from and what counts as one."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Environment:
  """A validated environment name, plus the rules for finding and normalizing one."""

  name: str

  # ClassVar, not Final: on a dataclass a Final with a value is a field with a default.
  ENV_VAR: ClassVar[str] = 'IDUNN_ENV'
  DEFAULT: ClassVar[str] = 'local'
  _VALID_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r'[a-z0-9][a-z0-9.-]*')

  @classmethod
  def current(cls, environment: str | None = None) -> Environment:
    """Resolve an environment from the argument, then ``IDUNN_ENV``, then ``local``.
    The variable is read on every call, but the facade only calls this when ``Idunn()`` is first
    built and on ``reset()``. That is why changing ``IDUNN_ENV`` mid-run does nothing until the
    next reset.
    """
    return cls(
      cls.normalize(environment if environment is not None else os.getenv(cls.ENV_VAR, cls.DEFAULT))
    )

  @classmethod
  def normalize(cls, environment: str) -> str:
    """Normalize and validate a name from ``@Adapter(envs=...)``, ``reset()`` or ``IDUNN_ENV``.
    Names are stripped and lowercased, and ``_`` becomes ``-`` so ``My_Env`` and ``my-env`` are
    the same place; a blank name means ``local``. The pattern already turns away path separators,
    so the only traversal left to refuse is ``..``, in case a name ever ends up in a path. A name
    that is not a ``str`` at all is a ``ValueError`` too, rather than an ``AttributeError`` about
    ``strip`` that leaves the reader to work out which name was meant.
    """
    if not isinstance(environment, str):
      message: str = f'Unsupported Idunn environment {environment!r}; a name must be a str.'
      raise ValueError(message)
    normalized: str = environment.strip().lower().replace('_', '-')
    if not normalized:
      normalized = cls.DEFAULT
    if cls._VALID_PATTERN.fullmatch(normalized) is None:
      message = (
        f'Unsupported Idunn environment {environment!r}; use letters, digits, dots, '
        'or hyphens, and do not start with punctuation.'
      )
      raise ValueError(message)
    if '..' in normalized:
      message = f'Unsupported Idunn environment {environment!r}.'
      raise ValueError(message)
    return normalized
