"""A small shop: Idunn sells golden apples, and a mead library down the road pours for her guests.
Shows, in one graph: several ports to a module; ``envs=`` picking the payment (a rune stick in
``local``, Andvari's gold in ``prod``); ``key=`` picking one of two heralds per parameter; a
``SINGLETON`` storeroom whose stock every ``TRANSIENT`` till shares; an adapter whose constructor
takes ports (``Till``); an optional port (``SagaPort | None``, a skald only ``local`` affords); an
explicit ``@Invert({...})`` map onto a narrower, non-port hint (``StockView``); keyword-only ports
throughout; a library sub-package (``mead``) whose consumer wires it on first use with
``@Invert(bootstrap=...)``; and ``describe()`` at the end.
Registers: mead.ports.BrewPort, shop.ports.CheckoutPort, shop.ports.HeraldPort,
  shop.ports.PaymentPort, shop.ports.SagaPort, shop.ports.StoreroomPort;
  mead.brewery.KvasirBrewery, shop.gjallarhorn_herald.GjallarhornHerald,
  shop.gold_coffer_payment.GoldCofferPayment, shop.raven_herald.RavenHerald,
  shop.rune_tally_payment.RuneTallyPayment, shop.skald_saga.SkaldSaga, shop.storeroom.Storeroom,
  shop.till.Till
Environments: local, prod
Run from the repo root, once per environment, and compare:
``IDUNN_ENV=local poetry run python -m examples.classy.complex.main`` and the same with ``prod``.
"""
