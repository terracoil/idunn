"""Utility layer: cross-cutting helpers with no internal dependencies."""

from .environment import Environment
from .meta_singleton import MetaSingleton
from .qualified_name import QualifiedName

__all__ = [
  'Environment',
  'MetaSingleton',
  'QualifiedName',
]
