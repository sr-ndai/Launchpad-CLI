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
- `--dry-run` now renders a submit preview with the manifest, payload summary,
  generated script, and the next command to run.
- `--transfer-mode multi-file` requires `--no-compress`.
- Root `--json` is supported for dry runs and successful submissions.
- successful submits highlight the job ID and point directly to the next status
  and download commands

## Good Defaults

For most users:

1. run `launchpad submit --dry-run .`
2. confirm the discovered files
3. run `launchpad submit .`
