# 🍎 Idunn — Class & File Catalog

A map of every class defined in the live `idunn/` package and the runnable `examples/`. Use it to
tell at a glance what is part of the public contract, what is plumbing, and what could be tightened.
The package is split into four layers — `app/`, `domain/`, `internal/`, `util/` — and the import
directions between them are enforced by `tests/test_architecture.py`.

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

`__init__.py` is the barrel that re-exports the public names below (its `__all__`). It contains no
logic of its own — 🟢 Public, 📦 Passive. The hidden plumbing it does **not** export: `MetaSingleton`,
`Environment`, `AutoDiscovery`, and `DecoratorSupport`.

## ⚙️ Decorators — `app/decorators.py`

| Class / Symbol | Nature | Purpose | Audience | Splittable? | Generic utility? |
|----------------|--------|---------|----------|-------------|------------------|
| `Port` | ⚙️ Active | Marks a `typing.Protocol` as an injectable port: validates it really is a Protocol, sets `__idunn_port__`, and makes it `runtime_checkable`. | 🟢 Public | — | — |
| `Adapter` | ⚙️ Active | Decorator factory that declares a class as an adapter for a port, capturing `key`/`lifecycle`/`default`/`envs` into an `AdapterDeclaration`. Constructs nothing. | 🟢 Public | — | — |
| `Invert` | ⚙️ Active | Wraps a *consumer's* `__init__`: every `@Port`-typed parameter is resolved from the `Idunn()` singleton at construction time and assigned to `self.<name>` (caller args override). Supports `keys=` and an explicit `{param: Port}` map. | 🟢 Public | — | — |

## 🧱 Definitions & metadata — `domain/`

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `lifecycle_enum.py` | `LifecycleEnum` | 📦 Passive | `StrEnum` of adapter lifecycles: `SINGLETON`, `TRANSIENT`. Passed by users to `@Adapter`. | 🟢 Public | — | — |
| `registration_key.py` | `RegistrationKey` | 📦 Passive | Frozen `(port, key)` pair used to group adapter bindings. Leaks to users through `Idunn().adapters` keys. | 🟡 Mixed | Yes — could be internal-only if `adapters` exposed a different shape. | ✅ Minor — a generic frozen composite key. |
| `report.py` | `ReportMap` | 📦 Passive | `TypedDict` returned by `autodiscover`: module-name and qualified-class-name string tuples (`root_package`, `imported_*_modules`, `imported_modules`, `registered_ports`, `registered_adapters`). A plain dict, no `Any`. | 🟢 Public | — | — |
| `adapter_declaration.py` | `AdapterDeclaration` | 📦 Passive | Frozen carrier of the config captured by `@Adapter`; the only consumer is the container at registration time. | 🟡 Mixed | Yes — realistically an internal type; nothing user-facing needs it. | — |
| `adapter_metadata.py` | `AdapterMetadata` | 📦 Passive *(with helpers)* | Frozen record of one *registered* adapter, plus `is_available_in()` and `environment_label()`. Surfaced via `Idunn().adapters`. | 🟡 Mixed | Yes — keep the data fields public for introspection, hide the helper methods. | — |

## 🚨 Exceptions — `domain/errors.py`

All are 🟢 Public, 📦 Passive — users catch them. `IdunnError` is the shared base.

| Class | Raised when… |
|-------|--------------|
| `IdunnError` | Base for every Idunn error. |
| `InvalidPortError` | `@Port` is applied to a non-Protocol class. |
| `InvalidAdapterError` | An adapter registration is invalid (bad target, duplicate key/default, unsatisfied port). |
| `AdapterNotFoundError` | No active adapter is registered for a requested port. |
| `DiscoveryError` | Autodiscovery fails to import a bounded module. |
| `MissingTypeHintError` | Constructor injection needs a type hint that is missing (or a non-port param with no default). |
| `InjectionCycleError` | Constructor dependency resolution loops back on itself. |

## 🏗️ Engine & orchestration

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `app/idunn.py` | `Idunn` | ⚙️ Active | The engine **and** the public container — a process-wide singleton (`metaclass=MetaSingleton`). Registers ports/adapters, selects by precedence + environment, builds object graphs, caches singletons, `reset()`s state, and can `describe()` itself. | 🟢 Public | N/A (🟢) — large: registration, resolution, and description are three responsibilities that could be separated internally. | — |
| `util/meta_singleton.py` | `MetaSingleton` | ⚙️ Active | Metaclass that caches one instance per class, making `Idunn()` a process-wide singleton. | 🔴 Hidden | — | ✅ A generic singleton metaclass. |
| `util/environment.py` | `Environment` | ⚙️ Active *(value + logic)* | Frozen value object holding a resolved env `name`, plus `current()` (resolve from arg → `IDUNN_ENV` → `local`) and `normalize()` (slugify + validate). Reached only via `Idunn().reset(environment=...)`; not exported. | 🔴 Hidden | — | ✅ `normalize()` is a generic slug normalizer. |
| `internal/auto_discovery.py` | `AutoDiscovery` | ⚙️ Active | Imports the *bounded* set of port/adapter modules (names containing `port`/`ports`/`adapter`/`adapters`), registers the decorated classes, and returns a `ReportMap`. Reached via `Idunn().autodiscover`. | 🔴 Hidden | — | ✅ The module-scan helpers (`_candidate_module_names*`, `_module_name_for_file`, `_has_named_part`) are a reusable "find dotted modules under a package" utility. |
| `internal/decorator_support.py` | `DecoratorSupport` | ⚙️ Active | Helper holding `normalize_envs()`, which collapses the `envs` argument into a normalized `frozenset`. | 🔴 Hidden | — | Minor — env-name normalization, tied to Idunn rules. |

## 📚 Examples — `examples/basic_usage.py`

Teaching code: 🟢 Public as *documentation*, but not part of the importable library.

| Class | Nature | Purpose |
|-------|--------|---------|
| `AppleBasketPort` | 📦 Passive | `@Port` Protocol — contract with a single `take_apple()` method. |
| `GoldenAppleBasketAdapter` | ⚙️ Active | `@Adapter` (singleton) implementing `AppleBasketPort`. |
| `Feast` | ⚙️ Active | Plain consumer whose `__init__` is decorated with `@Invert`; its `AppleBasketPort` is injected and assigned to `self.basket` automatically. |

## 🧭 Reading the catalog

- **Tighten the public surface.** The 🟡 rows (`RegistrationKey`, `AdapterDeclaration`,
  `AdapterMetadata`) are exported today but are closer to plumbing than headline API. Each has a
  concrete split noted above if you ever want a leaner `__all__`.
- **Reusable bits worth extracting.** `MetaSingleton`, `Environment.normalize` (slug normalizer), and
  `AutoDiscovery`'s module-scan helpers are the most project-agnostic code in the package.
- **Genuinely-hidden classes.** `MetaSingleton`, `Environment`, `AutoDiscovery`, and
  `DecoratorSupport` are never meant to be imported by end users.
