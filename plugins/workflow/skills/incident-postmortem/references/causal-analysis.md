# Causal Analysis and Blameless Language

Read this in step 7 when working through contributing factors, in step 9 when
strengthening action items, and in step 11 when rewriting the draft into
blameless language. SKILL.md has the rules; this
file has the question bank, a worked causal tree, and the rewrite table.

Contents: probing questions by category, branching why/how tree, reconstructing
local rationality, reframing "human error", weak-to-strong action items,
blameless rewrite table.

## Probing questions by category

Go through every category, even when the cause seems obvious. One obvious cause
is exactly when the others get skipped. A category with no factor is fine, as
long as you looked.

**Trigger and change**
- What changed in the hours or days before impact: code, config, flags,
  infrastructure, dependencies, data, traffic, people on call?
- Was the change itself faulty, or was it a normal change that met an abnormal
  condition?
- How was it rolled out (all at once, canary, staged), and why didn't the
  rollout catch it?

**Design and latent conditions**
- Which conditions were present long before the trigger and only mattered
  once it arrived? Examples: missing timeouts, unbounded retries, shared
  resource pools, single points of failure, capacity headroom eroded by growth.
- What limited the blast radius, and what failed to limit it?
- Were there safety mechanisms (rate limits, circuit breakers, quotas,
  validation) that were absent, misconfigured, or bypassed?

**Detection**
- Which signal first showed the problem, and how long before a human acted?
- Did an alert fire? If not, which alert would have, and why didn't it exist or
  why was its threshold or window too loose?
- Did the alert reach the right person with enough context to act?
- Was the first report from a customer or a colleague? Then monitoring missed it.

**Response and diagnosis**
- Which hypotheses were tried, in what order, and what evidence led to each?
- What made the real cause hard to see: missing dashboards, misleading metrics,
  noisy logs, a "known" error that was really new?
- Did the runbook exist, was it found, and was it right?
- Were the right people reachable? Were escalation paths clear?
- Did anything about the response make things worse, such as a mitigation
  with side effects or coordination overhead?

**Recovery**
- Once the decision was made, how long did mitigation take? What made it slow
  or fast (rollback tooling, deploy time, cache warm-up, data repair)?
- Was a safe rollback available? Had it been exercised recently?

**Process and review**
- Which reviews, tests, or checks did the change pass, and what did they not
  cover?
