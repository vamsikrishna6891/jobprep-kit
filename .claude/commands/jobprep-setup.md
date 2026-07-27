# /jobprep-setup -- One-time intake interview

Builds your personal profile so `/jobprep` can tailor resumes with YOUR context.
Run once before your first `/jobprep`. Re-run any section later to update.

Everything written here stays local in `profile/` (gitignored). Nothing is uploaded.

## How to run this interview

Ask the questions below conversationally, ONE SECTION AT A TIME. Do not dump all
questions at once. Follow up when an answer is vague. Push back on anything that
sounds inflated: the pipeline only works if the profile is honest.

After all five sections, write the output files (see "Outputs") and show the user
a summary for confirmation before saving.

## Section A: Identity and targets

1. Full name, city, phone, email, LinkedIn URL, portfolio/website (if any).
2. What job titles are you targeting? Group them into 2-4 archetypes
   (e.g. "Data Scientist", "Product Analyst", "ML Engineer"). Archetypes drive
   base-resume selection and let the funnel measure which type converts for you.
3. Seniority band (junior / mid / senior / staff / lead / manager)?
4. Location constraints: which metros, remote or onsite or hybrid, any hard "no" regions?
5. Compensation floor (a number below which you would not accept)? Never printed
   on any document. Used only to flag low-comp roles at fit-scoring time.
6. Work authorization: any constraints a job description could conflict with
   (visa sponsorship needed, security clearance, etc.)? If yes: should the resume
   avoid any specific words or facts? (Example: some visa holders avoid the word
   "Founder" or names of side businesses.) These become HARD RULES in writing-rules.md.

## Section B: Career history and the claims ledger

For EACH role, most recent first:
7. Employer, title, dates, location. Was the payroll title different from what
   you want on the resume? (Note both. Inflating a title is the user's call and
   risk; recording the truth here prevents accidental contradictions later.)
8. 3-6 concrete achievements. For each, ask: "What is the evidence?" Only claims
   the user can back in an interview go in the ledger. Numbers must be real.
9. Tech stack ACTUALLY used in that role. Do not let adjacent tools creep in.
   (If they watched a teammate use Spark, Spark does not go on the list.)
10. Any side projects or ventures? For each: what is honestly claimable
    (live URL? users? revenue?) and what must NOT be claimed?
11. Education, certifications.
12. Anything that must NEVER appear on a resume (dead projects, fabricated
    metrics from old resumes, employers under NDA)? This is the deny-list.

## Section C: Writing rules

13. Any punctuation or style bans? (Common: no em dashes because they read as
    AI-generated. Ask, do not assume.)
14. Resume length limit (default: 1 page under 10 years experience, 2 max).
15. Contact line format preference. Default: one single line, never wrapping.
16. Tone: plain and factual vs achievement-forward? Any words they hate?

## Section D: Base resumes

17. Collect their current resume file(s). Save one per archetype into
    `profile/resumes/<archetype>.html` (convert to clean HTML if given a PDF or
    docx: extract text faithfully, do not rewrite content during conversion).
18. If an archetype has no base resume yet, offer to build one FROM THE CLAIMS
    LEDGER ONLY. Every bullet must trace to a Section B answer.

## Section E: Channels and cadence

19. Can they use LinkedIn for warm-path research (finding hiring managers and
    mutual connections)? If yes, note that the warm-path step is available.
    Any network they must avoid signaling to (e.g. current employer)?
20. Weekly application target and any "auto-skip" filters (posting older than
    N days, specific companies, agencies/staffing firms)?

## Outputs

Write these files, then show a summary and confirm:

- `profile/profile.md` -- Sections A + E answers, structured with headers.
- `profile/claims-ledger.md` -- Section B. One block per role: title (payroll vs
  resume), dates, achievements each tagged `evidence:`, stack, deny-list at the bottom.
- `profile/writing-rules.md` -- Section C as a checklist the pipeline audits against.
- `profile/resumes/<archetype>.html` -- base resumes from Section D.

## Hard rules for the interviewer

- Never invent an answer the user did not give. Blank is better than guessed.
- If an achievement has no evidence, it goes in the ledger marked `unverified:`
  and the pipeline will not use it.
- The deny-list and work-authorization rules are non-negotiable once set: every
  future /jobprep run must honor them without being reminded.
