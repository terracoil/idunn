"""Entry point for the functional shop: discover the application, use the library, show the wiring.
The same shop as ``examples.classy.complex`` with every consumer a function. The application
discovers only its own ``shop`` package, the ``mead`` library bootstraps itself, and
``describe()`` at the end shows both. Run it under ``IDUNN_ENV=local`` and ``IDUNN_ENV=prod``.
"""

from idunn import Idunn, ReportMap

from .mead import pour
from .shop import open_stall, sell, take_stock

if __name__ == '__main__':
  report: ReportMap = Idunn().autodiscover('examples.functional.complex.shop')
  ports: int = len(report['registered_ports'])
  adapters: int = len(report['registered_adapters'])
  print(f'shop wired: {ports} ports, {adapters} adapters')
  print(open_stall('Idunn'))
  print(sell('Bragi', 2))
  print(sell('Freyja', 2))  # a new till for each call, but the same storeroom
  print(take_stock())
  print(pour('Thor'))
  print(pour('Loki'))  # this call's bootstrap is a cache hit
  print()
  print(Idunn().describe())
