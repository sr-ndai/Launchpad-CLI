"""Layered configuration models and helpers for Launchpad."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import UnionType
from typing import Any, Mapping, MutableMapping, Sequence, Union, get_args, get_origin

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CLUSTER_CONFIG_PATH = Path("/shared/config/launchpad.toml")
DEFAULT_PROJECT_CONFIG_NAME = ".launchpad.toml"
ENV_PREFIX = "LAUNCHPAD_"

ENVIRONMENT_PATH_ALIASES: dict[str, tuple[str, ...]] = {
    "HOST": ("ssh", "host"),
    "USER": ("ssh", "username"),
    "KEY": ("ssh", "key_path"),
    "PORT": ("ssh", "port"),
    "SOLVER": ("submit", "solver"),
    "PARTITION": ("cluster", "default_partition"),
    "STREAMS": ("transfer", "parallel_streams"),
    "COMPRESSION": ("transfer", "compression_level"),
}


class LaunchpadBaseModel(BaseModel):
    """Shared Pydantic defaults for Launchpad configuration models."""

    model_config = ConfigDict(extra="ignore")


class SSHConfig(LaunchpadBaseModel):
    """SSH connection settings resolved from config files and environment."""

    host: str | None = Field(
        default=None,
        description="Cluster head node hostname or IP address.",
    )
    port: int = Field(default=22, description="SSH port for the cluster head node.")
    username: str | None = Field(
        default=None,
        description="SSH username used for Launchpad operations.",
    )
    key_path: str | None = Field(
        default=None,
        description="Path to the SSH private key file.",
    )
    known_hosts_path: str | None = Field(
        default=None,
        description="Optional known_hosts file for strict host verification.",
    )


class TransferConfig(LaunchpadBaseModel):
    """Transfer tuning defaults for upload and download workflows."""

    parallel_streams: int = Field(
        default=8,
        description="Number of transfer streams to use when parallel transfer is enabled.",
    )
    chunk_size_mb: int = Field(
        default=64,
        description="Preferred chunk size in megabytes for transfer work.",
        ge=1,
    )
    compression_level: int = Field(
        default=3,
        description="Default zstd compression level for archive creation.",
    )
    compression_threads: int = Field(
        default=0,
        description="Number of threads for compression work. Zero means auto-detect.",
    )
    verify_checksums: bool = Field(
        default=True,
        description="Whether transfers should verify checksums after completion.",
    )
    resume_enabled: bool = Field(
        default=True,
        description="Whether interrupted transfers should attempt resume behavior.",
    )

    @property
    def chunk_size_bytes(self) -> int:
        """Return the configured transfer chunk size in bytes."""

        return self.chunk_size_mb * 1024 * 1024


class ClusterConfig(LaunchpadBaseModel):
    """Cluster-wide filesystem and scheduler defaults."""

    shared_root: str = Field(
        default="/shared",
        description="Root path of the shared cluster filesystem.",
    )
    default_partition: str = Field(
        default="simulation-r6i-8x",
        description="Default SLURM partition for submissions.",
    )
    default_wall_time: str = Field(
        default="99:00:00",
        description="Default SLURM wall time limit.",
    )
    scratch_root: str = Field(
        default="{job_dir}/scratch",
        description="Scratch directory template for remote jobs.",
    )
    logs_subdir: str = Field(
        default="logs",
        description="Subdirectory name used for remote log output.",
    )


class SubmitConfig(LaunchpadBaseModel):
    """Default submission behavior shared by commands."""

    solver: str | None = Field(
        default=None,
        description="Preferred solver when it should not be auto-detected.",
    )
    cpus: int | None = Field(
        default=None,
        description="Default CPUs per task override for submissions.",
    )
    partition: str | None = Field(
        default=None,
        description="Preferred partition override for submissions.",
    )
    name_prefix: str | None = Field(
        default=None,
        description="Optional prefix used when generating run names.",
    )


class RemoteBinariesConfig(LaunchpadBaseModel):
    """Remote binary names or paths validated by diagnostics later in Phase 1."""

    sbatch: str = Field(default="sbatch", description="Path or executable name for sbatch.")
    squeue: str = Field(default="squeue", description="Path or executable name for squeue.")
    sacct: str = Field(default="sacct", description="Path or executable name for sacct.")
    tar: str = Field(default="tar", description="Path or executable name for tar.")
    zstd: str = Field(default="zstd", description="Path or executable name for zstd.")


class NastranDefaults(LaunchpadBaseModel):
    """Baseline Nastran configuration defaults."""

    executable_path: str = Field(
        default="/shared/siemens/nastran2312/bin/nastran",
        description="Path to the Nastran executable on the cluster.",
    )
    input_extension: str = Field(
        default=".dat",
        description="Primary file extension used for Nastran input discovery.",
    )
    memory: str = Field(default="236Gb", description="Default Nastran memory setting.")
    buffpool: str = Field(default="5Gb", description="Default Nastran buffpool setting.")
    buffsize: int = Field(default=65537, description="Default Nastran buffsize setting.")
    smemory: str = Field(default="150Gb", description="Default Nastran smemory setting.")
    memorymaximum: str = Field(
        default="236Gb",
        description="Default Nastran memorymaximum setting.",
    )
    default_cpus: int = Field(
        default=12,
        description="Default CPU count used for Nastran submissions.",
    )


class AnsysDefaults(LaunchpadBaseModel):
    """Baseline ANSYS configuration defaults."""

    executable_path: str = Field(
        default="/shared/ansys/v241/bin/ansys241",
        description="Path to the ANSYS executable on the cluster.",
    )
    input_extension: str = Field(
        default=".dat",
        description="Primary file extension used for ANSYS input discovery.",
    )
    default_cpus: int = Field(
        default=12,
        description="Default CPU count used for ANSYS submissions.",
    )


class SolverConfig(LaunchpadBaseModel):
    """Grouped solver-specific defaults."""

    nastran: NastranDefaults = Field(
        default_factory=NastranDefaults,
        description="Nastran solver defaults.",
    )
    ansys: AnsysDefaults = Field(
        default_factory=AnsysDefaults,
        description="ANSYS solver defaults.",
    )


class LaunchpadConfig(LaunchpadBaseModel):
    """Top-level Launchpad configuration model."""

    ssh: SSHConfig = Field(default_factory=SSHConfig, description="SSH connection settings.")
    transfer: TransferConfig = Field(
        default_factory=TransferConfig,
        description="Transfer and compression settings.",
    )
    cluster: ClusterConfig = Field(
        default_factory=ClusterConfig,
        description="Cluster-wide defaults.",
    )
    submit: SubmitConfig = Field(
        default_factory=SubmitConfig,
        description="Submission defaults and overrides.",
    )
    solvers: SolverConfig = Field(
        default_factory=SolverConfig,
        description="Solver-specific settings.",
    )
    remote_binaries: RemoteBinariesConfig = Field(
        default_factory=RemoteBinariesConfig,
        description="Remote binary names used by cluster commands.",
    )


@dataclass(frozen=True, slots=True)
class ConfigLayer:
    """A single configuration layer that participated in resolution."""

    name: str
    data: dict[str, Any]
    path: Path | None = None
    loaded: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """Resolved Launchpad configuration and the layers used to build it."""

    config: LaunchpadConfig
    layers: tuple[ConfigLayer, ...]

    @property
    def loaded_files(self) -> tuple[Path, ...]:
        """Return the config files that were found and read."""

        return tuple(layer.path for layer in self.layers if layer.loaded and layer.path is not None)

    def as_dict(self) -> dict[str, Any]:
        """Return the resolved configuration as plain Python data."""

        return self.config.model_dump(mode="json", exclude_none=True)


def default_user_config_path(home: Path | None = None) -> Path:
    """Return the default user config path for the current home directory."""

    base_home = home if home is not None else Path.home()
    return base_home / ".launchpad" / "config.toml"


def default_log_dir(home: Path | None = None) -> Path:
    """Return the default Launchpad log directory for the current home directory."""

    base_home = home if home is not None else Path.home()
    return base_home / ".launchpad" / "logs"


def load_optional_toml(path: Path, *, name: str) -> ConfigLayer:
    """Load a TOML file when present and return a config layer description."""

    if not path.exists():
        logger.debug("Config layer `{}` not found at {}", name, path)
        return ConfigLayer(name=name, data={}, path=path, loaded=False)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    logger.debug("Loaded config layer `{}` from {}", name, path)
    return ConfigLayer(name=name, data=data, path=path, loaded=True)


def environment_overrides(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Translate `LAUNCHPAD_*` environment variables into nested config data."""

    values = env if env is not None else os.environ
    overrides: dict[str, Any] = {}
    for key, raw_value in values.items():
        if not key.startswith(ENV_PREFIX):
            continue
        suffix = key[len(ENV_PREFIX) :]
        path = ENVIRONMENT_PATH_ALIASES.get(suffix)
        if path is None:
            path = tuple(part.lower() for part in suffix.split("__") if part)
        if not path:
            continue
        _set_nested_value(overrides, path, raw_value)

    if overrides:
        logger.debug("Resolved environment overrides for keys: {}", _flatten_keys(overrides))
    return overrides


