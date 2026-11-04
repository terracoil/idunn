"""A small shop: Idunn sells golden apples, and a mead library down the road pours for her guests.
Shows, in one graph: several ports to a module; ``envs=`` picking the payment (a rune stick in
``local``, Andvari's gold in ``prod``); ``key=`` picking one of two heralds per parameter; a
``SINGLETON`` storeroom whose stock every ``TRANSIENT`` till shares; an adapter whose constructor
takes ports (``Till``); an optional port (``SagaPort | None``, a skald only ``local`` affords); an
explicit ``@Invert({...})`` map onto a narrower, non-port hint (``StockView``); keyword-only ports
throughout; a library sub-package (``mead``) that calls ``bootstrap`` on its own root from its
entry point; and ``describe()`` at the end.
Registers: BrewPort, CheckoutPort, HeraldPort, PaymentPort, SagaPort, StoreroomPort;
  GjallarhornHerald, GoldCofferPayment, KvasirBrewery, RavenHerald, RuneTallyPayment, SkaldSaga,
  Storeroom, Till
Run from the repo root, once per environment, and compare:
``IDUNN_ENV=local poetry run python -m examples.classy.complex.main`` and the same with ``prod``.
"""
