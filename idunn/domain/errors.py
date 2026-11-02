"""The Idunn exception family: one ``except IdunnError`` catches everything Idunn means to raise.
Every message names classes as ``module.QualName``, because ``Feast`` alone could be anyone's.
"""


class IdunnError(Exception):
  """Base of every Idunn error, so callers can catch the family once rather than six times."""


class InvalidPortError(IdunnError):
  """Raised when something that is not a ``@Port`` is asked to act like one.
  That covers ``@Port`` on anything but a Protocol (``Port(5)`` included), ``@Adapter`` naming
  an unmarked port, and resolving a non-port, for example through an explicit ``@Invert({...})``
  entry.
  """


class InvalidAdapterError(IdunnError):
  """Raised when an adapter cannot be trusted with its port.
  That covers ``@Adapter`` on a non-class, ``@Adapter`` applied twice to one class, two adapters
  sharing a port and key in overlapping environments, and a built instance that does not satisfy
  its port.
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
  """Raised when constructor resolution loops back to an adapter that is still being built."""
