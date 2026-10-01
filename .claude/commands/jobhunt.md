# /jobhunt -- Find open roles that fit, ranked, ready for /jobprep

Pulls open roles straight from company job boards, filters them with the user's
search settings, ranks the survivors against their profile, and shows the top hits.
Invoke as `/jobhunt`, or `/jobhunt 10` to change how many hits to show (default 5).
`/jobhunt discover` forces the company discovery step below.

Prerequisites: `profile/profile.md` and `profile/search.json` exist. If either is
missing, stop and run `/jobprep-setup` first (Section F writes `search.json`).

This command finds and ranks. It never applies, never sends outreach, and never
writes to the funnel. Tailoring is `/jobprep`.

## Steps

0. **Discover companies (some runs only).** The scanner reads one company board at
   a time, so it only sees companies on its list. This step grows that list to fit
   the user's own market. Run it when ANY of these is true, otherwise skip it:
   - `sourcing/discovery-log.jsonl` does not exist (first run).
   - Its last line is dated more than 14 days ago.
   - The user typed `/jobhunt discover`.

   How:
   - Read `profile/search.json`. Take the 3 title phrases that best describe the
     user's target (drop any trailing `*`), their first 2 locations, and "remote"
     if `remote` is true.
   - Web search each platform for those titles and places, restricted to the
     platform's job domain. One search per platform per title, 18 searches at most.
     Example queries:
     `site:boards.greenhouse.io "data scientist" austin`
     `site:jobs.ashbyhq.com "data scientist" remote`
     `site:jobs.lever.co "product analyst" austin`
     `site:apply.workable.com "data scientist" texas`
     `site:jobs.smartrecruiters.com "data scientist" austin`
     `site:myworkdayjobs.com "data scientist" austin`
   - Collect every result URL, whatever the posting says. Do not judge the roles
     here. A stale posting still reveals a company that hires for this title.
   - Pass all the URLs to the scanner in one call:
     `python3 tools/source.py --add-url "<url1>" "<url2>" ...`
     It works out each company's board, keeps only boards that are live and not
     already scanned, and saves them to `profile/companies.json`.
   - Tell the user in one line how many companies were added, and name them.
   - If web search is unavailable, say so in one line and continue with step 1.
     Never invent a company or a board id.

1. **Source.** Run `python3 tools/source.py`. It takes a few minutes and uses no
   LLM tokens. Read the one-line summary it prints.
   - Any `board error` line: report it in one line at the end. Do not retry.
   - `candidates=0`: do not relax a filter on your own. Read
     `sourcing/<date>/excluded.jsonl`, tell the user the top three drop reasons
     with counts, and ask which setting to loosen.

2. **Shortlist from titles.** Read `sourcing/<date>/candidates.json`. From title,
   company, location, pay, and flags alone, pick up to 15 worth a full read.
   Prefer titles closest to the user's most recent title and target archetypes in
   `profile/profile.md`. A recruiter's first check is title match.

3. **Read and score.** For each shortlisted role, read `sourcing/<date>/jd/<key>.txt`
   and score 1-10 the same way `/jobprep` step 2 does: domain fit, title match,
   comp vs floor, skills overlap, trajectory, posting age. Use only facts in
   `profile/`. Check every hard constraint in `profile/profile.md`. A conflict the
   JD states explicitly = score 0, drop it, and say why in one line.
   - If the funnel has 20+ submitted rows, apply the per-archetype conversion
     check from `/jobprep` step 2 before scoring.

4. **Show the top hits.** One table, best first:

   | # | Company | Role | Location | Base pay | Posted | Fit | Biggest gap |

   - Base pay: the posted range, or "not posted". Never guess a number.
   - Under the table, list any flags from `candidates.json` per role
     (`REAPPLY`, `ACTIVE-AT-COMPANY`, `PRIOR-AT-COMPANY`) and the apply URL.
   - Then one line: boards scanned, postings fetched, candidates, board errors.

5. **Wait for the user.** They answer with any of:
   - `prep N` -> run `/jobprep sourcing/<date>/jd/<key>.txt` for that role. The
     file starts with Company, Title, Location, URL, Posted, and Pay lines, so
     nothing needs refetching. Carry the Posted date to the funnel log.
   - `skip N` -> append that role's URL to `sourcing/skipped.json` (a JSON list of
     URL strings, create it if missing). It will not be shown again.
   - `more` -> show the next 5 from the scored shortlist.

## Adding companies

The starter list in `tools/companies.json` leans toward US tech companies. Step 0
adds companies that hire for the user's titles in their market. When the user names
a specific company that is not being scanned:

`python3 tools/source.py --add "Company Name"`

It guesses the board id from the name and prints the board link. Tell the user to
open the link and confirm it is the right company, since two companies can share a
name. If nothing is found, look at the URL of any job on the company's careers
page and pass the board directly:

| Job URL contains | Command |
|---|---|
| `boards.greenhouse.io/acme` or `job-boards.greenhouse.io/acme` | `--add "Acme" --board greenhouse:acme` |
| `jobs.ashbyhq.com/acme` | `--add "Acme" --board ashby:acme` |
| `jobs.lever.co/acme` | `--add "Acme" --board lever:acme` |
| `apply.workable.com/acme` | `--add "Acme" --board workable:acme` |
| `jobs.smartrecruiters.com/Acme` | `--add "Acme" --board smartrecruiters:Acme` |
| `acme.wd5.myworkdayjobs.com/en-US/External/...` | `--add "Acme" --board "workday:acme.wd5.myworkdayjobs.com\|acme\|External"` |

User additions live in `profile/companies.json` (gitignored) and override the
starter list. To stop scanning a starter company, set it to an empty list there:
`{"Acme": []}`.

## Hard rules

- Never relax a filter silently. Fewer than the requested number of hits: show
  what passed and say how many.
- Never invent pay, posting dates, or sponsorship status. Missing = "not posted".
- Discovery adds companies only through `tools/source.py`, which checks each board
  is live. Never write to `profile/companies.json` by hand from search results.
- Rank on the profile only. No facts about the user from outside `profile/`.
- No applying, no outreach, no funnel writes from this command.
