# Facilitating the Postmortem Review Meeting

Read this when the user asks for help running, preparing, or improving the
review meeting, or wants an agenda, an invite, or opening remarks. The meeting
exists to deepen the analysis and get agreement on action items. It is not
where the document gets written or the timeline gets read aloud.

Contents: before the meeting, roles, agenda, opening, questioning techniques,
handling hard moments, remote meetings, after the meeting.

## Before the meeting

- **Hold it soon.** Aim for within about a week of resolution, while memory is
  fresh. Give large incidents a few days so the draft is substantially complete.
- **Circulate a complete draft at least a day ahead.** Timeline, impact, and
  proposed factors and actions should all be there. Ask attendees to read it
  and comment beforehand, so the meeting can spend its time on disagreements
  and gaps.
- **Invite the people who hold the facts and the people who own the fixes.**
  That means the responders, the incident commander, the owners of the systems
  involved, an engineering manager who can commit capacity for action items,
  and a product or customer-facing representative when customers were
  affected. Keep it small enough for real discussion, roughly 4 to 10 people.
  Open a separate session for observers if many want to attend.
- **Book enough time.** 45 to 60 minutes covers most incidents. Major,
  multi-team incidents may need 90 minutes or two sessions.
- **Note in advance who might feel exposed**, such as whoever made the change or
  ran the command. Talk to them beforehand. Tell them how the meeting will run,
  and that the analysis is about the system.

## Roles

| Role | Who | Responsibility |
|---|---|---|
| Facilitator | Someone not directly involved in the incident, ideally trained or experienced. Not the most senior person in the room, and not the manager of the responders. | Run the agenda, keep it blameless, draw out quiet voices, protect the timebox. Hold back their own opinions on causes and fixes. |
| Postmortem owner | The document's author | Present the summary, take changes back into the doc, own follow-through |
| Note-taker | Anyone other than the facilitator | Capture corrections, new factors, disagreements, and agreed actions with owners |

## Agenda (60 minutes)

| Time | Item |
|---|---|
| 0:00 to 0:05 | Opening and ground rules (see below) |
| 0:05 to 0:10 | Owner summarizes impact and the shape of the incident. Don't read the document aloud. |
| 0:10 to 0:30 | Walk the key decision points of the timeline. Focus on what people saw and why their choices made sense. Correct the record. |
| 0:30 to 0:45 | Contributing factors: what is missing, and what is mislabeled? Take detection and response as seriously as the trigger. |
| 0:45 to 0:55 | Action items: check that each maps to a factor, and agree priority, owner, and due date. Note items deliberately not taken. |
| 0:55 to 1:00 | Lessons worth sharing beyond the team. Confirm next steps and the publication date. |

## Opening the meeting

Say the ground rules out loud, every time, even with a team that has heard them
before. A short version in your own words:

> We're here to understand how this happened and how to make the system safer.
> We assume everyone acted reasonably with the information, time, and tools
> they had. Nothing said here will be used to evaluate anyone. If you notice us
> drifting toward who should have done what, call it out, and we'll steer back
> to what made that hard.

Then remind people that hindsight makes the right answer look obvious, and that
the useful question is what made it not obvious at the time.

## Questioning techniques

- **Walk forward through decision points** rather than backward from the
  cause. At each point ask: what were you seeing, what did you expect, what
  options did you have, what made you pick this one?
- **Ask "what" and "how" rather than "why did you".** "What made rolling back
  feel risky at that point?" gets an explanation. "Why didn't you roll back?"
  gets a defense.
- **Probe for surprises.** "What surprised you?" and "When did your
  understanding change?" often find the gaps in mental models that matter most.
- **Look for the normal work.** Ask how the task usually goes when nothing
  breaks. The incident often shows a workaround everyone relies on.
- **Look for the "almost".** "What nearly made this worse?" leads to the
  where-we-got-lucky list.
- **Get several accounts.** Different responders saw different slices. Note
  where accounts conflict instead of forcing one consensus story. A conflict
  often points to a confusing signal.

The individual interview questions in `evidence-gathering.md` work here too.

## Handling hard moments

| Situation | What to do |
|---|---|
| Someone assigns blame ("X should have...") | Redirect to the conditions: "Let's look at what X was seeing at that point. What would have made the other option visible?" |
| Someone blames themselves | Thank them for the openness, then widen the view: "Anyone in that seat with that dashboard could have made the same call. What would have helped?" Follow up privately afterwards. People involved in serious incidents often carry real stress about it. |
| A senior person dominates or announces the cause early | Acknowledge it as one hypothesis, then explicitly ask others what they saw before converging: "Before we settle on that, what else had to be true?" |
| Discussion turns into designing the fix | Capture it as a candidate action item, give it an owner to work up, and return to the agenda. Detailed design happens elsewhere. |
| Disagreement on facts | Note both versions and assign someone to check the evidence after the meeting. Don't settle facts by seniority or vote. |
| A team is defensive about its system | Restate that every factor is a property of the overall system, including the parts other teams own, and that action items will land where the leverage is, not where the fault was. |
| Too many action items | Ask which three, if done, would most reduce the chance or impact of a recurrence. Move the rest to "considered" or the backlog, and say so explicitly. |
| An action item gets no owner | Don't leave the meeting with it unowned. The engineering manager present assigns it, or it's recorded as "not taken" with a reason. |

## Remote and hybrid meetings

- Share the document on screen and have the note-taker edit it live, so
  corrections are visible.
- Use round-robin prompts ("let's hear from each responder on this decision")
  so quieter people get a turn instead of having to interrupt.
- Keep a written side channel for anyone who'd rather type a sensitive point.
  Check it at each agenda transition.
- Ask before recording. Recordings make many people more guarded, so for most
  teams written notes are enough.

## After the meeting

- Update the document within a day or two: corrections, new factors, the agreed
  action items, and the review record.
- File every action item in the owning team's tracker and link it from the
  document. The postmortem is a record, not a task tracker.
- Publish where the organization expects postmortems to live, and announce it
  to the people who can learn from it, beyond the team involved.
- Put open action items on the team's regular planning agenda until they're
  closed. Unfinished action items are the most common way the same incident
  happens twice.
- For significant incidents, consider a short write-up or reading-group session
  for the wider engineering organization. Other people's incidents are a cheap
  way to learn.
