"""Entry point for the shop: discover the application, use the library, then show the wiring.
The application discovers only its own ``shop`` package. The ``mead`` library next door is left to
bootstrap itself, as a library installed from PyPI would, and ``describe()`` at the end shows both
in one graph. Run it under ``IDUNN_ENV=local`` and ``IDUNN_ENV=prod`` and compare the receipts.
"""

from idunn import Idunn, ReportMap

from .mead import MeadHall
from .shop import Stall, Stocktaker

if __name__ == '__main__':
  report: ReportMap = Idunn().autodiscover('examples.classy.complex.shop')
  ports: int = len(report['registered_ports'])
  adapters: int = len(report['registered_adapters'])
  print(f'shop wired: {ports} ports, {adapters} adapters')
  stall: Stall = Stall('Idunn')
  print(stall.open())
  print(stall.sell('Bragi', 2))
  print(Stall('Idunn').sell('Freyja', 2))  # a new stall and a new till, but the same storeroom
  print(Stocktaker().report())
  print(MeadHall().pour('Thor'))
  print(MeadHall().pour('Loki'))  # this hall's cupbearer finds the library already wired
  print()
  print(Idunn().describe())
