# Decision Log

> Append-only. The Coordinator logs significant decisions here.
> **Never delete or modify existing entries.**

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2026-03-12 | Create a local `main` branch before initializing the workflow. | The repository arrived with `master` only, but the installed `.ai` system and branch model require `main` as the default baseline. | Coordination and task branches now follow the documented `main -> phase -> task` structure without rewriting existing history. |
| 2026-03-12 | Split Phase 1 into four focused tasks and assign scaffolding first. | The foundation phase spans packaging, configuration, transport, and operator UX; smaller prompts reduce review scope and keep Builder work sequentially actionable. | The queue now contains tasks `1.1` to `1.4`, with task `1.1` active and the remaining tasks staged behind explicit dependencies. |
| 2026-03-12 | Defer Phase 1 PR creation until the remote branch baseline is aligned. | The local workflow now uses `main`, but the remote still only exposes `origin/master`, and no local PR CLI is installed to automate creation. | Phase 1 is complete locally on `phase/01-foundation`, but the PR step remains a coordination follow-up rather than part of this review pass. |
| 2026-03-12 | Start Phase 2 from refreshed `main` after the Phase 1 PR merge landed. | `origin/main` now contains the merged Phase 1 history, so Phase 2 can branch from the human-approved baseline instead of continuing on the completed phase branch. | The active coordination branch moves to `phase/02-submission-pipeline`, and Phase 1 remains closed rather than accumulating new planning work. |
| 2026-03-12 | Split Phase 2 into three sequential tasks and assign solver groundwork first. | Submission work spans solver abstraction, remote submit primitives, and CLI orchestration; separating them keeps reviews narrow and prevents the submit command from being built on unstable interfaces. | The queue now stages tasks `2.1` to `2.3`, with `2.1` active and later tasks gated on explicit dependencies. |
