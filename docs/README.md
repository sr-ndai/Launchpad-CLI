# Documentation

Use this page as the entry point for Launchpad's docs.

## Start Here

These pages are written for people who want Launchpad to work quickly and do
not want to read the whole command reference first.

- [Getting Started](guides/getting-started.md)
- [Submit Your First Job](guides/first-job.md)
- [Common Tasks](guides/common-tasks.md)
- [Troubleshooting](guides/troubleshooting.md)

## Reference

These pages are for users who want the full command surface and configuration
model.

- [Configuration Reference](reference/configuration.md)
- [Command Reference](reference/commands/README.md)

## Technical Notes

These are useful if you are extending Launchpad or reviewing design decisions.

- [Architecture](../ARCHITECTURE.md)
- [Transfer Architecture Decision](transfer-benchmark.md)

## Current Limits

- Nastran is the only implemented solver workflow.
- ANSYS submit support is intentionally deferred.
- `launchpad config edit` and `launchpad config validate` are scaffolded but
  not implemented.