def normalize_cli_overrides(overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize CLI override mappings into nested config dictionaries."""

    if overrides is None:
        return {}

    normalized: dict[str, Any] = {}
    for key, value in overrides.items():
        if value is None:
            continue
        if "." in key:
            _set_nested_value(normalized, tuple(part.strip() for part in key.split(".")), value)
            continue
        if isinstance(value, Mapping):
            branch = normalize_cli_overrides({str(nested_key): nested_value for nested_key, nested_value in value.items()})
            existing = normalized.get(key)
            if isinstance(existing, MutableMapping):
                normalized[key] = deep_merge(existing, branch)
            else:
                normalized[key] = branch
            continue
        normalized[key] = value

    if normalized:
        logger.debug("Resolved CLI overrides for keys: {}", _flatten_keys(normalized))
    return normalized


def resolve_config(
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    cluster_config_path: Path | None = None,
    user_config_path: Path | None = None,
) -> ResolvedConfig:
    """Resolve the Launchpad configuration using the documented layer order."""

    current_dir = cwd if cwd is not None else Path.cwd()
    cluster_path = cluster_config_path if cluster_config_path is not None else DEFAULT_CLUSTER_CONFIG_PATH
    user_path = user_config_path if user_config_path is not None else default_user_config_path()
    project_path = current_dir / DEFAULT_PROJECT_CONFIG_NAME
    env_overrides = environment_overrides(env)
    cli_layer_overrides = normalize_cli_overrides(cli_overrides)

    layers = (
        load_optional_toml(cluster_path, name="cluster"),
        load_optional_toml(user_path, name="user"),
        load_optional_toml(project_path, name="project"),
        ConfigLayer(
            name="environment",
            data=env_overrides,
            loaded=bool(env_overrides),
        ),
        ConfigLayer(
            name="cli",
            data=cli_layer_overrides,
            loaded=bool(cli_layer_overrides),
        ),
    )

    merged = LaunchpadConfig().model_dump(mode="python")
    for layer in layers:
        if layer.data:
            merged = deep_merge(merged, layer.data)

    config = LaunchpadConfig.model_validate(merged)
    logger.debug("Resolved config with loaded files: {}", [str(path) for path in ResolvedConfig(config=config, layers=layers).loaded_files])
    return ResolvedConfig(config=config, layers=layers)


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge two configuration dictionaries."""

    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def dumps_toml(data: Mapping[str, Any]) -> str:
    """Serialize nested configuration data into a minimal TOML string."""

    lines = _render_toml_table(data)
    return "\n".join(lines)


def write_toml_file(path: Path, data: Mapping[str, Any]) -> Path:
    """Write nested configuration data to disk as TOML."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{dumps_toml(data)}\n", encoding="utf-8")
    logger.debug("Wrote TOML config to {}", path)
    return path


def render_config_docs() -> str:
    """Render the documented configuration schema as plain text."""

    lines: list[str] = []
    _append_model_docs(LaunchpadConfig, lines=lines)
    return "\n".join(lines)


def _append_model_docs(
    model_type: type[BaseModel],
    *,
    lines: list[str],
    prefix: str = "",
) -> None:
    for field_name, field in model_type.model_fields.items():
        path = f"{prefix}.{field_name}" if prefix else field_name
        nested_model = _nested_model_type(field.annotation)
        if nested_model is not None:
            lines.append(path)
            if field.description:
                lines.append(f"  {field.description}")
            _append_model_docs(nested_model, lines=lines, prefix=path)
            continue

        default_value = _field_default(field)
        default_text = "required" if field.is_required() else json.dumps(default_value)
        lines.append(
            f"{path} ({_format_annotation(field.annotation)}, default={default_text})"
        )
        if field.description:
            lines.append(f"  {field.description}")


def _nested_model_type(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation

    origin = get_origin(annotation)
    if origin is None:
        return None

    for argument in get_args(annotation):
        nested = _nested_model_type(argument)
        if nested is not None:
            return nested
    return None


def _field_default(field: Any) -> Any:
    if field.default_factory is not None:
        default = field.default_factory()
        if isinstance(default, BaseModel):
            return default.model_dump(mode="json", exclude_none=True)
        return default

    if isinstance(field.default, BaseModel):
        return field.default.model_dump(mode="json", exclude_none=True)
    return field.default


def _format_annotation(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is None:
        return getattr(annotation, "__name__", str(annotation))

    if origin in (list, tuple, set):
        arguments = ", ".join(_format_annotation(argument) for argument in get_args(annotation))
        return f"{origin.__name__}[{arguments}]"

    if origin in (Union, UnionType):
        arguments = " | ".join(_format_annotation(argument) for argument in get_args(annotation))
        return arguments

    arguments = ", ".join(_format_annotation(argument) for argument in get_args(annotation))
    return f"{getattr(origin, '__name__', str(origin))}[{arguments}]"


def _flatten_keys(data: Mapping[str, Any], *, prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            keys.extend(_flatten_keys(value, prefix=path))
        else:
            keys.append(path)
    return keys


def _set_nested_value(target: MutableMapping[str, Any], path: Sequence[str], value: Any) -> None:
    current: MutableMapping[str, Any] = target
    normalized_path = [part.strip().lower() for part in path if part.strip()]
    for segment in normalized_path[:-1]:
        existing = current.get(segment)
        if not isinstance(existing, MutableMapping):
            existing = {}
            current[segment] = existing
        current = existing
    if normalized_path:
        current[normalized_path[-1]] = value


def _render_toml_table(data: Mapping[str, Any], *, prefix: tuple[str, ...] = ()) -> list[str]:
    lines: list[str] = []
    scalar_items: list[tuple[str, Any]] = []
    nested_items: list[tuple[str, Mapping[str, Any]]] = []

    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            nested_items.append((key, value))
        else:
            scalar_items.append((key, value))

    if prefix:
        lines.append(f"[{'.'.join(prefix)}]")

    for key, value in scalar_items:
        lines.append(f"{key} = {_format_toml_value(value)}")

    for key, value in nested_items:
        if lines:
            lines.append("")
        lines.extend(_render_toml_table(value, prefix=(*prefix, key)))

    return lines


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Path):
        return json.dumps(str(value))
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    return json.dumps(str(value))
