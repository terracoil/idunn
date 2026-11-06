# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Poetry project, in-project `.venv`, with `poetry.lock` committed. `bin/devtool` (a Freyja CLI, run
as `poetry run bin/devtool ...`) wraps the same commands and also handles tagging and publishing.
It finds the repo root from its own path (`REPO_ROOT`), so it works from any directory, and
`build clean` empties `tmp/` except the `venv-*` directories and `.gitkeep` (never `tmp/` itself)
and removes a symlink as a link, never following it to what lies outside the repo.
`bin/devtool test lint` runs `ruff check`, `ruff format --check` and mypy, every step even after
one fails, and exits non-zero if any did; `--fix` rewrites instead of reporting, `--skip-mypy` and
`--clean` (clear Ruff's cache) do what they say. `bin/devtool test all|unit|integration` runs
pytest, where `integration` selects the `integration` marker and `unit` everything else, and each
exits non-zero when tests fail. `test all` lints first, then runs the suite twice:
`poetry run pytest` on the project interpreter, then
`tmp/venv-3.14/bin/python -m pytest` on the newest installed non-free-threaded pyenv 3.14.x (it
runs `pyenv install 3.14` if there is none, rebuilds the venv when its interpreter differs, and
reinstalls the project, `pytest` and the dev group's other `pytest*` plugins when `pyproject.toml`
changes). That second run is what un-skips the two PEP 649 tests in
`tests/test_invert_contract.py`. `-k`, `-sv` and `-n` go to both runs (`-n` is pytest-xdist, in
the dev group), coverage to the poetry run only, and lint and each run print separate verdicts.
`pytest-timeout` (dev group, `timeout = 120` in pyproject, above the examples' 60 s subprocess
limit) fails any test still running after two minutes: the net for a hang `Racer` cannot see, such
as a busy-spin on the main thread, under `-n` too.

```bash
poetry install --with dev
poetry run pytest
poetry run pytest tests/test_invert.py -k <name>       # one test
poetry run ruff format --check . && poetry run ruff check .   # to fix: drop --check, add --fix
poetry run mypy                                        # strict; covers idunn/, tests/, examples/
poetry check --lock                                    # pyproject valid, lock in step with it
poetry build
poetry run python -m examples.classy.simple.main       # the README's my_app; see examples/*/*/
IDUNN_ENV=prod poetry run python -m examples.classy.complex.main   # the shop, one env per run
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
| `idunn/internal/` | `InversionMapper`, `InversionResolver`, `SingletonGeneration`, `InversionValidator`, `ConstructionStack`, `ConstructorPlanner`, `LazyPlan`, `AutoDiscovery`, `BootstrapGate`, `BootstrapGeneration`, `BootstrapFlight`, `ReportMerger`, `DecoratorSupport`, `PortRegistry` | domain, util |
| `idunn/domain/` | frozen dataclasses (`AdapterDeclaration`, `AdapterMetadata`, `Catalog`, `EngineSnapshot`, `FunctionShape`, `InvertDeclaration`, `ParameterPlan`, `PortBinding`), the `SlotKey` alias, `LifecycleEnum`, `ReportMap` TypedDict, the `IdunnError` hierarchy | util |
| `idunn/util/` | `Environment`, `ImportContext`, `KeyedLocks`, `MetaSingleton`, `QualifiedName` | nothing internal |
| `idunn/testing/` | `__init__.py` only: re-exports `Harness` from `app` | app |

No modules may live at `idunn/` root besides `__init__.py`. Cross-package imports go through each
layer's `__init__.py` re-exports (e.g. `from idunn.domain import ...`), never module paths.
`test_architecture.py` also rejects, inside `idunn/`, `..` relatives, module paths and the root
barrel (`from idunn import app` would otherwise slip a back edge past the matrix), and any module
import cycle in `idunn/` or `examples/` (Tarjan over module-level edges, barrels included).
`testing` is a public barrel, not a layer of its own: no layer lists it in `ALLOWED`, so production
code (Idunn's own included) never imports `idunn.testing`, and `test_testing_holds_only_its_barrel`
keeps the implementation in `app/harness.py`, beside the facade hooks it uses.
`InversionValidator`, `ConstructionStack`, `SingletonGeneration`, `BootstrapGeneration`,
`BootstrapFlight` and `ReportMerger` are intentionally *not* re-exported from `idunn.internal`: only
their siblings use them.

### Public surface

`idunn/__init__.py` exports exactly: the three decorators, `Idunn`, `LifecycleEnum`, the `ReportMap`
TypedDict returned by discovery, and the seven `IdunnError` classes. `idunn/testing/__init__.py`
exports exactly `Harness`, and the root does not re-export it. `tests/test_public_surface.py` pins
both sets, so changing either means changing that test. The engine classes are never public.

### Key invariants

- **Decorators only attach metadata; nothing is constructed until an `@Invert`-decorated `__init__`
  or function runs.** `@Port` records the Protocol in `PortRegistry` (a `WeakSet` keyed by class
  identity) and makes it `runtime_checkable`; `@Adapter` stamps a frozen `AdapterDeclaration` on
  the class as `__idunn_adapter__` (`AdapterDeclaration.attach`, read back by `of` from the class's
  own `__dict__` only, mirroring `InvertDeclaration`); `@Invert` plans and wraps; `autodiscover()`
  only imports modules and registers. `@Adapter` refuses a class that already holds a declaration
  of its own (stacked decorators raise `InvalidAdapterError`); a decorated subclass is fine, and an
  undecorated one is no adapter to discovery or to `Harness.install` (`InvalidAdapterError`).
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
  one `register_batch`; `override(port, instance, *, key=None)` checks the port
  (`InvalidPortError`), the key (`TypeError`) and the instance (`InvalidAdapterError`) up front,
  then answers that `(port, key)` ahead of selection in every environment, with no adapter needed, a
  caller-supplied argument still winning. Each block calls `Idunn()._snapshot()` on entry and
  `_restore()` on exit through the private hooks `_snapshot`, `_restore`, `_install` and
  `_override`; the snapshot holds the environment, the catalog and overrides by reference (both
  immutable), and read-only copies of the singletons and bootstrap's reports and carried runs. Each
  part's `restore` takes exactly what its `snapshot` returned (the facade unpacks the
  `EngineSnapshot`, so `internal` never sees it). Restores install fresh copies as whole new
  generations (a `SingletonGeneration` of `dict(instances)` and fresh `KeyedLocks`, a new
  `BootstrapGeneration`), exactly as `clear()` swaps, so a build racing a restore lands in the
  discarded one and no later write reaches a snapshot an outer block still needs. The resolver puts
  the overrides back before the generation: a resolve captures its generation once but reads
  overrides live, so the other order lets one starting mid-restore build a singleton against the
  departing fake into the restored generation. Blocks nest LIFO, and `Harness` enforces it: the open
  blocks' snapshots sit in its class-level `_blocks` stack, a block's depth is its token, and
  `_unwind` checks it before anything is restored. An outer block exiting first raises
  `RuntimeError` and leaves its depth in `_abandoned`; the inner block's exit then unwinds through
  it to the outer block's own snapshot, so neither block's wiring leaks. `_snapshot()` stays a pure
  read (tests probe with it), so the stack lives in `Harness`, and `reset()` leaves it alone: a
  block open across a reset still restores its own snapshot on exit. Plans survive a restore (they
  depend only on the class). The harness is process-wide: fine under xdist, not for
  thread-concurrent tests in one process.
- **`Idunn().bootstrap(root)` is `autodiscover` run once per root through `BootstrapGate`** (cache
  keyed by root only, so repeat calls ignore their options; failures are not cached). Libraries call
  it from their entry points instead of at import. Two rules keep it deadlock-free: no Idunn lock is
  held while importing (the gate's plain `Lock` guards bookkeeping only), and a thread that may hold
  an import lock never waits for another thread's discovery. A first call opens a `BootstrapFlight`.
  A call that finds one open waits on its `Event` and shares the cached report, unless its thread
  already has a run in the flight (re-entry: the flight's `runners` holds one thread ident per run
  in progress, so a finished owner, or a new thread that inherited its ident, waits like anyone
  else) or `ImportContext.active()` (an `importlib._bootstrap` frame on its stack); then it joins
  the flight, runs its own discovery and returns its own run's report. The last run out caches
  `ReportMerger.merge` of every successful run, which is exact because each class is new for exactly
  one atomic batch, so the cached report lists every class wherever a module put its `bootstrap`
  call. The owner returns that cached report, or the merge so far when a participant outlives it,
  which takes an import the owner never waits on (a module outside the root, or one its discovery
  excludes or skips). An owner failure caches nothing and wakes the waiters, who retry; the failed
  flight's successful runs carry over into the retry's flight, because their classes stay registered
  and no retry would list them as new. `reset()` clears the cache (so the conftest fixture isolates
  it) by swapping in a new generation, reports, flights and carried runs as one
  `BootstrapGeneration` (a `NamedTuple`); every run captures it once at entry, so a stale run lands
  in the discarded one.
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
  they fire at decoration on every version and never evaluate a hint: a mapped or keyed name must be
  a named parameter (not the instance slot, `*args` or `**kwargs`) and keyword-only, a second
  `@Invert` on one function raises, as do anything without a code object and a `staticmethod` or
  `classmethod` object, since `@Invert()` must sit beneath those (all `TypeError`).
  `Invert.__init__` refuses non-port map values (`InvalidPortError`) and non-`str` keys
  (`TypeError`; `isinstance`, so a `StrEnum` member counts, and `@Adapter(key=...)` and
  `Harness.override(key=...)` apply the same rule, so no adapter or stand-in sits on a key nobody
  can ask for). All three then keep the key as `DecoratorSupport.plain_key` returns it
  (`str.__str__`, not `str()`, which renders a `(str, Enum)` member as `Cls.NAME`), so an enum key
  is stored, matched and printed as its plain value. Annotation rules need `get_type_hints`: a map
  entry on a port-annotated parameter and a key on a non-port raise `InvalidPortError`, at
  decoration when the hints resolve, else at the first call (`LazyPlan` in the wrapper closure
  swallows only `NameError`, and never caches a failure). Port parameters are keyword-only, enforced
  at decoration (annotation-based checks at the first call if a hint is a forward reference;
  `TypeError`) and at call time: a call passing more positional arguments than
  `FunctionShape.positional_limit` raises `TypeError` before anything is injected, so ports arrive
  only by keyword and the wrapper reads them from `kwargs` alone. `ConstructorPlanner.plan` always
  applies the rule and `plan_adapter` only to a decorated constructor; it is not a toggle, since the
  wrappers depend on it. Undecorated adapter constructors are exempt, since the resolver passes
  every port by keyword.
  `@Invert(bootstrap=root)` (keyword-only, a non-empty `str`, else `TypeError` at decoration, kept
  via `plain_key`; every dotted part must then be an identifier, else `ValueError` naming it, both
  judged by `Invert._root` from the string alone, never imported or looked up then; `autodiscover`
  and `bootstrap` do not repeat the check) is frozen on `InvertDeclaration.bootstrap`, which the
  planner and the resolver ignore. Both wrappers run, in this order: positional-limit
  check, `lazy.get()`, then, if a root is set and any planned port is absent from `kwargs`
  (optional ones count), the public `Idunn().bootstrap(root)`, once, then inject. So a planning
  error or too many positionals raise before discovery, a failure leaves `self` untouched, and a
  caller supplying every port discovers nothing. `InversionResolver._build` passes every planned
  parameter by keyword, fallbacks included, so a dependency build never bootstraps under a
  singleton's lock; `test_invert_bootstrap.py` pins that. `bootstrap=` on a function with no port
  parameters raises `TypeError` from `LazyPlan._refuse_idle_bootstrap` (at decoration, or at each
  call behind a forward reference); that one method is the whole rule. `Idunn.bootstrap` reads
  `BootstrapGate.cached` first, so the warm path builds no `partial`.
- **Resolved instances are structurally checked** against the port (`isinstance` on the
  runtime-checkable Protocol) after construction; a mismatch raises `InvalidAdapterError`.
- **Each `SINGLETON` is built once per generation, under its own lock.** The warm path is one
  lock-free `dict.get`. A miss first runs the cycle walk (`_assert_acyclic`) holding nothing, then
  takes the adapter's `RLock` from `KeyedLocks` and checks the cache again inside it. The resolver's
  generation is a `SingletonGeneration` (`instances`, `locks`), read once in `inject` and passed
  down the whole recursion; `clear()` swaps in a new one, so a build racing `reset()` lands in the
  discarded dict. Locks are only taken along dependency edges, so acyclic graphs cannot invert and
  unrelated singletons never wait on each other; the walk takes cyclic graphs off the table before
  any lock is held. A singleton build publishes its stack, itself included, in a `ConstructionStack`
  (a `threading.local`) for the length of the build, and `inject` starts from that instead of `()`:
  an `@Invert()` consumer created inside the constructor continues the path, so a loop through it is
  an edge the walk and the stack check both see (U16), and worker threads start empty. Singleton
  builds only: publishing around every TRANSIENT build cost ~10% of a warm transient resolve, so a
  consumer built inside a transient constructor starts at the innermost singleton, which still
  covers every lock the thread holds. The lock stays an `RLock` as a backstop for same-thread
  re-entry, and it is never shared with `BootstrapGate`. Documented limits (ADVANCED,
  "Thread-safety, with fine print"): a constructor holds its lock while it runs, so one that imports
  modules or calls `bootstrap` can deadlock against a thread importing a module that needs the same
  singleton, and one that waits on a thread needing that singleton deadlocks outright. A loop made
  only of `TRANSIENT`s and closed by a consumer built inside one of their constructors is still a
  `RecursionError`; no lock is involved, so no hang.

### Resolution flow

`InversionResolver._inject` → `_choose`, the one selection rule (the `is_port` guard, then an
override, else `InversionMapper.find` over a copy-on-write `(port, key)` index filtered by
environment), returning the stand-in or the adapter to build; with neither, a tolerant parameter
gets its fallback and a required one raises `AdapterNotFoundError` (built by `_missing`) →
`_instance` (stack check, then the singleton cache) → `_build` fills the adapter's plan, a
`tuple[ParameterPlan, ...]` from `ConstructorPlanner.plan_adapter`, cached per adapter class in
`_plans` on first build (no lock: a racing duplicate is identical; failures are not cached;
`clear()` swaps in a new dict), each parameter through `_inject` again. Planning an adapter raises
`MissingTypeHintError` for any named parameter without a default that is not a port (annotated or
not), and `TypeError` for a positional-only port, since the resolver passes keywords; `*args` and
`**kwargs` are skipped, and a constructor with no code object (`object.__init__`) has nothing to
inject. A constructor hint that does not resolve (a port defined inside a function under `from
__future__ import annotations`) raises `MissingTypeHintError` from `_adapter_hints`, naming the
adapter, quoting the `NameError` (never `exc.name`, which a hint that calls something may leave
`None`) and chained from it; it is uncached like every planning failure, so the cycle walk, a
`Harness` install and a plain build all surface it alike and a later build succeeds once the name
exists. Only `@Invert` consumers defer (`LazyPlan`); an adapter cannot wait.
Re-entry into an adapter already on the construction stack raises `InjectionCycleError`.
`_overrides` is `None` outside a `Harness` block, so the warm path pays one identity test for the
whole override feature, and one `find` per parameter, tolerant or not. `TRANSIENT` (the default)
rebuilds every time. A `SINGLETON` is cached per adapter class in the captured generation; on a
miss, `_build_once` runs the cycle walk, then builds under the adapter's lock. The walk is a
depth-first dry run from the adapter (its path starts with the current stack, so its message names
the same `a -> b -> a` path) over the cached plans, choosing each edge through the build's own
`_choose`: an overridden `(port, key)` and a tolerant parameter with nothing active have no edge, a
singleton already built is a leaf, and a required parameter with no adapter halts the walk, because
the build raises `AdapterNotFoundError` there and never reaches anything beyond it. A `done` set
keeps it linear per miss. The construction-time stack check stays: it is what catches loops among
`TRANSIENT`s. `inject` seeds its stack from the thread's `ConstructionStack`, which a singleton
build publishes around itself, so a consumer built mid-build extends the path rather than starting a
new one.

The index is a frozen `Catalog` (domain) that the mapper replaces whole. Readers (`find`,
`bindings`, `catalog`) read `self._catalog` once and never lock, so `describe()` comes from one
snapshot. Every write is `register_batch` under the mapper's write lock: copy the catalog once,
skip classes already registered (or repeated in the batch), validate each new adapter against its
`(port, key)` slot only, and swap once; any error leaves the catalog untouched. There is no
one-at-a-time register: a batch costs one copy plus the slot sizes, so discovery is linear in the
classes found, while a loop of batches of one is quadratic (only `Wiring.register_adapter`, a test
seam, does that; anything that registers many classes must batch them). The write lock is a
plain `Lock` on purpose: a batch that re-entered registration would swap in a catalog built from a
stale copy and lose the inner update, so a deadlock is the louder, better failure. Validation
keeps at most one adapter per slot per environment, so there is no tie-breaker and no
registration order beyond the catalog's insertion order.

### Adapter selection and environments

Unkeyed adapters answer unkeyed resolution; keyed adapters are opt-in. Two adapters sharing a port
and key that are active in overlapping environments (either env-agnostic, or sharing an env name)
raise `InvalidAdapterError` at registration. `Environment.current` resolves the active env from
`Idunn().reset(environment=...)`, then `IDUNN_ENV`, then `local`; names are stripped, lowercased
with `_`→`-`, blank → `local`, validated against `[a-z0-9][a-z0-9.-]*`, and `..` is rejected; a
name that is not a `str` is a `ValueError` too. The
facade reads it only at first construction and on each `reset()`, so changing `IDUNN_ENV` later
has no effect until `reset()`.

### AutoDiscovery boundary

The facade builds one `AutoDiscovery(mapper)` beside the resolver in `__init__` and keeps it for
life; `reset()` empties the shared mapper in place, so explicit `bootstrap`,
`@Invert(bootstrap=...)` and repeated `autodiscover` calls all register a root once per reset
(`test_every_door_into_discovery_registers_a_root_once_per_reset`).
`Idunn().autodiscover(root)` takes a dotted name (never a module object) and imports every module
under `root` (the root included, namespace directories too), skipping `__main__` parts,
non-identifier parts, and test modules (`tests`, `test`, `test_*`, `*_test`, `conftest`) plus any
`exclude` patterns (`fnmatchcase` on each dotted part below the root; user patterns add to the
defaults). The module running as `__main__` is reused, never re-imported. All modules import first;
then one `register_batch` folds ports across the whole set before adapters, so a port first touched
by an adapter is still reported as a port. A class counts only in the module that defines it
(`__module__` filter, scanned via `vars()`); ports by `PortRegistry` identity, adapters by
`AdapterDeclaration.of` (the stamp in their *own* `__dict__`, the test `Harness.install` applies
too). `strict=True` raises `DiscoveryError` before
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
  `Wiring` (a standalone mapper + resolver; `Wiring.of(*adapters)` registers one batch) for
  resolution tests, `Resolve.port` to build one port through the facade's private door as a
  required `ParameterPlan`, `PackageWriter` for throwaway packages (as the `writer` fixture in
  `conftest.py`), `ImportingCall` to run a callable mid-import (from a loader, with no module-body
  frame), and `Racer`.
- Every thread a test starts goes through `Racer` (`_support.py`), never a bare `threading.Thread`
  (the subprocess drivers in `test_bootstrap.py` run in a child interpreter under a timeout and are
  the exception): daemon threads sharing one deadline, with a thread still alive after it recorded
  as a `TimeoutError`, so a deadlock fails the test instead of hanging the suite. `run` starts
  targets behind one barrier, `start`/`join` stagger them, with `results` and `raised` by thread
  name, and `call` runs one call that might hang, such as a bootstrap-gate call that a regression
  would otherwise park on the main thread. The `eager_switching` fixture in `conftest.py` sets
  `sys.setswitchinterval(1e-6)` for races that the GIL would otherwise hide. Run concurrency tests
  repeatedly (ten times per interpreter, 3.14 through `tmp/venv-3.14/bin/python -m pytest`) before
  calling them green. ADVANCED, "Maintainer notes", documents all of this for humans.
- Tests and `examples/` are type-checked under strict mypy; keep them fully annotated.
- Examples are `examples/{classy,functional}/{simple,complex}/`, each a package with a guarded
  `main.py`. `tests/test_examples.py` (integration) globs `examples/*/*/main.py` and reads two
  lines of each `__init__` docstring (from source, via `ast`). `Environments: a, b` names the
  runs: each in a scrubbed subprocess with `IDUNN_ENV=<name>` against `expected.<name>.txt`, except
  `unset`, which runs with no `IDUNN_ENV` against `expected.txt`; stdout must match exactly, and the
  `expected*.txt` files present must match the line exactly (a missing or extra file fails).
  `Registers: ports; adapters` lists classes by module-qualified name relative to the example
  package (`shop.till.Till`), and in-process discovery must report exactly those, so a class that
  moves module fails. A new example needs both lines and its expected files. The README's "Normal
  usage" `my_app` listings are `examples/classy/simple` minus module docstrings, with only the
  discovery root changed, and `test_readme_normal_usage_quotes_the_simple_example_file_for_file`
  holds them to it, so edit the example and the README together.
- Tests import public names from their home barrel exactly as users do (`idunn`, or `idunn.testing`
  for `Harness`), and so do the generated-module source strings that tests write to `tmp_path`.
  Non-public names come from the highest re-exporting layer package (`idunn.domain`,
  `idunn.internal`, `idunn.util`), never from a module path. `tests/test_public_surface.py`
  enforces this in `tests/` and `examples/` for `from idunn... import` statements (a public name
  from any barrel but its home, `from idunn.app import Harness` included, is flagged) and for plain
  `import idunn.x.y` module paths (`import idunn.internal`, a layer package, is fine). The import
  strings in `test_architecture.py` are `LayerProbe` fixtures and are exempt.

## Code style

Beyond the global Python rules: 2-space indent, 100-column lines, single quotes (Ruff format),
strict mypy, full type hints, single return point with guard clauses allowed. Behavior lives in
classes, including all three decorators. `Port.__new__` returns the decorated Protocol and carries
one `# type: ignore[misc]` because strict mypy requires `__new__` to return an instance. `Adapter`
and `Invert` are `__init__` + `__call__` classes, so `Invert` is always applied with parentheses:
`@Invert()`, never bare.

Ruff selects `B`, `D`, `E4/E7/E9`, `F`, `I`. Consequences: every public member in `idunn/` needs a
docstring (tests are exempt from `D100`–`D104` and `D107`; `D105`/`D106` still apply), and
`from x import *` is rejected (`F403`), so the global ">5 imports → `*`" heuristic does not apply
here. Use explicit imports plus `__all__`.