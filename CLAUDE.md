# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Poetry project, in-project `.venv`, with `poetry.lock` committed. `bin/devtool` (a Freyja CLI, run
as `poetry run bin/devtool ...`) wraps the same commands and also handles tagging and publishing;
`bin/devtool test all|unit|integration` runs pytest, where `integration` selects the `integration`
marker and `unit` everything else, and each exits non-zero when tests fail. `test all` runs the
suite twice: `poetry run pytest` on the project interpreter, then
`tmp/venv-3.14/bin/python -m pytest` on the newest installed non-free-threaded pyenv 3.14.x (it
runs `pyenv install 3.14` if there is none, rebuilds the venv when its interpreter differs, and
reinstalls the project, `pytest` and the dev group's other `pytest*` plugins when `pyproject.toml`
changes). That second run is what un-skips the two PEP 649 tests in
`tests/test_invert_contract.py`. `-k`, `-sv` and `-n` go to both runs, coverage to the poetry run
only, and each run's verdict is printed separately.

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
caches live under the git-ignored `tmp/`, and so does `tmp/venv-3.14`, which is how the suite runs
on 3.14 locally (`bin/devtool test all`); a `tmp/venv-3.11` built the same way covers the floor.
Release notes live in `CHANGELOG.md` (Keep a Changelog, one entry per release, shipped in the
sdist); ADVANCED's "Releasing" notes link to it instead of repeating it.

## Architecture

Idunn is a constructor-time IoC toolkit: **Port → Adapter → `@Invert` consumer**, with a process-wide
`Idunn` singleton facade in front of a small engine.

### Layers (enforced by `tests/test_architecture.py`)

| Layer | Holds | May import |
|-------|-------|------------|
| `idunn/app/` | `Port` (`port.py`), `Adapter` (`adapter.py`), `Invert` (`invert.py`), `Idunn` facade (`idunn.py`), `Harness` (`harness.py`) | anything but `testing` |
| `idunn/internal/` | `InversionMapper`, `InversionResolver`, `InversionValidator`, `ConstructionStack`, `ConstructorPlanner`, `LazyPlan`, `AutoDiscovery`, `BootstrapGate`, `BootstrapFlight`, `ReportMerger`, `DecoratorSupport`, `PortRegistry` | domain, util |
| `idunn/domain/` | frozen dataclasses (`AdapterDeclaration`, `AdapterMetadata`, `Catalog`, `EngineSnapshot`, `FunctionShape`, `InvertDeclaration`, `ParameterPlan`, `PortBinding`), `LifecycleEnum`, `ReportMap` TypedDict, the `IdunnError` hierarchy | util |
| `idunn/util/` | `Environment`, `ImportContext`, `KeyedLocks`, `MetaSingleton`, `QualifiedName` | nothing internal |
| `idunn/testing/` | `__init__.py` only: re-exports `Harness` from `app` | app |

