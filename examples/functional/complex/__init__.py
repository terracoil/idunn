"""The shop again, with every consumer a function: what ``@Invert()`` looks like without ``self``.
Port implementations are still classes, because a Protocol needs something to satisfy it, and
they are copies of the classes in ``examples.classy.complex``. Everything that consumes a port is a
function: ``envs=`` still picks the payment, ``key=`` still picks a herald per parameter, the
``SINGLETON`` storeroom still outlives every call, ``Till`` still takes ports in its constructor,
``SagaPort | None`` is still optional, the explicit map still fills a ``StockView``, ports are
keyword-only, and the ``mead`` library's consumer is a function wearing ``bootstrap=``.
Registers: mead.ports.BrewPort, shop.ports.CheckoutPort, shop.ports.HeraldPort,
  shop.ports.PaymentPort, shop.ports.SagaPort, shop.ports.StoreroomPort;
  mead.brewery.KvasirBrewery, shop.gjallarhorn_herald.GjallarhornHerald,
  shop.gold_coffer_payment.GoldCofferPayment, shop.raven_herald.RavenHerald,
  shop.rune_tally_payment.RuneTallyPayment, shop.skald_saga.SkaldSaga, shop.storeroom.Storeroom,
  shop.till.Till
Environments: local, prod
Run from the repo root, once per environment, and compare:
``IDUNN_ENV=local poetry run python -m examples.functional.complex.main`` and the same with
``prod``.
"""
