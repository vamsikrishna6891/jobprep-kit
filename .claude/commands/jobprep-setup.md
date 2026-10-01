# /jobprep-setup -- One-time intake interview

Builds your personal profile so `/jobprep` can tailor resumes with YOUR context.
Run once before your first `/jobprep`. Re-run any section later to update.

Everything written here stays local in `profile/` (gitignored). Nothing is uploaded.

## How to run this interview

Ask the questions below conversationally, ONE SECTION AT A TIME. Do not dump all
questions at once. Follow up when an answer is vague. Push back on anything that
sounds inflated: the pipeline only works if the profile is honest.

After all six sections, write the output files (see "Outputs") and show the user
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

## Section F: Job search settings (for /jobhunt)

Most of this is already answered in Sections A and E. Confirm it, do not re-ask it.

21. Title phrases to search for, per archetype from question 2. Plain phrases, any
    case. End a phrase with `*` to match a prefix (`product analy*` catches Analyst
    and Analytics). Ask for near-synonyms recruiters use for the same job.
22. Title words that rule a role out (intern, director, contract, and so on).
    Seniority from question 3 drives the defaults: propose them, let the user edit.
23. Locations from question 4 as short place names (city, state, region). Remote
    yes or no. If yes, which regions they can legally work from. Empty regions
    means any remote role anywhere.
24. Base pay floor for search. Explain it is checked against the TOP of the posted
    base range, and that total comp is usually higher than base. Then ask: keep or
    drop roles that post no pay range? Default keep.
25. From question 6: do they need visa sponsorship? If yes, postings that state
    they will not sponsor are dropped.
26. How fresh: maximum posting age in days (default 30).
27. Any target companies they want scanned? For each one not already in
    `tools/companies.json`, run `python3 tools/source.py --add "<name>"` and have
    the user confirm the board link it prints. Tell them the first `/jobhunt` also
    discovers companies that hire for their titles in their locations.
28. Optional: YC startup jobs. If interested, which role families
    (software-engineer, designer, product-manager, recruiting-hr, sales-manager,
    marketing, support, operations, science).

## Outputs

Write these files, then show a summary and confirm:

- `profile/profile.md` -- Sections A + E answers, structured with headers.
- `profile/claims-ledger.md` -- Section B. One block per role: title (payroll vs
  resume), dates, achievements each tagged `evidence:`, stack, deny-list at the bottom.
- `profile/writing-rules.md` -- Section C as a checklist the pipeline audits against.
- `profile/resumes/<archetype>.html` -- base resumes from Section D.
- `profile/search.json` -- Section F, in the exact shape of
  `profile/search.example.json` (same keys, no others, drop the `_` comment keys).
  Then run `python3 tools/source.py` once to prove the file loads and show the
  user how many candidates their settings produce.

## Hard rules for the interviewer

- Never invent an answer the user did not give. Blank is better than guessed.
- If an achievement has no evidence, it goes in the ledger marked `unverified:`
  and the pipeline will not use it.
- The deny-list and work-authorization rules are non-negotiable once set: every
  future /jobprep run must honor them without being reminded.