No modules may live at `idunn/` root besides `__init__.py`. Cross-package imports go through each
layer's `__init__.py` re-exports (e.g. `from idunn.domain import ...`), never module paths.
`testing` is a public barrel, not a layer of its own: no layer lists it in `ALLOWED`, so production
code (Idunn's own included) never imports `idunn.testing`, and `test_testing_holds_only_its_barrel`
keeps the implementation in `app/harness.py`, beside the facade hooks it uses.
`InversionValidator`, `ConstructionStack`, `BootstrapFlight` and `ReportMerger` are intentionally
*not* re-exported from `idunn.internal`: only their siblings use them.

### Public surface

`idunn/__init__.py` exports exactly: the three decorators, `Idunn`, `LifecycleEnum`, the `ReportMap`
TypedDict returned by discovery, and the seven `IdunnError` classes. `idunn/testing/__init__.py`
exports exactly `Harness`, and the root does not re-export it. `tests/test_public_surface.py` pins
both sets, so changing either means changing that test. The engine classes are never public.

### Key invariants

- **Decorators only attach metadata; nothing is constructed until an `@Invert`-decorated `__init__`
  or function runs.** `@Port` records the Protocol in `PortRegistry` (a `WeakSet` keyed by class
  identity) and makes it `runtime_checkable`; `@Adapter` stores a frozen `AdapterDeclaration` on
  the class; `@Invert` plans and wraps; `autodiscover()` only imports modules and registers.
  `@Adapter` refuses a class whose own `__dict__` already holds a declaration (stacked decorators
  raise `InvalidAdapterError`); a decorated subclass is fine.
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
- **There is no public `resolve()` or `register()`.** `@Invert` reaches the engine through one
  private door, `Idunn()._inject(parameter)`, which takes a `ParameterPlan` and leaves tolerance to
  the resolver; tests reach it through `Resolve.port` in `tests/_support.py`. Registration outside
  discovery is `idunn.testing.Harness.install` alone, and it is scoped (U9): one `with` block or one
  decorated call, undone on exit. This is deliberate (`docs/ADVANCED.md`); do not add a public
  `resolve`, or a register that outlives its block.
- **`Harness` blocks restore an `EngineSnapshot` on exit, error or not.** `install(*adapters)` is
  one `register_batch`; `override(port, instance, *, key=None)` checks the port (`InvalidPortError`)
  and the instance (`InvalidAdapterError`) up front, then answers that `(port, key)` ahead of
  selection in every environment, with no adapter needed, a caller-supplied argument still winning.
  Each block calls `Idunn()._snapshot()` on entry and `_restore()` on exit through the private hooks
  `_snapshot`, `_restore`, `_install` and `_override`; the snapshot holds the environment, the
  catalog and overrides by reference (both immutable), and read-only copies of the singletons and
  bootstrap's reports and carried runs. Restores install fresh copies as whole new generations
  (`(dict(instances), KeyedLocks())`, new gate maps), exactly as `clear()` swaps, so a build racing
  a restore lands in the discarded one and no later write reaches a snapshot an outer block still
  needs. The resolver puts the overrides back before the generation: a resolve captures its
  generation once but reads overrides live, so the other order lets one starting mid-restore build
  a singleton against the departing fake into the restored generation. Blocks nest LIFO. Plans
  survive a restore (they depend only on the class). The harness is process-wide: fine under
  xdist, not for thread-concurrent tests in one process.
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
- **Keys apply wherever `@Invert(keys=...)` decorates something**: a consumer's constructor, an
  adapter's constructor, or a function. The resolver honours an adapter constructor's own keys and
  explicit map (it reads the `InvertDeclaration` stamped on the wrapper as `__idunn_invert__`), so
  the wrapper then finds every port supplied. An undecorated or plain `@Invert()` adapter
  constructor resolves unkeyed, so a keyed adapter never sneaks into a constructor that did not ask
  for it by name.
- **Optional dependencies** are a parameter typed `Port | None` or any `@Port` parameter with a
  default: a missing adapter yields the default/`None` instead of `AdapterNotFoundError`. One
  planner (`ConstructorPlanner`, on `DecoratorSupport.port_from_annotation`) and one resolver path
  (`InversionResolver._inject`, behind `inject`) serve `@Invert` functions and adapter
  constructors alike, so they cannot disagree.
- **`@Invert` details.** Two forms, chosen by the function's own name (`__code__.co_name`): on an
  `__init__` it assigns `self.<name>` for every port parameter, injected or caller-supplied, before
  the body runs; on anything else (function, method, static method) it passes the ports as keyword
  arguments and assigns nothing anywhere. Shape rules come from `__code__` via `FunctionShape`, so
  they fire at decoration on every version and never evaluate a hint: a mapped or keyed name must
  be a named parameter (not the instance slot, `*args` or `**kwargs`) and keyword-only, a second
  `@Invert` on one function raises, as do anything without a code object and a `staticmethod` or
  `classmethod` object, since `@Invert()` must sit beneath those (all `TypeError`).
  `Invert.__init__` refuses non-port map values (`InvalidPortError`) and non-`str` keys
  (`TypeError`). Annotation rules need `get_type_hints`: a map entry on a port-annotated parameter
  and a key on a non-port raise `InvalidPortError`, at decoration when the hints resolve, else at
  the first call (`LazyPlan` in the wrapper closure swallows only `NameError`, and never caches a
  failure). Port parameters are keyword-only, enforced at decoration (annotation-based checks at
  the first call if a hint is a forward reference; `TypeError`) and at call time: a call passing
  more positional arguments than `FunctionShape.positional_limit` raises `TypeError` before
  anything is injected, so ports arrive only by keyword and the wrapper reads them from `kwargs`
  alone. `ConstructorPlanner.KEYWORD_ONLY_PORTS` is where the rule lives, not a toggle: the
  wrappers depend on it. Undecorated adapter constructors are exempt, since the resolver passes
  every port by keyword.
- **Resolved instances are structurally checked** against the port (`isinstance` on the
  runtime-checkable Protocol) after construction; a mismatch raises `InvalidAdapterError`.
- **Each `SINGLETON` is built once per generation, under its own lock.** The warm path is one
  lock-free `dict.get`. A miss first runs the cycle walk (`_assert_acyclic`) holding nothing, then
  takes the adapter's `RLock` from `KeyedLocks` and checks the cache again inside it. The resolver's
  generation is `(instances, locks)`, read once in `inject` and passed down the whole recursion;
  `clear()` swaps in a new one, so a build racing `reset()` lands in the discarded dict. Locks are
  only taken along dependency edges, so acyclic graphs cannot invert and unrelated singletons never
  wait on each other; the walk takes cyclic graphs off the table before any lock is held. A
  singleton build publishes its stack, itself included, in a `ConstructionStack` (a
  `threading.local`) for the length of the build, and `inject` starts from that instead of `()`:
  an `@Invert()` consumer created inside the constructor continues the path, so a loop through it
  is an edge the walk and the stack check both see (U16), and worker threads start empty.
  Singleton builds only: publishing around every TRANSIENT build cost ~10% of a warm transient
  resolve, so a consumer built inside a transient constructor starts at the innermost singleton,
  which still covers every lock the thread holds. The lock stays an `RLock` as a backstop for
  same-thread re-entry, and it is never shared with `BootstrapGate`.
  Documented limits (ADVANCED, "Thread-safety, with fine print"): a constructor holds its lock
  while it runs, so one that imports modules or calls `bootstrap` can deadlock against a thread
  importing a module that needs the same singleton, and one that waits on a thread needing that
  singleton deadlocks outright. A loop made only of `TRANSIENT`s and closed by a consumer built
  inside one of their constructors is still a `RecursionError`; no lock is involved, so no hang.

### Resolution flow

`InversionResolver._resolve` → `InversionMapper.select` (a copy-on-write `(port, key)` index,
filtered by environment) → `_build` fills the adapter's plan, a `tuple[ParameterPlan, ...]` from
`ConstructorPlanner.plan_adapter`, cached per adapter class in `_plans` on first build (no lock: a
racing duplicate is identical; failures are not cached; `clear()` swaps in a new dict), each
parameter through `_inject` and so recursively through `_resolve`. Planning an adapter raises
`MissingTypeHintError` for any named parameter without a default that is not a port (annotated or
not), and `TypeError` for a positional-only port, since the resolver passes keywords; `*args` and
`**kwargs` are skipped, and a constructor with no code object (`object.__init__`) has nothing to
inject. Re-entry into an adapter already on the construction stack raises `InjectionCycleError`. An
override is checked first in `_resolve`, right after the `is_port` guard (`_overrides` is `None`
outside a `Harness` block, so the warm path pays one identity test), and by `_inject`'s tolerance
check. `TRANSIENT` (the default) rebuilds every time. A `SINGLETON` is cached per adapter class in
the captured generation; on a miss, `_build_once` runs the cycle walk, then builds under the
adapter's lock. The walk is a depth-first dry run from the adapter (its path starts with the
current stack, so its message names the same `a -> b -> a` path) over the cached plans, following
exactly the build's selections: an overridden `(port, key)` and a tolerant parameter with nothing
active have no edge, a singleton already built is a leaf, and a required parameter with no adapter
halts the walk, because the build raises `AdapterNotFoundError` there and never reaches anything
beyond it. A `done` set keeps it linear per miss. The construction-time stack check stays: it is
what catches loops among `TRANSIENT`s. `inject` seeds its stack from the thread's
`ConstructionStack`, which a singleton build publishes around itself, so a consumer built mid-build
extends the path rather than starting a new one.

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
- `@Invert` integration tests install adapters with `idunn.testing.Harness`, exactly as users do:
  `with Harness.install(...):` (one batch, undone on exit), and `Harness.override(...)` for fakes.
  Because the facade has no register/resolve, engine tests use the seams in `tests/_support.py`:
  `Wiring` (a standalone mapper + resolver) for resolution tests, `Resolve.port` to build one port
  through the facade's private door as a required `ParameterPlan`, `PackageWriter` for throwaway
  packages, and `Racer`.
- Thread tests start their targets through `Racer` (`_support.py`): daemon threads behind one
  barrier, with a thread still alive after the timeout recorded as a `TimeoutError`, so a deadlock
  fails the test instead of hanging the suite. The `eager_switching` fixture in `conftest.py` sets
  `sys.setswitchinterval(1e-6)` for races that the GIL would otherwise hide. Run concurrency tests
  repeatedly (ten times per interpreter, 3.14 through `tmp/venv-3.14/bin/python -m pytest`) before
  calling them green. ADVANCED, "Maintainer notes", documents all of this for humans.
- Tests and `examples/` are type-checked under strict mypy; keep them fully annotated.
- Tests import public names from their home barrel exactly as users do (`idunn`, or `idunn.testing`
  for `Harness`), and so do the generated-module source strings that tests write to `tmp_path`.
  Non-public names come from the highest re-exporting layer package (`idunn.domain`,
  `idunn.internal`, `idunn.util`), never from a module path. `tests/test_public_surface.py`
  enforces this in `tests/` and `examples/` for `from idunn... import` statements (a public name
  from any barrel but its home, `from idunn.app import Harness` included, is flagged) and for plain
  `import idunn.x.y` module paths (`import idunn.internal`, a
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