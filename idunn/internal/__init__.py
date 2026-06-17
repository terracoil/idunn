"""Internal layer: discovery and decorator-support helpers.

These are re-exported for intra-package sibling imports (e.g. ``idunn.app``); they are **not** part of
Idunn's public API — ``idunn/__init__`` deliberately does not expose them.
"""

from .auto_discovery import AutoDiscovery
from .decorator_support import DecoratorSupport

__all__ = ['AutoDiscovery', 'DecoratorSupport']
