"""The entire public surface must be reachable from the top-level ``idunn`` package."""

import idunn

EXPECTED_PUBLIC_NAMES = {
  'Adapter',
  'AdapterNotFoundError',
  'DiscoveryError',
  'Idunn',
  'IdunnError',
  'InjectionCycleError',
  'InvalidAdapterError',
  'InvalidPortError',
  'Invert',
  'LifecycleEnum',
  'MissingTypeHintError',
  'Port',
}


def test_public_surface_matches_all() -> None:
  assert set(idunn.__all__) == EXPECTED_PUBLIC_NAMES


def test_public_names_are_importable() -> None:
  missing = [name for name in EXPECTED_PUBLIC_NAMES if not hasattr(idunn, name)]
  assert not missing, f'missing from idunn: {missing}'
