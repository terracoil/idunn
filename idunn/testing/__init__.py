"""Test tooling: :class:`Harness`, for wiring fakes into one block and leaving no trace behind.
Kept out of the root package on purpose. Production code has no business installing adapters by
hand, and ``tests/test_architecture.py`` makes sure none of Idunn's own layers import this one.
"""

from idunn.app import Harness

__all__ = ['Harness']
