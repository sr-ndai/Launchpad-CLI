"""Configuration models and future loading entry points for Launchpad."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SSHConfig(BaseModel):
    """SSH connection settings resolved from config files and environment."""

    host: str = Field(default="cluster.example.com")
    port: int = Field(default=22)
    username: str = Field(default="launcher")
    key_path: str = Field(default="~/.ssh/id_ed25519")
    known_hosts_path: str | None = None


class TransferConfig(BaseModel):
    """Transfer defaults reserved for future transport implementation."""

    parallel_streams: int = Field(default=1)
    chunk_size_mb: int = Field(default=64)
    compression_level: int = Field(default=3)
    verify_checksums: bool = Field(default=True)
    resume_enabled: bool = Field(default=True)


class ClusterConfig(BaseModel):
    """Cluster-wide filesystem and scheduler defaults."""

    shared_root: str = Field(default="/shared")
    default_partition: str = Field(default="simulation-r6i-8x")
    default_wall_time: str = Field(default="99:00:00")
    logs_subdir: str = Field(default="logs")


class LaunchpadConfig(BaseModel):
    """Top-level application configuration."""

    ssh: SSHConfig = Field(default_factory=SSHConfig)
    transfer: TransferConfig = Field(default_factory=TransferConfig)
    cluster: ClusterConfig = Field(default_factory=ClusterConfig)

