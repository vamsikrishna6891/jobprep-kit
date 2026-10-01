# jobprep-kit

A job-application pipeline you run inside [Claude Code](https://claude.com/claude-code).
One command finds open roles that fit you, straight from company job boards.
A second evaluates a role, tailors your resume honestly, scores the keyword
match, drafts warm-path outreach, and logs everything to a local dashboard.

Born from a real search: ~100 tracked applications taught this system that
keyword match past the mid-80s buys nothing, that referrals convert several
times better than cold applies, and that funnel math lies unless you track the
furthest stage reached, not just current status. Those lessons are baked in.

## What you get

- **`/jobprep-setup`** - a one-time interview that captures your career history,
  hard constraints, and writing rules into a local `profile/` folder. This is
  the system's only source of personal context. It never leaves your machine.
- **`/jobhunt`** - finds open roles for you. Scans about 150 company job boards
  directly, filters on your titles, locations, pay floor, and visa needs, skips
  anything already in your funnel, then ranks the survivors against your profile.
- **`/jobprep <job URL or JD>`** - the full pipeline: fit score, base-resume pick,
  keyword baseline, honest tailoring, recruiter gut-check, PDF, warm-path
  outreach draft, funnel logging.
- **`funnel/funnel.py`** - a zero-dependency local dashboard (Python stdlib only).
  Conversion funnel, status distribution, weekly volume, inline editing.
- **`tools/match.py`** - a free ATS-style keyword scorer. No accounts, no APIs.
- **`tools/source.py`** - the job-board scanner behind `/jobhunt`. No accounts,
  no API keys, no LLM tokens.

## Quickstart (5 minutes)

```bash
git clone https://github.com/vamsikrishna6891/jobprep-kit.git
cd jobprep-kit
claude                      # open Claude Code in the repo
```

Then, inside Claude Code:

1. `/jobprep-setup` - answer the interview (~30 questions, one time).
2. `/jobhunt` - get a ranked table of open roles, then say `prep 1`.
   Or skip the search: `/jobprep <paste a job URL or the JD text>`.
3. `python3 funnel/funnel.py` - open the dashboard at http://localhost:8000.

## Where /jobhunt looks

Most people only search LinkedIn. Most companies post to their own job board
first, and those boards have public feeds. `/jobhunt` reads the feeds directly,
so you see roles the day they open, with the pay range the company posted.

| Platform | How it is covered |
|----------|-------------------|
| Greenhouse | Per company, full board, structured pay ranges |
| Ashby | Per company, full board, structured pay ranges |
| Lever | Per company, full board, structured pay ranges |
| Workday | Per company, searched with your first 12 title phrases, up to 100 results each (Workday has no full feed) |
| Workable | Per company, full board |
| SmartRecruiters | Per company, full board |
| YC (Work at a Startup) | Every YC company at once, by role family, newest postings |

Not covered: LinkedIn, Indeed, and company-built career sites (Google, Meta,
Apple, Amazon, Microsoft). Those have no public feed. Check them by hand.

The scanner reads one company board at a time, so it only sees companies on its
list. The starter list in `tools/companies.json` is about 150 companies and leans
toward US tech. Two things make the list yours:

**Discovery.** On your first `/jobhunt`, and every two weeks after, Claude searches
each platform for your titles in your locations
(`site:boards.greenhouse.io "data scientist" austin`), takes the companies behind
the results, and adds every one whose board is live. A data scientist in Austin and
a product manager in Berlin end up scanning different companies. Run
`/jobhunt discover` to do it on demand.

**By name.** Add a target in one line:

```bash
python3 tools/source.py --add "Company Name"
```

It finds the board, prints the link so you can confirm it is the right company,
and saves it to `profile/companies.json`. A board it cannot find can be added by
hand, see `.claude/commands/jobhunt.md`.

What gets filtered, all from `profile/search.json`:

- Title must match one of your phrases and none of your excluded words.
- Location must be one of your places, or remote in a region you can work from.
  A posting listed only as a country you accept ("United States") is kept, because
  boards often list remote roles that way. Read the JD before you trust it.
- The top of the posted base range must reach your floor. Roles with no posted
  range are kept or dropped, your choice. Ranges described as total compensation,
  on-target earnings, bonus, or equity do not count as base. USD only.
- Posting must be newer than your age limit. Workday shows older roles as
  "30+ days ago" with no real date, so those are dropped.
- If you need sponsorship, postings that say they will not sponsor are dropped.
- A role already in your funnel is skipped. A rejected one comes back after 90 days,
  flagged as a reapply.

Every on-target role a filter dropped is written to `sourcing/<date>/excluded.jsonl`
with the reason, so you can see what a setting is costing you. The one exception is
roles you skipped yourself, which are left out quietly. When a company lists the same
title twice, only the first is kept and the second is logged there.

## Principles (why it works)

1. **Honesty is load-bearing.** Every resume claim must trace to the claims
   ledger you built during setup. The pipeline refuses to invent metrics,
   inflate titles, or add tools you never used. A tailored resume you cannot
   defend in an interview is worse than no application.
2. **80/85 rule.** Keyword match below 80% means tailor more. Above 85%, stop:
   real funnel data shows rejected applications averaged a HIGHER keyword match
   than successful ones past that point. The marginal hour goes to finding a
   referral instead.
3. **Warm paths beat cold applies.** Every prep ends with a hiring-manager /
   referral search and one drafted outreach note. You send it manually.
4. **Track stage_reached, not just status.** A rejection after three interviews
   is a very different signal than a rejection after silence. The funnel keeps
   both, so your conversion numbers stay true.
5. **Learn from your own funnel.** After ~20 applications the pipeline computes
   YOUR conversion rate per role archetype and raises the bar on the ones that
   underperform. No borrowed benchmarks.

## Privacy

- `profile/` and `applications/` are gitignored. Your history, constraints, and
  resumes stay local.
- The dashboard binds to 127.0.0.1 and has no external calls.
- The keyword scorer is offline.
- Network access is limited to two things: Claude Code fetching job descriptions
  you give it, and `tools/source.py` reading public job-board feeds. The scanner
  requests each board and filters on your machine. The one thing it sends is your
  title phrases, as the search text for Workday boards only. Discovery also runs
  web searches for your titles and locations. Nothing else from your profile
  leaves your machine.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.9+ (standard library only)
- Google Chrome (for HTML-to-PDF rendering)
- `pdftotext` (optional, for PDF audits: `brew install poppler` / `apt install poppler-utils`)

## Layout

```
.claude/commands/     jobhunt.md, jobprep.md, jobprep-setup.md   the pipeline
profile/              YOUR context (gitignored), see profile.example.md
                      and search.example.json
applications/         one folder per company (gitignored)
sourcing/             one folder per /jobhunt run (gitignored)
funnel/funnel.py      local dashboard + funnel.sqlite (gitignored)
tools/match.py        keyword scorer
tools/source.py       job-board scanner
tools/companies.json  starter list of company boards
tools/test_source.py  offline tests: python3 tools/test_source.py
```

## License

MIT
