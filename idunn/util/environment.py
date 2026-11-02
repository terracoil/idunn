"""Environment names: where they come from and what counts as one."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Environment:
  """A validated environment name, plus the rules for finding and normalizing one."""

  name: str

  ENV_VAR = 'IDUNN_ENV'
  DEFAULT = 'local'
  _VALID_PATTERN = re.compile(r'[a-z0-9][a-z0-9.-]*')

  @classmethod
  def current(cls, environment: str | None = None) -> 'Environment':
    """Resolve an environment from the argument, then ``IDUNN_ENV``, then ``local``.
    The variable is read on every call, but the facade only calls this when ``Idunn()`` is first
    built and on ``reset()``. That is why changing ``IDUNN_ENV`` mid-run does nothing until the
    next reset.
    """
    raw_environment = environment if environment is not None else os.getenv(cls.ENV_VAR)
    if raw_environment is None:
      raw_environment = cls.DEFAULT
    return cls(cls.normalize(raw_environment))

  @classmethod
  def normalize(cls, environment: str) -> str:
    """Normalize and validate a name from ``@Adapter(envs=...)``, ``reset()`` or ``IDUNN_ENV``.
    Names are stripped and lowercased, and ``_`` becomes ``-`` so ``My_Env`` and ``my-env`` are
    the same place; a blank name means ``local``. The traversal check is purely defensive, in
    case a name ever ends up in a path. Only ``..`` can reach it, since the pattern already turns
    away separators; the separator tests stay as a second lock on a door that is already shut.
    """
    normalized = environment.strip().lower().replace('_', '-')
    if not normalized:
      normalized = cls.DEFAULT
    if cls._VALID_PATTERN.fullmatch(normalized) is None:
      message = (
        f'Unsupported Idunn environment {environment!r}; use letters, digits, dots, '
        'or hyphens, and do not start with punctuation.'
      )
      raise ValueError(message)
    if '/' in normalized or '\\' in normalized or '..' in normalized:
      message = f'Unsupported Idunn environment {environment!r}.'
      raise ValueError(message)
    return normalized
