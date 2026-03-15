# Submit Your First Job

This is the shortest safe workflow from local input files to downloaded
results.

## 1. Open the Folder With Your Inputs

Launchpad submit works from the current directory by default.

```powershell
cd C:\Projects\wing-model
```

For the implemented workflow, Launchpad looks for Nastran input files such as
`.dat`.

## 2. Preview the Submit Without Sending Anything

```powershell
launchpad submit --dry-run .
```

What to check in the dry run:

- the solver is `nastran`
- the discovered input files are correct
- any extra files you need are included
- the remote job directory looks right

If a referenced file is missing, either add it with `--extra-files` or use
`--include-all`.

## 3. Submit the Job

```powershell
launchpad submit .
```

Launchpad shows a spinner while compressing, a progress bar during upload, and
a spinner while the cluster extracts the archive. When submission succeeds, the
SLURM job ID is highlighted. Keep that job ID.

## 4. Check Progress

```powershell
launchpad status <JOB_ID>
launchpad status --watch
```

Use the first command for one snapshot. Use the second to keep refreshing until
you stop it with `Ctrl+C`.

## 5. Read Logs If You Need More Detail

```powershell
launchpad logs <JOB_ID>
launchpad logs <JOB_ID> -f
launchpad logs <JOB_ID> 0 -f
```

If the job has multiple tasks and you run `launchpad logs <JOB_ID> -f` from a
human terminal, Launchpad opens the interactive picker so you can choose the
task log with arrow keys. Explicit task refs still work with raw task IDs,
aliases, filenames, and relative paths on new manifest-backed jobs.

## 6. Download Results

```powershell
launchpad download <JOB_ID> .\results
```

Launchpad checks local space first, then shows a progress bar during transfer
and a spinner while extracting locally. A summary with next-step hints appears
when the download completes.

## 7. Optional Cleanup

```powershell
launchpad cleanup <JOB_ID>
```

Only do this after you are sure you have the results you need.

## If Something Does Not Match Expectations

- config or SSH problem: run `launchpad doctor`
- no solver files found: check you are in the right directory
- wrong packaged files: re-run with `--dry-run`
- download problems: see [Troubleshooting](troubleshooting.md)