- Did any process encourage the risky path (deadline pressure, a review
  checklist that didn't fit, an approval nobody could meaningfully evaluate)?

**Organizational context**
- Ownership: was it clear who owned the failing component and its alerts?
- Load: on-call burden, alert fatigue, staffing, time of day, concurrent
  incidents.
- Knowledge: was relevant knowledge held by one person? Was documentation
  current?
- Priorities: had a known risk been accepted or deferred? By what process?

**External dependencies**
- Which third-party or other-team dependency was involved? How did our system
  behave when it degraded (timeouts, fallbacks, caching, queueing)?
- How did we learn about their problem: our monitoring, their status page, or
  customers?

**History**
- Has this, or something close, happened before? Were the earlier action items
  completed? If they weren't, why not? That answer is usually organizational and
  usually the most important finding.

## A branching why/how tree

A single chain of five "whys" tends to follow whichever branch the questioner
finds most interesting, and stops at one cause. Branch at every level instead,
asking both "why did this happen?" and "what else had to be true for it to
matter?". This tree is the analysis behind `example-postmortem.md`, and its
CF IDs match that document.

```
Checkout failed for 38% of attempts for 47 minutes
│
├─ Why did requests fail?  orders-service exhausted its worker threads waiting on inventory
│   ├─ Why was inventory slow?  node replacement drained 1 of 3 replicas (routine, weekly)
│   │   └─ What else had to be true?  the remaining replicas had no headroom for a caller surge
│   │       └─ inventory had no per-caller limits or load shedding, and its capacity plan
│   │          covered losing one replica at normal load only                          → CF3
│   └─ Why so much load?  new retry policy retried 3x immediately, no backoff, no budget → CF1
│       ├─ How did it ship?  reviewed as client-only; load tests mock inventory, so nothing
│       │  exercised dependency latency                                                → CF4
│       ├─ How did canary miss it?  a 5% canary can't produce amplification; canary watched
│       │  only its own error rate and latency                                         → CF5
│       └─ What else had to be true?  a shared resilient client from an earlier retry storm
│          existed, but adoption was optional and untracked                            → CF7
│
├─ Why 11 minutes to detect?  alert required >5% errors sustained for 10 minutes       → CF2
│   └─ What else had to be true?  the first customer ticket, 4 minutes earlier, had no
│      route to on-call                                                                → CF8
│
└─ Why 26 minutes from detection to the rollback decision?  responders scaled inventory
   first, because it looked like the bottleneck
    └─ What made the deploy hard to suspect?  no deploy markers or per-caller inbound-rate
       panels, and the runbook starts with capacity checks                             → CF6
```

Stopping rules for a branch:

- Stop when you reach a condition that an action item can change, and the
  change would prevent or limit this whole class of incident, not just this
  instance.
- Stop when the next answer lies outside anything the organization can
  influence ("the cloud provider replaced a node"). Then ask how the system
  should behave when that happens again.
- Never stop at a person. "Engineer X approved the change" is a point in the
  timeline. The branch continues with what made approving it reasonable.

## Reconstructing local rationality

For every decision in the timeline that looks wrong afterwards, write down:

1. **What they knew.** Which alerts, dashboards, messages, and prior experience
   they had.
2. **What they were trying to do.** Their goal at that moment, and the pressure
   they were under (time, customers, other incidents).
3. **What the system made easy or hard.** Defaults, tooling, UI, missing
   information, misleading signals.

If the decision still looks unreasonable after these three, you don't have the
full picture yet. Go back to the responder or the evidence. People rarely do
things that make no sense to them at the time.

## Reframing "human error"

Treat a mistake by a person as the place where an investigation starts, not
where it ends. Ask what made the error possible and what let it do so much
damage.

| Surface finding | Questions that lead to systemic factors |
|---|---|
| An engineer ran a command against production instead of staging | How do the two environments differ in the tooling? Is the target visible at the moment of running? Is there a confirmation or dry-run? Why does this task need direct production access at all? |
| A reviewer approved a risky change | What did the diff show? Could the risk be seen in the diff, or only by knowing the runtime behavior? Does review have a way to flag changes that need load testing? |
| On-call didn't see the alert for 20 minutes | How many alerts fired that shift? How is the page delivered? Was this one distinguishable from the routine noise? |
| A config value was mistyped | Is the config validated, typed, or schema-checked? Is it tested before rollout? Does it roll out gradually? |
| A runbook step was skipped | Was the step clear, current, and discoverable under pressure? Could it be automated? |

## Weak to strong action items

A weak item hopes people will behave differently. A strong one changes what the
system makes easy, names the factor it addresses, and says how "done" will be
checked. The examples refer to the incident in `example-postmortem.md`.

| Weak | Strong |
|---|---|
| Be more careful when changing retry settings | Add a CI check that fails on retry config without backoff or a retry budget (CF1) |
| Improve monitoring | Page on error-budget burn rate (1h and 5m windows at 14.4x), which pages about 2 minutes into a 38% error ratio instead of 11. Done when a replay of this incident's metrics pages within 3 minutes. (CF2) |
| Remind engineers to check recent deploys | Show deploy and flag-change markers on the service dashboards, and make "list changes in the last 72h" the first runbook step (CF6) |
| Tell support to escalate faster | Page on-call automatically when checkout-failure tickets cluster, and add a "page on-call" action to the support tool (CF8) |
| Look into inventory capacity | Investigate: how many inventory replicas hold weekday peak with one replica lost and retries at the new budget? Report back with a capacity plan by 2026-04-03 (CF3) |

## Blameless rewrite table

| Instead of | Write | Why |
|---|---|---|
| "Alex pushed a bad config." | "A config change set the pool size to 0. Validation accepted the value." | Describes the action and the gap that let it through. The person isn't the finding. |
| "The on-call engineer should have checked recent deploys." | "The runbook's first steps covered capacity checks. Recent deploys were not part of it, and the dashboard showed no deploy markers." | A counterfactual only says the outcome would have differed. It doesn't explain why the step didn't happen. |
| "The reviewer failed to notice the missing backoff." | "The diff changed a retry count. The load behavior was not visible in the diff, and no test exercised dependency latency." | "Failed to" judges in hindsight. The rewrite names what was and wasn't visible. |
| "Obviously the cache was the problem." | "In hindsight, the cache eviction graph showed the drop at 14:03. During the incident that panel was on a separate dashboard." | "Obviously" erases the uncertainty responders actually faced. |
| "Root cause: human error." | "Contributing factors: no guardrail on bulk deletes (CF1), production and staging prompts look identical (CF2)." | "Human error" can't be fixed by an action item. Its conditions can. |
| "Careless testing let this slip through." | "Integration tests mock the inventory client, so dependency latency is never exercised." | Character judgments end learning and teach people to hide mistakes. |
| "We need everyone to be more careful with migrations." | "Add a pre-deploy check that blocks migrations that take an exclusive lock on large tables (action 3)." | "Be careful" is a hope, not a control. |

On names: describe people by role ("the on-call engineer", "the incident
commander", "a reviewer") in the narrative, analysis, and lessons. Some teams
allow names in the timeline for traceability. Follow the team's existing
practice, but never put a name next to an error.
