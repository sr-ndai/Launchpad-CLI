# Command Reference

This section documents the current Launchpad CLI surface.

## Help Surfaces

Launchpad intentionally splits operator guidance across three entry points:

- `launchpad` opens the welcome screen
- `launchpad --help` shows the compact root reference card
- `launchpad <command> --help` shows flags and examples for one command

## Global Options

These options are available on the root command:

- `-v`, `--verbose`
- `-q`, `--quiet`
- `--json`
- `--no-color`
- `--version`
- `-h`, `--help`

Notes:

- `--json` only works when the selected command supports structured output
- human-readable command flows use the shared Phase 7 panel layout
- `launchpad logs` now accepts manifest-backed task references such as aliases,
  filenames, and relative paths on new jobs, and uses an interactive picker for
  ambiguous multi-task human TTY flows
- `launchpad` and `lp` are equivalent

## Commands

- [config](config.md): initialize and inspect configuration
- [submit](submit.md): package inputs and submit a job
- [status](status.md): inspect current or recent SLURM state
- [logs](logs.md): read SLURM or solver logs
- [download](download.md): retrieve results
- [cancel](cancel.md): cancel jobs or tasks
- [cleanup](cleanup.md): delete remote job directories
- [ls](ls.md): list remote files and directories
- [ssh](ssh.md): open an interactive shell on the cluster
- [doctor](doctor.md): check local and remote prerequisites
