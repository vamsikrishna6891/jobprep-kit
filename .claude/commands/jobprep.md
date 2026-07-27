# /jobprep -- Evaluate a role, build a tailored resume, score it, log it

One trigger for the full apply-prep pipeline. Invoke as `/jobprep <job URL or pasted JD>`.

Prerequisite: `profile/profile.md` exists. If it does not, stop and run
`/jobprep-setup` first. The profile is the pipeline's only source of personal
context: never use facts about the user that are not in `profile/`.

Does three things in order: (1) evaluate fit, (2) build a tailored resume,
(3) score the match. Then logs the application to the funnel dashboard.

## Steps

1. **Get the JD + posting age.** Fetch the URL (WebFetch) or read the pasted text.
   If the page is auth-gated and fetch fails, ask the user to paste the JD.
   Find the posting date (page metadata, "posted X days ago", or search the req id).
   Reqs older than 14 days convert worse: flag it in the fit table and carry the
   date to the funnel log. Unknown date = say so, do not guess.

2. **Evaluate fit (verdict first).** Score 1-10 in a tight table: domain fit,
   title match vs target archetypes, comp vs floor, skills overlap, trajectory,
   posting age. Check the JD against every hard constraint in `profile/profile.md`
   (location, work authorization). A hard-constraint conflict the JD states
   explicitly = fit 0, verdict skip, full stop. Otherwise call out honest
   frictions (location, in-office, level, domain gaps). Recommend apply / skip / maybe.
   - **Learn from your own funnel.** Once the funnel has 20+ submitted rows, compute
     conversion by archetype before scoring:
     `sqlite3 funnel/funnel.sqlite "SELECT archetype, COUNT(*), SUM(CASE WHEN stage_reached IN ('screen','interview','onsite','offer') THEN 1 ELSE 0 END) FROM apps WHERE status != 'withdrawn' GROUP BY archetype;"`
     If an archetype converts at half the rate of another, say so plainly and
     raise the fit bar for it. Do not import anyone else's conversion numbers.

3. **Pick the base resume.** Choose the closest archetype resume in
   `profile/resumes/`. Do not start from scratch.

4. **Baseline score.** Save the JD as `applications/<company>/jd.txt`, then:
   `python3 tools/match.py applications/<company>/jd.txt profile/resumes/<archetype>.html`
   Note the baseline % and the ranked missing terms.

5. **Tailor the resume.** Copy the base to `applications/<company>/` and apply
   only honest rewrites: reframe existing ledger claims toward the JD's language,
   surface buried relevant work, reorder bullets. Every specific claim (numbers,
   scope words like "led" or "owned", "shipped to production") must trace to
   `profile/claims-ledger.md`. No fabrication. No new metrics. No retitling to
   match the JD. Claims marked `unverified:` are unusable. Honor every rule in
   `profile/writing-rules.md`.

6. **Recruiter gut-check (qualitative pass).** Read the tailored resume the way
   a recruiter scans 200 resumes in 10 seconds each. Report in a tight block:
   the first 3 things that stand out, what reads as generic, shortlist or pass,
   and the single change with the highest shortlist lift. If that change is an
   honest rewrite from ledger content, apply it now. Never invent a stronger
   number to patch a weak claim.

7. **Re-score and generate the PDF.** Re-run `tools/match.py` on the tailored
   resume. 80 is the floor. 85 is the ceiling: once you hit 85, STOP polishing
   keywords (past the mid-80s, more keyword match buys nothing; the warm path is
   where the time pays). Render the PDF with headless Chrome:
   `chrome --headless --no-pdf-header-footer --print-to-pdf=<out.pdf> <resume.html>`
   (macOS binary: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`).
   Verify: ~1 page, contact on one non-wrapping line, every writing-rules.md
   check passes on the RENDERED PDF (`pdftotext out.pdf -` then grep), not just the source.

8. **Warm path (optional module, highest-lift step).** Referral and
   hiring-manager-touched applications convert several times better than cold
   ones. If the profile says LinkedIn research is available:
   - Identify the likely hiring manager and any 1st/2nd-degree connections.
   - Output a tight block: HM name + title + profile URL (or "not found"), best
     bridge connection (or "none"), and ONE drafted outreach note (connection-request
     length, no public job-seeking signal, respecting any avoid-list in the profile).
   - The user sends it manually. NEVER send outreach automatically.
   - If unavailable or nothing found, say so in one line and move on.

9. **Log to the funnel (automatic, do not wait to be told).** Upsert into
   `funnel/funnel.sqlite`, table `apps(id, company, role, archetype, date, score,
   status, note, channel, posted_date, stage_reached)`:
   `sqlite3 funnel/funnel.sqlite "INSERT OR REPLACE INTO apps VALUES('<kebab-id>','<Company>','<Role>','<archetype>','<YYYY-MM-DD>',<score>,'prepped','<base used, baseline->final %>','cold','<posted-date-or-NULL>','applied');"`
   - `status` = where it sits NOW (prepped/applied/screen/interview/onsite/offer/rejected/withdrawn).
   - `stage_reached` = furthest stage EVER attained. Forward-only: a rejection
     flips status but leaves stage_reached at its peak. This split exists because
     conversion math on status alone erases every interview that later died.
   - When the user later says "applied" for a role, flip status without being asked.
     When they mention a recruiter call / interview / onsite, update BOTH status
     AND stage_reached without being asked.

10. **Report**: fit verdict, final match %, gut-check verdict + highest-lift
    change, warm-path block, top missing keywords, honesty flags (anything the
    JD wants that the ledger cannot support), file paths.

## File convention

- One folder per company: `applications/<company>/` (gitignored).
- Multiple roles at one company: `applications/<company>/<role-short>/`.
- Resume filename: `<Your-Name>-<Company>-<Role-Short>.{html,pdf}`.
- Always co-locate `jd.txt` and `match-<YYYY-MM-DD>.md` (the scorer output).

## Hard rules

- Score-first, score-after. A resume is not done without both runs. Floor 80, stop at 85.
- No fabrication. No retitling. Every claim traces to the ledger.
- The deny-list and work-authorization rules in the profile are absolute.
- The gut-check is diagnostic only: it may prompt honest rewrites, never new claims.
- Audit the rendered PDF against writing-rules.md, not just the HTML source.
- Funnel logging happens at prep time, every time, unprompted.
