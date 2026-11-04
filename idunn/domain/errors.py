"""The Idunn exception family: one ``except IdunnError`` catches everything Idunn means to raise.
Every message names classes as ``module.QualName``, because ``Feast`` alone could be anyone's.
"""


class IdunnError(Exception):
  """Base of every Idunn error, so callers can catch the family once rather than six times."""


class InvalidPortError(IdunnError):
  """Raised when something that is not a ``@Port`` is asked to act like one.
  That covers ``@Port`` on anything but a Protocol (``Port(5)`` included), ``@Adapter`` naming
  an unmarked port, an ``@Invert({...})`` map value that is not a port, and resolving a non-port.
  It also covers the two ``@Invert`` contradictions about ports: a parameter both annotated with a
  port and mapped to one, and ``keys`` naming a parameter that is not a port. ``Harness.override``
  raises it too, before its block runs, when handed something that is not a port.
  """


class InvalidAdapterError(IdunnError):
  """Raised when an adapter cannot be trusted with its port.
  That covers ``@Adapter`` on a non-class, ``@Adapter`` applied twice to one class, two adapters
  sharing a port and key in overlapping environments (the batch that hits it, discovery's or
  ``Harness.install``'s, registers nothing), and a built instance or a ``Harness.override``
  stand-in that does not satisfy its port.
  """


class AdapterNotFoundError(IdunnError):
  """Raised when a required port has no active adapter in the current environment."""


class DiscoveryError(IdunnError):
  """Raised when a module below the discovery root fails to import and ``strict=True``.
  Also raised, whatever ``strict`` says, for a root package that does not live in directories (a
  zip, say), since discovery reads the file system. The root's own import errors are not wrapped:
  they propagate as-is.
  """


class MissingTypeHintError(IdunnError):
  """Raised when an adapter constructor parameter has no default and Idunn cannot supply it.
  The name undersells it: an annotation that is not a ``@Port`` counts as missing too.
  """


class InjectionCycleError(IdunnError):
  """Raised when constructor resolution loops back to an adapter that is still being built.
  A loop through a ``SINGLETON`` is caught by a dry walk before anything is built, so two threads
  racing one can never end up holding half of it each. A loop closed by an ``@Invert()`` consumer
  created inside a constructor during a singleton's build is caught too, once that consumer is
  made: it continues the build's path instead of starting a fresh one.
  """
