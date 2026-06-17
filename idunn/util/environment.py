"""Environment resolution for Idunn."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Environment:
  """Resolves and validates the active Idunn environment."""

  name: str

  ENV_VAR = 'IDUNN_ENV'
  DEFAULT = 'local'
  _VALID_PATTERN = re.compile(r'[a-z0-9][a-z0-9.-]*')

  @classmethod
  def current(cls, environment: str | None = None) -> 'Environment':
    """Return the active Idunn environment."""
    raw_environment = environment if environment is not None else os.getenv(cls.ENV_VAR)
    if raw_environment is None:
      raw_environment = cls.DEFAULT
    return cls(cls.normalize(raw_environment))

  @classmethod
  def normalize(cls, environment: str) -> str:
    """Normalize an environment name for decorator matching."""
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
