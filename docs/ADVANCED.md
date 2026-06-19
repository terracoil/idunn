# Idunn — Advanced & Power-User Notes 🔧
![Idunn](https://github.com/terracoil/idunn/blob/master/docs/images/idunn.png)

The [README](../README.md) covers the whole everyday API: the three decorators (`@Port`,
`@Adapter`, `@Invert`) plus the single `Idunn().autodiscover(...)` bootstrap. This document collects
the rarely-needed corners — how resolution actually fires, how to inspect the wired graph, manual
registration, test isolation, and the features Idunn deliberately omits.

> Everything here is reachable, but none of it belongs in normal application code. If you find
> yourself using these in business logic, step back: the decorators are almost always enough.

## When does resolution happen? ⏳

Decorators do **not** construct anything. `@Port` and `@Adapter` only attach metadata; `@Invert`
only wraps a constructor. `autodiscover()` imports the bounded modules so the decorators have run,
finds the decorated classes, and registers them — it constructs nothing either. Apples get
*catalogued* at discovery; they only get *picked* at construction.

Construction fires when you build an `@Invert`-decorated object:

```python
feast = Feast(other="funky")      # @Invert resolves Feast's @Port parameters, then runs __init__
```

At that moment Idunn:

1. selects the active adapter for each `@Port`-typed parameter;
2. inspects that adapter's constructor;
3. recursively resolves *its* `@Port` parameters (a `Port | None` or defaulted port param is
   optional — a missing adapter yields the default/`None`);
4. instantiates dependencies first, then the adapter;
5. caches `SINGLETON` instances, rebuilds `TRANSIENT` ones each time;
6. assigns each resolved value to `self.<name>` on the consumer.

Dependency order is handled at resolution time, not registration time. If `FeastAdapter` depends on
`AppleBasketPort`, Idunn resolves `AppleBasketPort` first, even if `FeastAdapter` was registered
first. Registration order is not destiny.

## Inspecting the wired graph — `describe()` 📒

`Idunn().describe()` renders a readable snapshot of the active port→adapter bindings for the current
environment. It is built from the same structured map the resolver uses to select adapters, so what
it prints is exactly what an unkeyed resolve would pick.

```python
from idunn import Idunn

Idunn().autodiscover("my_app")
print(Idunn().describe())
```

Example output:

```text
Environment: test

my_app.ports.PaymentPort
  selected: my_app.adapters.fake.FakePaymentAdapter
  - my_app.adapters.stripe.StripePaymentAdapter key=None envs=prod singleton
  - my_app.adapters.fake.FakePaymentAdapter key=None envs=ci,test
```

The `selected:` line is the adapter an unkeyed resolve returns in the active environment; a port
whose adapters are *all* keyed shows `selected: <none>` — by design, nothing answers an unkeyed
resolve there.

## Manual registration (instead of autodiscovery) 🔩

`autodiscover()` is built on a registration primitive that you can, in principle, drive yourself —
but it is **not** part of the public facade. The supported way to register adapters is
`autodiscover()`. If you have an unusual setup (e.g. adapters defined outside any discoverable
`ports`/`adapters` module), structure them into a small discoverable package and point
`autodiscover` at it rather than registering by hand.

```python
# Preferred: let discovery do it.
Idunn().autodiscover("my_app")

# Tests that define adapters inline drive the internal engine directly — see tests/_support.py.
```

## Test isolation 🧪

`Idunn` is a process-wide singleton, so tests must reset it between cases. `reset()` keeps the same
object identity but empties all registrations and cached instances, and rebinds the environment:

```python
import pytest
from idunn import Idunn


@pytest.fixture(autouse=True)
def _reset_idunn():
    Idunn().reset(environment="local")
    yield
    Idunn().reset(environment="local")
```

`reset(environment=...)` resolves the active environment from its argument, then `IDUNN_ENV`, then
the `local` default. Anything still clutching a reference across a reset finds the basket suddenly
empty.

For engine-level tests that need to register adapters defined inside a test function (where
`autodiscover` cannot reach them) or to resolve a bare port directly, drive the internal
`InversionMapper` / `InversionResolver` — see `tests/_support.py` in the repo for the `Wiring` and
`Container` helpers used by Idunn's own suite.

## Why there is no public `resolve()` 🚫

Earlier sketches of Idunn exposed `Idunn().resolve(Port)`. It was removed from the public surface on
purpose: resolving a port by hand is a *non-standard* way to start a graph and invites container code
to leak into business logic. The sanctioned trigger is constructing an `@Invert`-decorated object —
your entry point — and letting the graph wire itself. Resolution still happens internally (it is how
`@Invert` does its work); it just isn't an API you call.

## Deliberate non-features 🧱

These look like gaps but are intentional constraints. Documented here so you don't go hunting:

- **No lifecycle on `@Invert`.** Lifecycle (`SINGLETON`/`TRANSIENT`) is a property of the *provider*
  (`@Adapter`), the single source of truth for a binding. A consumer cannot request a different
  scope than its adapter declares.
- **No priority / fallback ordering.** The only disambiguators are `key` and `envs`. Two unkeyed
  adapters active in overlapping environments raise `InvalidAdapterError` rather than letting one win
  by some priority — Idunn fails loud rather than guessing.
- **No value / configuration injection.** `@Invert` injects only `@Port`-typed parameters. Plain
  config values (strings, ints, settings objects) are passed by the caller, not the container.
- **No field or setter injection.** Constructor-time only.
- **No multi-container support, no thread safety.** One process-wide container; wire on one thread at
  startup, then resolve.

## Class catalog 🗂️

For a class-by-class map of the package — public vs. internal, passive vs. active — see
[`docs/classes.md`](./classes.md).
