"""Idunn exception hierarchy."""


class IdunnError(Exception):
  """Base error for Idunn."""


class InvalidPortError(IdunnError):
  """Raised when @Port is applied to a non-Protocol class."""


class InvalidAdapterError(IdunnError):
  """Raised when an adapter registration is invalid."""


class AdapterNotFoundError(IdunnError):
  """Raised when no active adapter is registered for a requested port."""


class DiscoveryError(IdunnError):
  """Raised when Idunn autodiscovery fails."""


class MissingTypeHintError(IdunnError):
  """Raised when constructor injection needs a type hint that is missing."""


class InjectionCycleError(IdunnError):
  """Raised when constructor dependency resolution loops back on itself."""
