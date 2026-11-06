"""The simple example with no consumer class: an ``@Invert()`` function receives the basket.
The port and its adapter are still classes, since a Protocol needs something to satisfy it; the
consumer is a plain function whose port arrives as a keyword argument and is kept nowhere.
Registers: ports.AppleBasketPort; adapters.GoldenAppleBasketAdapter
Environments: unset
Run from the repo root with ``poetry run python -m examples.functional.simple.main``.
"""
