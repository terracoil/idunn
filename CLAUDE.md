# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Poetry project, in-project `.venv`, with `poetry.lock` committed. `bin/devtool` (a Freyja CLI) wraps
the same commands and also handles tagging and publishing; `bin/devtool test all|unit|integration`
runs pytest, where `integration` selects the `integration` marker and `unit` everything else.

```bash
poetry install --with dev
poetry run pytest
poetry run pytest tests/test_invert.py -k <name>       # one test
poetry run ruff format --check . && poetry run ruff check .   # to fix: drop --check, add --fix
poetry run mypy                                        # strict; covers idunn/, tests/, examples/
poetry check --lock                                    # pyproject valid, lock in step with it
poetry build
poetry run python -m examples.my_app.main             # runnable example (the README's my_app layout)
```

CI (`.github/workflows/ci.yml`) has two jobs. `quality` runs once on 3.13.16: `poetry check --lock`,
format check, lint and mypy. `test` runs pytest on Python 3.11, 3.12, 3.13.16 and 3.14. Users get
`requires-python = ">=3.11,<4.0"`; development happens on 3.13.16 (the in-project `.venv`). mypy
(`python_version = "3.11"`) and Ruff (`target-version = "py311"`) target the floor, so 3.12+-only
syntax and APIs are rejected. Keep the classifiers and the CI matrix in step with the floor, and
re-lock (`poetry lock`) after any dependency edit, or the quality job fails. Pytest, Ruff and mypy
caches live under the git-ignored `tmp/`.

## Architecture

Idunn is a constructor-time IoC toolkit: **Port → Adapter → `@Invert` consumer**, with a process-wide
`Idunn` singleton facade in front of a small engine.

### Layers (enforced by `tests/test_architecture.py`)

| Layer | Holds | May import |
|-------|-------|------------|
| `idunn/app/` | `Port` (`port.py`), `Adapter` (`adapter.py`), `Invert` (`invert.py`), `Idunn` facade (`idunn.py`) | anything |
| `idunn/internal/` | `InversionMapper`, `InversionResolver`, `InversionValidator`, `AutoDiscovery`, `BootstrapGate`, `BootstrapFlight`, `ReportMerger`, `DecoratorSupport`, `PortRegistry` | domain, util |
| `idunn/domain/` | frozen dataclasses (`AdapterDeclaration`, `AdapterMetadata`, `Catalog`, `PortBinding`), `LifecycleEnum`, `ReportMap` TypedDict, the `IdunnError` hierarchy | util |
| `idunn/util/` | `Environment`, `ImportContext`, `MetaSingleton`, `QualifiedName` | nothing internal |

No modules may live at `idunn/` root besides `__init__.py`. Cross-package imports go through each
layer's `__init__.py` re-exports (e.g. `from idunn.domain import ...`), never module paths.
`InversionValidator`, `BootstrapFlight` and `ReportMerger` are intentionally *not* re-exported from
`idunn.internal`: only their siblings use them.

### Public surface

`idunn/__init__.py` exports exactly: the three decorators, `Idunn`, `LifecycleEnum`, the `ReportMap`
TypedDict returned by discovery, and the seven `IdunnError` classes. `tests/test_public_surface.py`
pins this set, so changing it means changing that test. The engine classes are never public.

### Key invariants

- **Decorators only attach metadata; nothing is constructed until an `@Invert`-decorated `__init__`
  runs.** `@Port` records the Protocol in `PortRegistry` (a `WeakSet` keyed by class identity) and
  makes it `runtime_checkable`; `@Adapter` stores a frozen `AdapterDeclaration` on the class;
  `autodiscover()` only imports modules and registers. `@Adapter` refuses a class whose own
  `__dict__` already holds a declaration (stacked decorators raise `InvalidAdapterError`); a
  decorated subclass is fine.
- **Error messages name things through `QualifiedName.of`**, which renders a class or function as
  `module.QualName` and anything else, parameterized aliases such as `Repo[User]` included, as its
  `repr`. So `Port(5)` raises `InvalidPortError` rather than an `AttributeError` from the message
  itself. Never format `__qualname__`, or a class's `repr`, into a message directly.
- **`Idunn()` takes no arguments**, and neither does `MetaSingleton.__call__`: a singleton argument
  would count once and be ignored after. The environment comes from `IDUNN_ENV` or
  `reset(environment=...)`.
