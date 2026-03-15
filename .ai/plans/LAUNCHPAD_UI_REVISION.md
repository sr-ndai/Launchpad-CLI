# Launchpad CLI — UI Revision: Lessons from Impeccable

> **Context:** The first redesign pass (V1 plan) successfully eliminated box
> fatigue and established a clean flat layout. The welcome screen is excellent.
> But the remaining commands (doctor, config show, config init) feel washed out
> — everything blends into the same dim gray mush. This revision fixes that by
> applying Impeccable's core principles translated to terminal design.

---

## 1. The Diagnosis

Looking at the current screenshots with Impeccable's lens, the problem is the
CLI equivalent of "gray text on colored backgrounds":

**The V1 plan over-applied dimming.** When labels, values, details, and
suggestions all live in the same gray band, nothing stands out. The user's eye
has nowhere to land. The welcome screen works because it has real contrast:
bright white text, cyan arrows, bold command names, and dim descriptions each
at a *different* brightness level. The other screens don't have that range.

Impeccable's anti-pattern list includes "Don't use gray text on colored
backgrounds — it looks washed out." The terminal equivalent: **don't use `dim`
for everything that isn't the primary identifier.** That's exactly what
happened.

---

## 2. The Three Impeccable Principles That Apply

### Principle 1: Tinted Neutrals

> "Tint your neutrals toward your brand hue — even a subtle hint creates
> subconscious cohesion."

Currently `display.py` uses Rich's generic `dim` and `grey70`. These are pure
gray — they have no relationship to the brand color (cyan). Replace them with
**cyan-tinted grays** that feel cohesive with the accent color.

```python
# ── BEFORE (generic grays) ──
C_DIM    = "dim"
C_MUTED  = "grey70"

# ── AFTER (tinted neutrals) ──
# These hex values are blue/cyan-tinted grays.
# They feel cohesive with the cyan accent rather than dead neutral.
C_SECONDARY  = "#8a9bae"  # Labels, metadata — readable but clearly secondary
C_TERTIARY   = "#5e6d7e"  # Suggestions, hints — intentionally quiet
C_FAINT      = "#44515e"  # Decorative rules, separators only
```

The exact hex values should be tuned on the actual terminal, but the principle
is: **no pure gray anywhere.** Every "gray" has a slight cool-blue tint that
echoes the cyan accent.

### Principle 2: Visual Hierarchy Through Varied Weight

> "Vary font weights and sizes to create clear visual hierarchy."

Terminals don't have font sizes, but they do have **four brightness levels**
(bold/bright, normal, secondary, faint) and **color as emphasis**. The current
UI only uses two levels: bold for identifiers and dim for everything else. That
is not enough.

Define exactly **five visual tiers** and assign every piece of text to one:

```
Tier   Rich Markup                     Used For
─────  ─────────────────────────────── ──────────────────────────────────
 T1    [bold]text[/]                    Primary identifiers: job ID, run name,
                                        check names, command names in help
 T2    [default]text[/]  (no markup)    Important values: file paths, IP
                                        addresses, partition names, version
                                        strings — things the user actually needs
 T3    [#8a9bae]text[/]  (C_SECONDARY)  Labels in KV pairs, column headers,
                                        section sub-headers, status words
 T4    [#5e6d7e]text[/]  (C_TERTIARY)   Suggestions after errors, secondary
                                        metadata (port numbers, default values),
                                        "not found" messages
 T5    [#44515e]text[/]  (C_FAINT)      Rule lines, decorative separators,
                                        version number in welcome screen
```

**The critical mistake in V1 was putting both labels (T3) and values (T2) in
the same dim tier.** Labels should be secondary. Values should be full
brightness. This creates the contrast that makes KV pairs scannable.

### Principle 3: Strategic Color Accents

> "Dominant colors with sharp accents outperform timid, evenly-distributed
> palettes."

The welcome screen nails this: cyan `→` arrows are the *only* colored elements,
and they pop because everything else is white or gray. The other screens need
the same discipline. Color should be used for exactly three purposes:

1. **State** — green ✓, red ✗, yellow ▲ (already correct)
2. **Action affordance** — cyan `→` for next-step commands (already correct)
3. **Key identifiers** — the ONE most important value in a section gets the
   accent color

That third use is new. Example: in the doctor output, the check name (Python
Runtime, SSH Connection) should be T1 bold white. But the *result value* for
passing checks (Python 3.12.2, 10.98.72.105:22) can afford to be default
white — it doesn't need cyan. Cyan is reserved for the next-steps block.

