# Common Tasks

Use this page when you know what you want to do, but not which command does
it.

| I want to... | Use this |
| --- | --- |
| Set up Launchpad on a new machine | `launchpad config init` then `launchpad doctor` |
| See exactly which settings Launchpad will use | `launchpad config show` |
| See every supported config key and default | `launchpad config show --docs` |
| Open a shell on the cluster | `launchpad ssh` |
| Preview a submit without changing anything | `launchpad submit --dry-run .` |
| Include extra files in a submit | `launchpad submit --extra-files FILE ...` |
| Package the whole directory | `launchpad submit --include-all` |
| Watch all current jobs | `launchpad status --watch` |
| Inspect a specific job | `launchpad status <JOB_ID>` |
| Follow the live log for one task | `launchpad logs <JOB_ID> <TASK_ID> -f` |
| Download only selected tasks | `launchpad download <JOB_ID> --tasks 0,2` |
| Include scratch folders in the download | `launchpad download <JOB_ID> --include-scratch` |
| Cancel a whole job | `launchpad cancel <JOB_ID>` |
| Cancel only selected tasks | `launchpad cancel <JOB_ID> 0 2` |
| List files on the cluster | `launchpad ls` or `launchpad ls REMOTE_PATH` |
| Remove old remote job directories | `launchpad cleanup --older-than 30d` |

## Good Habits

- Run `launchpad submit --dry-run` before a new or unusual job.
- Keep your user config small; use per-command flags for one-off overrides.
- Use `launchpad doctor` before assuming the cluster is the problem.
- Do not run `cleanup` until you have checked the local download.