- **Only the exact decorated class is a port; subclasses are not.** Nothing is written into the
  Protocol's namespace, because Python 3.11 counts every attribute there as a protocol member and
  structural adapters would then fail `isinstance`. So an adapter that subclasses its port, or an
  undecorated Protocol that extends one, is not a port (`@Adapter(...)` and resolution raise
  `InvalidPortError`). `Port.__new__` still reads the private `typing` flag `_is_protocol`, because
  the public `typing.is_protocol` is 3.13+ and the floor is 3.11.
- **There is no public `resolve()` or `register()`.** `@Invert` reaches the engine through the private
  `Idunn()._inject` / `Idunn()._has`. This removal is deliberate (`docs/ADVANCED.md`); do not add one.
- **`Idunn().bootstrap(root)` is `autodiscover` run once per root through `BootstrapGate`** (cache
  keyed by root only, so repeat calls ignore their options; failures are not cached). Libraries
  call it from their entry points instead of at import. Two rules keep it deadlock-free: no Idunn
  lock is held while importing (the gate's plain `Lock` guards bookkeeping only), and a thread that
  may hold an import lock never waits for another thread's discovery. A first call opens a
  `BootstrapFlight`. A call that finds one open waits on its `Event` and shares the cached report,
  unless its thread already has a run in the flight (re-entry: the flight's `runners` holds one
  thread ident per run in progress, so a finished owner, or a new thread that inherited its ident,
  waits like anyone else) or `ImportContext.active()` (an `importlib._bootstrap` frame on its
  stack); then it joins the flight, runs its own discovery and returns its own run's report. The
  last run out caches `ReportMerger.merge` of every successful run, which is exact because each
  class is new for exactly one atomic batch, so the cached report lists every class wherever a
  module put its `bootstrap` call. The owner returns that cached report, or the merge so far when a
  participant outlives it, which takes an import the owner never waits on (a module outside the
  root, or one its discovery excludes or skips). An owner failure caches nothing and wakes the
  waiters, who retry; the failed flight's successful runs carry over into the retry's flight,
  because their classes stay registered and no retry would list them as new. `reset()` clears the
  cache (so the conftest fixture isolates it) by swapping in a new generation, reports, flights and
  carried runs as one tuple; every run captures it once at entry, so a stale run lands in the
  discarded one.
- **Keys apply only at `@Invert` consumers.** `@Invert(keys={'param': 'name'})` selects a keyed
  adapter for that parameter. When the resolver recursively builds an adapter's own constructor
  dependencies it always resolves unkeyed (`key=None`), so keyed adapters never satisfy
  adapter-to-adapter dependencies.
- **Optional dependencies** are a parameter typed `Port | None` or any `@Port` parameter with a
  default: a missing adapter yields the default/`None` instead of `AdapterNotFoundError`. The
  annotation→port logic is shared (`DecoratorSupport.port_from_annotation`), so `@Invert` consumers
  and adapter constructors behave identically.
- **`@Invert` details.** It assigns `self.<name>` for every port parameter, injected or
  caller-supplied, before the body runs. A port annotation beats an explicit `@Invert({...})` entry
  for the same parameter (`{**explicit, **discovered}`). Arguments bind with `bind_partial`, so a
  positional plain argument lands in a port parameter if one comes first.
- **Resolved instances are structurally checked** against the port (`isinstance` on the
  runtime-checkable Protocol) after construction; a mismatch raises `InvalidAdapterError`.

### Resolution flow

`InversionResolver._resolve` → `InversionMapper.select` (a copy-on-write `(port, key)` index,
filtered by environment) → `_construct` inspects the adapter's `__init__` and recursively resolves
each `@Port`-typed parameter. Any parameter without a default that is not a `@Port` (annotated or
not) raises `MissingTypeHintError`; `*args`/`**kwargs` are skipped; re-entry into an adapter
already on the construction stack raises `InjectionCycleError`. `SINGLETON` adapters are cached per
adapter class; `TRANSIENT` (the default) rebuild every time.

The index is a frozen `Catalog` (domain) that the mapper replaces whole. Readers (`find`, `select`,
`bindings`, `ports`) read `self._catalog` once and never lock, so `describe()` comes from one
snapshot. Every write is `register_batch` under the mapper's write lock: copy the catalog once,
skip classes already registered (or repeated in the batch), validate each new adapter against its
`(port, key)` slot only, and swap once; any error leaves the catalog untouched. `register_port`
and `register_adapter` are batches of one. A batch costs one copy plus the slot sizes, so discovery
is linear in the classes found, while a loop of single registrations is quadratic (only `Wiring`
and tests do that; anything that registers many classes must batch them). The write lock is a
plain `Lock` on purpose: a batch that re-entered registration would swap in a catalog built from a
stale copy and lose the inner update, so a deadlock is the louder, better failure. Validation
keeps at most one adapter per slot per environment, so there is no tie-breaker and no
registration order beyond the catalog's insertion order.

### Adapter selection and environments

Unkeyed adapters answer unkeyed resolution; keyed adapters are opt-in. Two adapters sharing a port
and key that are active in overlapping environments (either env-agnostic, or sharing an env name)
raise `InvalidAdapterError` at registration. `Environment.current` resolves the active env from
`Idunn().reset(environment=...)`, then `IDUNN_ENV`, then `local`; names are stripped, lowercased
with `_`→`-`, blank → `local`, validated against `[a-z0-9][a-z0-9.-]*`, and `..` is rejected. The
facade reads it only at first construction and on each `reset()`, so changing `IDUNN_ENV` later
has no effect until `reset()`.

### AutoDiscovery boundary

`Idunn().autodiscover(root)` takes a dotted name (never a module object) and imports every module
under `root` (the root included, namespace directories too), skipping `__main__` parts,
non-identifier parts, and test modules (`tests`, `test`, `test_*`, `*_test`, `conftest`) plus any
`exclude` patterns (`fnmatchcase` on each dotted part below the root; user patterns add to the
defaults). The module running as `__main__` is reused, never re-imported. All modules import first;
then one `register_batch` folds ports across the whole set before adapters, so a port first touched
by an adapter is still reported as a port. A class counts only in the module that defines it
(`__module__` filter, scanned via `vars()`); ports by `PortRegistry` identity, adapters by
`__idunn_adapter__` in their *own* `__dict__`. `strict=True` raises `DiscoveryError` before
anything registers; `strict=False` lists the module in `skipped_modules`; the root's own import
errors propagate unwrapped regardless of `strict`. A root `__path__` entry that is not a directory
(a zip) raises `DiscoveryError` before any submodule imports, whatever `strict` says. Registration
is atomic: each run validates one batch and swaps the catalog once, so an `InvalidAdapterError`
leaves the catalog untouched. The return value is a public `ReportMap` TypedDict of strings whose
key set is pinned in `tests/test_public_surface.py`; its `registered_*` tuples list only classes
newly registered by that call.

## Testing conventions

- `tests/conftest.py` has an autouse fixture that calls `Idunn().reset(environment='local')` before
  and after every test; rely on it rather than resetting by hand.
- Because the facade has no register/resolve, engine tests use the seams in `tests/_support.py`:
  `Wiring` (a standalone mapper + resolver) for resolution tests, and `Container.install(...)` to push
  adapters into the singleton, as one batch, for `@Invert` integration tests.
- Tests and `examples/` are type-checked under strict mypy; keep them fully annotated.
- Tests import public names from `idunn` exactly as users do, and so do the generated-module source
  strings that tests write to `tmp_path`. Non-public names come from the highest re-exporting layer
  package (`idunn.domain`, `idunn.internal`, `idunn.util`), never from a module path.
  `tests/test_public_surface.py` enforces this in `tests/` and `examples/` for `from idunn...
  import` statements and for plain `import idunn.x.y` module paths (`import idunn.internal`, a
  layer package, is fine). The import strings in `test_architecture.py` are `LayerProbe` fixtures
  and are exempt.

## Code style

Beyond the global Python rules: 2-space indent, 100-column lines, single quotes (Ruff format), strict
mypy, full type hints, single return point with guard clauses allowed. Behavior lives in classes, including all
three decorators. `Port.__new__` returns the decorated Protocol and carries one `# type: ignore[misc]`
because strict mypy requires `__new__` to return an instance. `Adapter` and `Invert` are `__init__` +
`__call__` classes, so `Invert` is always applied with parentheses: `@Invert()`, never bare.

Ruff selects `B`, `D`, `E4/E7/E9`, `F`, `I`. Consequences: every public member in `idunn/` needs a
docstring (tests are exempt from `D100`–`D104` and `D107`; `D105`/`D106` still apply), and
`from x import *` is rejected (`F403`), so the global ">5 imports → `*`" heuristic does not apply
here. Use explicit imports plus `__all__`.