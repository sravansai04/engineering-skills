# Design direction template

Copy the template below into the repo (where the project keeps design or architecture docs; if
there is no such place, `docs/design-direction.md`) or, for a throwaway prototype, into a comment
block at the top of the token file. Fill it before writing component code. A filled example for a
fictional product follows the template.

Keep it short. A direction that takes ten minutes to read will not be followed; one page that a
reviewer can check a screenshot against will.

---

```markdown
# Design direction: <product / surface>

Status: draft | agreed on <date> by <who>
Mode: author | consolidate | conform (conform rarely needs this document)

## 1. Brief
- Surface and its primary job:
- Primary user, and what they are doing when they open it (frequency, device, environment):
- Context dial: density <high/med/low>, expressiveness <low/med/high>, color budget, motion budget
- Fixed constraints: brand colors/fonts/logo, existing components to reuse, platforms,
  themes (light/dark/high contrast), locales and right-to-left, smallest viewport
- Content realities: longest names/labels, largest numbers, empty first-run state, max rows/items
- Assumptions made (anything not confirmed by the user):

## 2. Concept
- In one sentence: <qualities> because <reason rooted in the subject or the audience>.
- Signature decision (the element a returning user would recognize first, and which budget it gets):
- Deliberately not doing:

## 3. Swap test
- If a competitor's name replaced ours, what in this plan would feel wrong for them?
  (If the answer is "nothing", the plan is still generic. Revise before building.)
- Default version of this UI (what you would build with no brief at all), in two lines:
- Where this plan differs, and why (any axis where the Default and This direction columns match
  needs a stated reason or a change):

| Axis | Default | This direction | Why |
|---|---|---|---|

## 4. Decisions

| Axis | Decision | Rationale | Tokens |
|---|---|---|---|
| Typeface(s) and roles | | | font-* |
| Type scale (base, ratio, steps) | | | text-* |
| Line height / measure | | | leading-*, max-width |
| Spacing (base, steps) | | | space-* |
| Color: neutrals, accent, status | | | palette-*, color-* |
| Data visualization: categorical, sequential, diverging, chart chrome (if any charts) | | | chart-cat-*, chart-seq-*, chart-div-*, chart-grid |
| Dark mode approach | | | (per-theme semantics) |
| Shape: radius personality, scale; focus ring | | | radius-*, focus-ring-width, focus-ring-offset |
| Separation device and elevation levels | | | shadow-*, border-* |
| Motion: purposes, durations, easing | | | duration-*, ease-* |
| Layout: grid, max width, breakpoints | | | breakpoint-*, container-* |
| Iconography: set, sizes, stroke | | | icon-size-* |
| Imagery / illustration (if any) | | | |
| Voice of microcopy (labels, errors, empty states) | | | |

## 5. Tokens
- Source file(s):
- Tiers: primitives -> semantic -> (component, if any)
- Themes defined:

## 6. Components and states
| Component | Variants | States covered (default, hover, focus-visible, active, selected, disabled, loading, error, empty) |
|---|---|---|

## 7. Verification plan
- Contrast pairs file: <path>, resolving tokens from <token css> (run scripts/token-contrast.mjs; one group per theme)
- Hard-coded value scan: `scan-hardcoded.mjs --changed` (base <branch>), plus the native grep if native code changes
- Screenshot matrix: widths <320, 768, 1280, ...> x themes <light, dark> x states <...>
- Open questions:
```

---

## Filled example (fictional)

```markdown
# Design direction: Front-desk board for a veterinary clinic scheduling app

Status: draft
Mode: author

## 1. Brief
- Surface and job: the day board receptionists keep open all day to check patients in, see who is
  waiting, and spot overruns.
- User: receptionists at a shared desktop and a counter tablet, glancing between phone calls,
  often across the desk at arm's length; dozens of check-ins per hour at peak.
- Context dial: density high, expressiveness low, color budget = neutrals + one accent + status,
  motion = feedback only.
- Constraints: clinic brand teal (#0f766e) must appear; light and dark (night clinics);
  English and Spanish; smallest viewport 768px tablet, but must not break at 320.
- Content realities: pet names up to ~24 chars plus owner surname; 60+ appointments on busy days;
  wait times up to 3 digits of minutes.
- Assumptions: no illustration budget; system fonts acceptable to the client.

## 2. Concept
- Calm, legible-at-a-distance, and time-honest, because staff read it in glances while doing
  something else and a late patient must never hide.
- Signature decision: wait time is the hero typographic element of each row, set large in tabular
  figures, shifting from neutral to warning to danger as it grows. It takes the type and color
  budget; names, species, and actions use the base text steps and neutrals.
- Not doing: cards per appointment, pet illustrations, decorative brand gradients.

## 3. Swap test
- A salon's booking board would not lead every row with overrun minutes or carry a species and
  owner column; the plan is specific to this clinic's job.
- Default version: a white page with a card grid of appointments, blue primary buttons,
  rounded-xl everywhere, a big "Good morning!" header.

| Axis | Default | This direction | Why |
|---|---|---|---|
| Structure | Card grid | Single dense table, sticky time column | Scanning 60 rows needs alignment, not cards |
| Emphasis | Pet name bold | Wait time large, tabular | The decision staff make is "who is waiting too long" |
| Color | Blue accent, colored badges | Teal accent for actions only; status colors only on wait time | Color means something; less noise at a glance |
| Header | Greeting | Clock, counts per state | Information over pleasantry |

## 4. Decisions (excerpt)
| Axis | Decision | Rationale | Tokens |
|---|---|---|---|
| Typeface | System UI stack; tabular figures for times | Fast, familiar, excellent small sizes | font-ui |
| Type scale | 15px base, ratio 1.2, 6 steps; wait time 24px semibold | Dense but readable at arm's length | text-* |
| Spacing | 4px base; row height 44px (tablet tap) | Touch on the counter tablet | space-*, row-height |
| Color | Neutral ramp tinted 2% toward teal; accent teal 600/700; status amber/red only for waits | Brand present, restrained | color-* |
| Dark | Surfaces step lighter by elevation; accent at teal 400 | Night clinics; contrast held | per-theme semantics |
| Shape | Softened: radius 6px controls, 0 on table rows | Quiet, tabular | radius-* |
| Motion | 120ms state fades; new arrivals highlight once for 1.5s; none with reduced motion | Notice without distraction | duration-*, ease-* |
```