**Don't colorize everything.** Impeccable says: "the key is intentionality,
not intensity."

---

## 3. Revised Visual Grammar

### 3.1 The KV Pair — Fixed

The biggest visual problem. Here is the fix:

```
BEFORE (V1 — everything same gray):
  [dim]host[/]              [dim]test[/]
  [dim]port[/]              [dim]22[/]
  [dim]username[/]          [dim]test[/]

AFTER (labels secondary, values full brightness):
  [#8a9bae]host[/]              test
  [#8a9bae]port[/]              22
  [#8a9bae]username[/]          test
```

In Rich markup:
```python
def kv(label: str, value: str, *, label_width: int = 20, indent: int = 4) -> None:
    """Print an aligned key-value pair.

    Label is secondary tinted gray. Value is default terminal foreground
    (bright white on dark terminals). This contrast is what makes KV pairs
    scannable.
    """
    pad = " " * indent
    console.print(f"{pad}[{C_SECONDARY}]{label:<{label_width}}[/]{value}")
```

**Note:** The label width increased from 16 to 20 to prevent cramping on longer
labels like `compression_level` or `executable_path`.

### 3.2 Section Headers — More Breathing Room

The current headers (`Doctor ──────`) are good but could use one more visual
trick: the header text itself should be at T1 (bold) while the rule line uses
the faintest tier.

```python
def section_header(title: str) -> None:
    """Print a section header with a tinted rule line."""
    console.print()
    console.print(Rule(f"[bold]{title}[/]", style=C_FAINT, align="left"))
```

### 3.3 Status Lines — Separate the Check from the Result

The doctor output currently crams the check name and result onto one line with
no visual break. When the result is long (like the Config Resolution line), it
becomes a wall of text.

**Fix:** Put the result on the same line only if it's short (<40 chars).
Otherwise, drop it to a new line indented under the check name.

```
BEFORE:
  ✓  Config Resolution    Config resolved from /Users/srogachev/.launchpad/config.toml; ssh.host=test, ssh.username=test.

AFTER (short result, same line):
  ✓  Python Runtime       Python 3.12.13

AFTER (long result, dropped):
  ✓  Config Resolution
     config.toml → ssh.host=test, ssh.username=test
```

Implementation:
```python
def status_line(
    symbol: str,
    label: str,
    detail: str = "",
    *,
    indent: int = 4,
    max_inline_detail: int = 45,
) -> None:
    """Print a status-prefixed check line.

    Short details appear inline. Long details drop to the next line,
    indented and styled as tertiary text.
    """
    pad = " " * indent
    if detail and len(detail) <= max_inline_detail:
        console.print(
            f"{pad}{symbol}  [bold]{label:<22}[/][{C_SECONDARY}]{detail}[/]"
        )
    elif detail:
        console.print(f"{pad}{symbol}  [bold]{label}[/]")
        console.print(f"{pad}   [{C_TERTIARY}]{detail}[/]")
    else:
        console.print(f"{pad}{symbol}  [bold]{label}[/]")
```

### 3.4 Error/Suggestion Lines — Visually Distinct

Suggestions after failed checks should be clearly different from the check
result. Use T4 (tertiary) with a leading arrow to make them feel actionable
rather than just dim text:

```
BEFORE:
  ✗  Shared Config        Shared config not found: /shared/config/launchpad.toml
     Mount the shared `/shared` filesystem or rely on user/project/env config overrides.

AFTER:
  ✗  Shared Config
     not found: /shared/config/launchpad.toml
     → Mount /shared or rely on user/project/env config overrides.
```

The `→` prefix on the suggestion line reuses the same "action affordance"
pattern from next-steps, creating visual consistency.

### 3.5 The Skipped State — Less Text

The "Skipped remote checks because local SSH configuration is incomplete"
message appears three times and creates visual noise. Compress it:

```
BEFORE:
  —  SSH Connection       Skipped remote checks because local SSH configuration is incomplete.
  —  Remote Binaries      Skipped remote binary checks because local SSH configuration is incomplete.
  —  Remote Writable Root Skipped remote writable-path checks because local SSH configuration is incomplete.

AFTER:
  —  SSH Connection       skipped (SSH not configured)
  —  Remote Binaries      skipped (SSH not configured)
  —  Remote Writable Root skipped (SSH not configured)
```

Parenthetical reason in T4, not a full sentence. The user already knows why —
they just saw the SSH Key failure above.

