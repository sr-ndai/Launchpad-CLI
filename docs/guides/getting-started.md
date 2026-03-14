# Getting Started

This page is for a fresh Windows machine and a first Launchpad setup.

## Before You Start

You need:

- a cluster account
- an SSH private key that already works for that cluster
- the cluster host name
- your cluster username
- a terminal on Windows PowerShell

## 1. Install Launchpad

```powershell
uv tool install git+https://github.com/sr-ndai/Launchpad-CLI.git
launchpad --help
```

If the second command prints the command list, Launchpad is installed.

## 2. Create Your User Config

Interactive setup:

```powershell
launchpad config init
```

Non-interactive setup:

```powershell
launchpad config init --non-interactive --host headnode.example.com --username sergey --key-path C:\Users\sergey\.ssh\id_ed25519
```

This writes your user config to `~/.launchpad/config.toml`.

## 3. Check What Launchpad Resolved

```powershell
launchpad config show
launchpad doctor
```

What to expect:

- `config show` prints the resolved settings Launchpad will use
- `doctor` checks Python, config resolution, SSH key presence, SSH access,
  remote binaries, and the remote writable path

If `doctor` fails, go to [Troubleshooting](troubleshooting.md).

## 4. Know the Three Important File Locations

Launchpad resolves configuration in this order, highest priority first:

1. CLI flags
2. `LAUNCHPAD_*` environment variables
3. project-local `.launchpad.toml`
4. user config at `~/.launchpad/config.toml`
5. cluster config at `/shared/config/launchpad.toml`

In practice, most people only need the user config plus occasional command
flags.

## 5. Learn Four Terms Once

- `job`: the SLURM job created by `launchpad submit`
- `task`: one array item inside a job
- `partition`: the SLURM queue Launchpad submits into
- `scratch`: temporary remote working space for a task

## Next Step

Go to [Submit Your First Job](first-job.md).
