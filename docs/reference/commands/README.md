# Command Reference

This section documents the current Launchpad CLI surface.

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