---

## 4. Revised Command Output — Doctor

Putting it all together, here's what `launchpad doctor` should look like with
these revisions:

```
Doctor ─────────────────────────────────────────────

  Local Setup
    ✓  Python Runtime       Python 3.12.13
    ✓  Config Resolution
       config.toml → ssh.host=test, ssh.username=test
    ✗  SSH Key
       not found: test
       → Set ssh.key_path to a readable private key file.
    ✗  Shared Config
       not found: /shared/config/launchpad.toml
       → Mount /shared or rely on user/project/env config overrides.

  Cluster Access
    —  SSH Connection       skipped (SSH not configured)
    —  Remote Binaries      skipped (SSH not configured)
    —  Remote Writable Root skipped (SSH not configured)

  7 checks: 2 passed, 2 failed, 3 skipped

Next ───────────────────────────────────────────────
  → launchpad config init
  → launchpad config show
  → launchpad doctor
```

Visual breakdown by tier:
- **T1 (bold white):** "Doctor", "Local Setup", "Cluster Access", "Next",
  check names (Python Runtime, SSH Key, etc.)
- **T2 (default white):** result values (Python 3.12.13, test)
- **T3 (secondary tinted gray):** labels in dropped detail lines, count numbers
  in summary, "config.toml →"
- **T4 (tertiary tinted gray):** suggestion lines after `→`, "skipped" reasons
- **T5 (faint tinted gray):** the `─────` rule lines
- **Color:** green ✓, red ✗, dim —, cyan → (unchanged)

---

## 5. Revised Command Output — Config Show

The config show screen is actually close. The main fix is label/value contrast:

```
Resolved Configuration ─────────────────────────────

  Sources (highest to lowest priority)
    1. CLI flags                  none
    2. Environment variables      none
    3. Project config             not found
    4. User config                /Users/srogachev/.launchpad/config.toml
    5. Shared config              not found

  SSH
    host                test
    port                22
    username            test
    key_path            test

  Transfer
    parallel_streams    8
    chunk_size_mb       64
    compression_level   3
    verify_checksums    enabled
    resume_enabled      enabled
```

Key changes from current:
- **Labels** (`host`, `port`, `parallel_streams`) are `C_SECONDARY` (tinted
  gray) — readable but clearly subordinate.
- **Values** (`test`, `22`, `8`) are default foreground (bright white) — they
  pop because the labels recede.
- **Section names** (`SSH`, `Transfer`, `Cluster`) are **bold** at T1.
- **Source list numbers** are `C_SECONDARY`, source names are T1 (bold),
  values are T2 (default) or T4 if "not found"/"none".

The existing layout (indent levels, section grouping) is already good.

---

## 6. Config Init — Guided Setup

The current config init flow (Image 3) is functional but plain. Apply the tier
system:

```
Guided Setup ───────────────────────────────────────
Set up Launchpad for your cluster.

    config_file         /Users/srogachev/.launchpad/config.toml
    required_prompts    host, username, key_path, port
    optional            known_hosts_path stays inherited unless you pass a flag

Cluster SSH host or IP [10.98.72.105]: test
Cluster username [ubuntu]: test
Path to SSH private key [/Users/srogachev/.ssh/key.pem]: test
SSH port [22]:

Config Ready ───────────────────────────────────────
  ✓  Saved user config at /Users/srogachev/.launchpad/config.toml

  SSH
    host                test
    port                22
    username            test
    key_path            test
    known_hosts_path    system default / inherited

  Shared Config
    —  shared config not detected; user, project, env, and CLI overrides still work

Next ───────────────────────────────────────────────
  → launchpad config show
  → launchpad doctor
  → launchpad submit --dry-run .
```

Changes:
- The prompt defaults in brackets `[10.98.72.105]` should use `C_SECONDARY`
  (tinted gray), not the same brightness as the prompt text. This makes the
  user's input the brightest thing on the line.
- The metadata block at the top (`config_file`, `required_prompts`, `optional`)
  uses the standard `kv()` function with secondary labels.
- The "Config Ready" section follows the same pattern as doctor.

---

## 7. Updated display.py Constants

Replace the color constants section of `display.py`:

