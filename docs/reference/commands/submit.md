# `launchpad submit`

Use `submit` to discover solver inputs, package them, transfer them, generate
the remote SLURM script, and submit the job.

## Syntax

```text
launchpad submit [OPTIONS] [INPUT_DIR]
```

## Common Uses

Preview a submit:

```powershell
launchpad submit --dry-run .
```

Submit from the current folder:

```powershell
launchpad submit .
```

Override the run name and CPU count:

```powershell
launchpad submit . --name wing_v3 --cpus 16
```

Package extra files:

```powershell
launchpad submit . --extra-files materials.txt --extra-files include.inc
```

## Important Options

- `--solver [nastran|ansys]`
- `--name`
- `--cpus`
- `--max-concurrent`
- `--partition`
- `--time`
- `--begin`
- `--transfer-mode [auto|single-file|multi-file]`
- `--streams`
- `--compression-level`
- `--no-compress`
- `--extra-files FILE`
- `--include-all`
- `--dry-run`

## Behavior Notes

- `INPUT_DIR` defaults to the current directory.
- Nastran is the only implemented solver workflow right now.
- Asking for `ansys` results in a clear "not implemented" failure.
- project-local `.launchpad.toml` files can export solver-specific environment
  variables into the generated SLURM script through
  `solvers.nastran.environment`
- use that config surface for per-project requirements such as
  `SPLM_LICENSE_SERVER = "29001@eng-apps-license-01.rs.corp"` instead of
  hardcoding cluster-specific values in Launchpad itself
- `--dry-run` now renders a submit preview with the manifest, payload summary,
  generated script, and the next command to run.
- remote job directories are created beneath `cluster.workspace_root` when set
  and otherwise beneath the legacy `<shared_root>/<ssh.username>` fallback
- `--transfer-mode multi-file` requires `--no-compress`.
- Root `--json` is supported for dry runs and successful submissions.
- successful submits highlight the job ID and point directly to the next status
  and download commands

## Good Defaults

For most users:

1. run `launchpad submit --dry-run .`
2. confirm the discovered files
3. run `launchpad submit .`
