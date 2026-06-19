<!--
═══════════════════════════════════════════════════════════════════════════════
  🤖 CLAUDE — SELF-UPDATE RECIPE FOR THIS FILE  (docs/classes.md)
  Hidden from rendered Markdown; meant only for the agent maintaining this doc.

  TRIGGER. When the user says "update classes.md", "update the class catalog",
  "regenerate the catalog", or anything equivalent, follow this recipe top to
  bottom. Re-scan the source EVERY time — never hand-patch from memory, because
  the whole point of this file is that it tracks the code, not the other way around.

  STEP 1 — SCAN. Enumerate every class / Protocol / @dataclass / Enum / TypedDict /
    exception defined under idunn/ (all four layers: app/, domain/, internal/,
    util/) and under examples/. A quick sweep:
        grep -rn '^class \|^  class \|^    class ' idunn/ examples/
    Then read idunn/__init__.py (its __all__) to see what is actually exported.

  STEP 2 — CLASSIFY each class on two axes:
    • Audience:  🟢 Public  — in idunn/__init__.py __all__; meant to be used/caught.
                 🟡 Mixed   — exported only incidentally (e.g. leaks through
                              Idunn().adapters introspection), not a headline API.
                 🔴 Hidden  — internal plumbing; never imported by end users.
    • Nature:    📦 Passive — dataclass / enum / exception / TypedDict / Protocol
                              (holds shape, not behavior).
                 ⚙️ Active  — validates / resolves / scans / constructs / orchestrates.

  STEP 3 — GROUP into the sections below, keeping layer order app → domain →
    internal → util: Public API surface · Decorators · Definitions & metadata ·
    Exceptions · Engine & orchestration · Examples. Add or drop a section only if
    a whole area appears or disappears in the code.

  STEP 4 — COLUMNS per table: Class | Nature | Purpose | Audience | Splittable? |
    Generic utility?
    • Purpose      — one tight sentence: WHAT it does + any load-bearing invariant.
    • Splittable?  — only meaningful for 🟡 rows (how it could split public/hidden).
    • Generic utility? — ✅ when (part of) it is a reusable, project-agnostic helper.

  STEP 5 — SYNC CHECK against the previous version of this file:
    • new classes → add rows; removed classes → delete rows; renamed → rename.
    • if __all__ changed, re-derive every 🟢/🟡/🔴.
    • RE-READ the decorator signatures so Purpose text matches current params —
      e.g. @Adapter currently takes key / lifecycle / envs and has NO `default`.
    • spot-check the Examples section against examples/basic_usage.py specifically;
      it drifts most often (new demo classes get added there first).

  STEP 6 — Preserve the two legends and the "Reading the catalog" closing notes
    (refresh their wording if the splittable/reusable story actually changed), and
    KEEP THIS COMMENT BLOCK intact at the top so the next update is just as cheap.

  SOURCES OF TRUTH to verify against:
    idunn/__init__.py · idunn/app/decorators.py · idunn/app/idunn.py ·
    idunn/domain/* · idunn/internal/* · idunn/util/* · examples/basic_usage.py
═══════════════════════════════════════════════════════════════════════════════
-->

# 🍎 Idunn — Class & File Catalog

A map of every class defined in the live `idunn/` package and the runnable `examples/`. Use it to
tell at a glance what is part of the public contract, what is plumbing, and what could be tightened.
The package is split into four layers — `app/`, `domain/`, `internal/`, `util/` — and the import
directions between them are enforced by `tests/test_architecture.py`.

> *This file is self-maintaining: say "update classes.md" and Claude re-scans the source and
> regenerates it from the recipe embedded at the top.*

## 🔑 Legend

| Mark | Audience — *who is meant to see it* |
|------|-------------------------------------|
| 🟢 **Public** | Part of the intended end-user API; exported and meant to be used/caught directly. |
| 🟡 **Mixed**  | Currently exported, but incidental to the public story — leaks through introspection rather than being a headline API. The **Splittable** column says how it could be divided. |
| 🔴 **Hidden** | Internal plumbing; should never be seen or imported by end users. |

| Mark | Nature |
|------|--------|
| 📦 **Passive** | A *definition* — dataclass, enum, exception, TypedDict, or Protocol. Holds shape, not behavior. |
| ⚙️ **Active**  | *Does* something — validates, resolves, scans, constructs, orchestrates. |

- **Splittable?** — only meaningful for 🟡 rows: could the class be cleanly divided into a public
  surface and a hidden remainder?
- **Generic utility?** — ✅ when the class (or an extractable part of it) is a reusable,
  project-agnostic helper.

---

## 📦 Public API surface — `idunn/__init__.py`

`__init__.py` is the barrel that re-exports the public names in its `__all__` — the three decorators
(`Port`, `Adapter`, `Invert`), the `Idunn` facade, `LifecycleEnum`, and the full `IdunnError`
hierarchy. It contains no logic of its own — 🟢 Public, 📦 Passive. The hidden plumbing it does
**not** export: `InversionMapper`, `InversionResolver`, `InversionValidator`, `AutoDiscovery`,
`DecoratorSupport`, `MetaSingleton`, `Environment`, and the `PortBinding` snapshot type.

## ⚙️ Decorators — `app/decorators.py`

| Class / Symbol | Nature | Purpose | Audience | Splittable? | Generic utility? |
|----------------|--------|---------|----------|-------------|------------------|
| `Port` | ⚙️ Active | Marks a `typing.Protocol` as an injectable port: validates it really is a Protocol, sets `__idunn_port__`, and makes it `runtime_checkable`. | 🟢 Public | — | — |
| `Adapter` | ⚙️ Active | Decorator factory that declares a class as an adapter for a port, capturing `key`/`lifecycle`/`envs` into an `AdapterDeclaration`. Unkeyed adapters answer unkeyed resolution; keyed adapters are opt-in. Constructs nothing. | 🟢 Public | — | — |
| `Invert` | ⚙️ Active | Wraps a *consumer's* `__init__`: every `@Port`-typed parameter is resolved via the `Idunn()` facade at construction time and assigned to `self.<name>` (caller args override). Supports `keys=`, an explicit `{param: Port}` map, and **optional** deps (`Port \| None` or a defaulted param → default/`None` when no adapter). Delegates annotation→port resolution to `DecoratorSupport.port_from_annotation`. | 🟢 Public | — | — |

## 🧱 Definitions & metadata — `domain/`

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `lifecycle_enum.py` | `LifecycleEnum` | 📦 Passive | `StrEnum` of adapter lifecycles: `SINGLETON`, `TRANSIENT`. Passed by users to `@Adapter`. | 🟢 Public | — | — |
| `registration_key.py` | `RegistrationKey` | 📦 Passive | Frozen `(port, key)` pair used to group adapter bindings and as the `InversionMapper` selection-cache key. No longer leaks to users (the facade exposes no `adapters` map). | 🔴 Hidden | — | ✅ Minor — a generic frozen composite key. |
| `report.py` | `ReportMap` | 📦 Passive | `TypedDict` returned by `autodiscover`: module-name and qualified-class-name string tuples (`root_package`, `imported_*_modules`, `imported_modules`, `registered_ports`, `registered_adapters`). A plain dict, no `Any`. | 🟢 Public | — | — |
| `adapter_declaration.py` | `AdapterDeclaration` | 📦 Passive | Frozen carrier of the config captured by `@Adapter` (`port`/`key`/`lifecycle`/`envs`); the only consumer is `InversionMapper` at registration time. | 🔴 Hidden | — | — |
| `adapter_metadata.py` | `AdapterMetadata` | 📦 Passive *(with helpers)* | Frozen record of one *registered* adapter, plus `is_available_in()` and `environment_label()`. Surfaced read-only inside `PortBinding`. | 🔴 Hidden | — | — |
| `port_binding.py` | `PortBinding` | 📦 Passive | Frozen snapshot of one port: its `selected` adapter (for an environment) and all its `adapters`. Built by `InversionMapper.bindings()` as the single source of truth behind `describe()`. | 🟡 Mixed | Yes — exported from `domain` but not from top-level `idunn`; could become a public introspection type. | — |

## 🚨 Exceptions — `domain/errors.py`

All are 🟢 Public, 📦 Passive — users catch them. `IdunnError` is the shared base.

| Class | Raised when… |
|-------|--------------|
| `IdunnError` | Base for every Idunn error. |
| `InvalidPortError` | `@Port` is applied to a non-Protocol class. |
| `InvalidAdapterError` | An adapter registration is invalid (bad target, duplicate key in overlapping environments, unsatisfied port). |
| `AdapterNotFoundError` | No active adapter is registered for a requested port. |
| `DiscoveryError` | Autodiscovery fails to import a bounded module. |
| `MissingTypeHintError` | Constructor injection needs a type hint that is missing (or a non-port param with no default). |
| `InjectionCycleError` | Constructor dependency resolution loops back on itself. |

## 🏗️ Engine & orchestration

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `app/idunn.py` | `Idunn` | ⚙️ Active | Thin **facade** — a process-wide singleton (`metaclass=MetaSingleton`). Public surface is `autodiscover()`, `reset()`, and `describe()`; owns one `InversionMapper` + `InversionResolver` and delegates. `@Invert` reaches resolution via private `_inject` / `_has`. No public `resolve`/`register_*`. | 🟢 Public | — | — |
| `internal/inversion_mapper.py` | `InversionMapper` | ⚙️ Active | The catalog: registers ports/adapters, selects by key + environment, memoizes a `(environment, RegistrationKey)→AdapterMetadata` cache (invalidated on registration), and emits `PortBinding` snapshots. | 🔴 Hidden | — | — |
| `internal/inversion_resolver.py` | `InversionResolver` | ⚙️ Active | The construction engine: recursive constructor-time resolution, in-progress cycle stack, and the `SINGLETON` instance cache. Asks `InversionMapper` for selections; honors optional (`Port \| None` / defaulted) constructor params via `DecoratorSupport.port_from_annotation`. | 🔴 Hidden | — | — |
| `internal/inversion_validator.py` | `InversionValidator` | ⚙️ Active *(stateless)* | Stateless checks: adapter-class validity, duplicate registration in overlapping envs, and instance-satisfies-port. Called by mapper + resolver; raises `IdunnError`s. | 🔴 Hidden | — | — |
| `util/meta_singleton.py` | `MetaSingleton` | ⚙️ Active | Metaclass that caches one instance per class, making `Idunn()` a process-wide singleton. | 🔴 Hidden | — | ✅ A generic singleton metaclass. |
| `util/environment.py` | `Environment` | ⚙️ Active *(value + logic)* | Frozen value object holding a resolved env `name`, plus `current()` (resolve from arg → `IDUNN_ENV` → `local`) and `normalize()` (slugify + validate). Reached via `Idunn().reset(environment=...)`; not exported. | 🔴 Hidden | — | ✅ `normalize()` is a generic slug normalizer. |
| `internal/auto_discovery.py` | `AutoDiscovery` | ⚙️ Active | Imports the *bounded* set of port/adapter modules (names containing `port`/`ports`/`adapter`/`adapters`), registers the decorated classes into an `InversionMapper`, and returns a `ReportMap`. Reached via `Idunn().autodiscover`. | 🔴 Hidden | — | ✅ The module-scan helpers (`_candidate_module_names*`, `_module_name_for_file`, `_has_named_part`) are a reusable "find dotted modules under a package" utility. |
| `internal/decorator_support.py` | `DecoratorSupport` | ⚙️ Active | Helpers for the decorators: `normalize_envs()` (collapse `envs` into a normalized `frozenset`) and `port_from_annotation()` (resolve an annotation to `(port, optional)`, unwrapping `Optional`). | 🔴 Hidden | — | Minor — tied to Idunn rules. |

## 📚 Examples — `examples/`

Teaching code: 🟢 Public as *documentation*, but not part of the importable library. `examples/` is a
**discoverable package** run with `python -m examples.basic_usage`; it shows the real workflow —
`Idunn().autodiscover("examples.orchard")` then `@Invert`-root construction — with imports only from
`idunn`. The `examples.orchard` subpackage holds the discoverable `ports`/`adapters`.

| File | Class | Nature | Purpose |
|------|-------|--------|---------|
| `orchard/ports.py` | `AppleBasketPort` | 📦 Passive | `@Port` Protocol — contract with a single `take_apple()` method. |
| `orchard/adapters.py` | `GoldenAppleBasketAdapter` | ⚙️ Active | Unkeyed `@Adapter` (singleton) for `AppleBasketPort`; answers a plain `@Invert`. |
| `orchard/adapters.py` | `WildAppleBasketAdapter` | ⚙️ Active | Keyed `@Adapter` (`key='wild'`) for `AppleBasketPort`; opt-in, reached only via `@Invert(keys=...)`. |
| `basic_usage.py` | `Feast` | ⚙️ Active | Plain `@Invert`-root; its *unkeyed* `AppleBasketPort` is injected and assigned to `self.basket` automatically. |
| `basic_usage.py` | `Picnic` | ⚙️ Active | `@Invert`-root that opts into the keyed basket with `@Invert(keys={'basket': 'wild'})`. |
| `basic_usage.py` | `Example` | ⚙️ Active | Bundles the runnable `main()` (`autodiscover` + construct), avoiding loose module-level functions. |

## 🧭 Reading the catalog

- **The public surface is now tight.** Top-level `idunn` exports only the three decorators, `Idunn`,
  `LifecycleEnum`, and the exception hierarchy. The former 🟡 rows (`RegistrationKey`,
  `AdapterDeclaration`, `AdapterMetadata`) are now 🔴 plumbing behind the engine. The one remaining
  🟡 row is `PortBinding` — a read-only snapshot type that could graduate to a public introspection
  API if a need appears.
- **Reusable bits worth extracting.** `MetaSingleton`, `Environment.normalize` (slug normalizer), and
  `AutoDiscovery`'s module-scan helpers are the most project-agnostic code in the package.
- **Genuinely-hidden classes.** The engine trio (`InversionMapper`, `InversionResolver`,
  `InversionValidator`) plus `AutoDiscovery`, `DecoratorSupport`, `MetaSingleton`, and `Environment`
  are never meant to be imported by end users — they sit behind the `Idunn` facade.