```python
# ── Color semantics ──────────────────────────────────────────────────────
# State colors (used only for status symbols and state words)
C_SUCCESS  = "green"
C_ERROR    = "red"
C_WARN     = "yellow"
C_ACTION   = "cyan"          # Next-step arrows, action affordances

# Tinted neutral scale (blue/cyan-tinted grays for cohesion with C_ACTION)
# These replace generic "dim" and "grey70" everywhere.
# Tune these hex values on your actual terminal + color scheme.
C_SECONDARY = "#8a9bae"      # Tier 3: labels, column headers, metadata
C_TERTIARY  = "#5e6d7e"      # Tier 4: suggestions, hints, "not found"
C_FAINT     = "#44515e"      # Tier 5: rule lines, decorative separators

# Tier 1 (bold white) and Tier 2 (default white) don't need constants —
# they use Rich's [bold] and unstyled text respectively.
```

And update every primitive function to use these tiers instead of `dim`:

```python
SYM_PASS = f"[bold {C_SUCCESS}]✓[/]"
SYM_FAIL = f"[bold {C_ERROR}]✗[/]"
SYM_RUN  = f"[bold {C_SUCCESS}]●[/]"
SYM_PEND = f"[{C_TERTIARY}]○[/]"
SYM_WARN = f"[bold {C_WARN}]▲[/]"
SYM_SKIP = f"[{C_TERTIARY}]—[/]"
SYM_NEXT = f"[bold {C_ACTION}]→[/]"
```

---

## 8. Anti-Pattern Checklist (The CLI Slop Test)

Adapted from Impeccable's "AI Slop Test." Before shipping any command's output,
ask:

> If you showed this terminal output to an engineer and said "an AI wrote the
> code that produces this," would they believe you immediately?

The CLI slop fingerprints to avoid:

- [ ] **Everything is the same gray.** If you squint and all non-bold text
      blends into one brightness band, you have a hierarchy problem.
- [ ] **Every section is in a box.** One hero panel max. Most commands need
      zero panels.
- [ ] **Labels and values are the same brightness.** Labels recede. Values
      stand out. Always.
- [ ] **Long explanations on status lines.** If a check result wraps to a
      second line, it's too long. Drop it to a new indented line or truncate.
- [ ] **Repetitive messages.** If the same explanation appears 3+ times
      (like "skipped because SSH not configured"), compress it into a short
      parenthetical.
- [ ] **Color everywhere.** If more than 3 things on screen are colored
      (besides the state symbols), you're over-coloring.
- [ ] **No breathing room.** If every line is content with no blank lines, the
      eye can't find landmarks. One blank line between sections.
- [ ] **Dim suggestions with no action cue.** Suggestions after errors need a
      `→` prefix to feel actionable, not just quiet gray text.

---

## 9. Implementation Priority

This revision should be applied in this order:

1. **Update `display.py` color constants** — swap `dim`/`grey70` for the
   tinted neutral scale. This is 5 minutes of work and immediately improves
   every screen.

2. **Fix `kv()` contrast** — labels use `C_SECONDARY`, values use default
   (no markup). This fixes config show and all KV-heavy output.

3. **Fix `status_line()` with the long-detail drop** — add the
   `max_inline_detail` threshold. This fixes doctor's long lines.

4. **Compress skipped messages** — short parenthetical instead of full
   sentence. This reduces noise in doctor.

5. **Add `→` prefix to suggestion lines** — reuse the action pattern. This
   makes error recovery feel guided.

6. **Tune hex values on real terminal** — the `#8a9bae` / `#5e6d7e` / `#44515e`
   values are starting points. They need to be tuned for the team's actual
   terminal theme (likely a dark theme on Windows Terminal). If the team uses a
   light terminal theme, these need to be inverted (darker tinted grays).

---

## 10. Summary: What Changed from V1 Plan

| V1 Plan Said                          | This Revision Says                        |
|---------------------------------------|-------------------------------------------|
| Use `dim` for labels                  | Use `C_SECONDARY` (tinted gray) for labels|
| Use `grey70` for secondary text       | Use `C_TERTIARY` (tinted gray, darker)    |
| Rule lines use `dim`                  | Rule lines use `C_FAINT` (barely visible) |
| Values are default color              | Values are default color (**unchanged**)  |
| Status detail always on same line     | Drop long details to indented next line   |
| Suggestions in dim text               | Suggestions with `→` prefix in tertiary   |
| Repeated skip reasons in full         | Compressed to short parenthetical         |
| Two brightness levels (bold + dim)    | Five visual tiers (T1-T5)                 |
| Generic gray palette                  | Cyan-tinted neutral palette               |

The layout, structure, and primitive function signatures from V1 are all
correct and unchanged. This revision only changes the **color palette** and
**text placement rules** within those primitives.
