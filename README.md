# jobprep-kit

A job-application pipeline you run inside [Claude Code](https://claude.com/claude-code).
One command evaluates a role, tailors your resume honestly, scores the keyword
match, drafts warm-path outreach, and logs everything to a local dashboard.

Born from a real search: ~100 tracked applications taught this system that
keyword match past the mid-80s buys nothing, that referrals convert several
times better than cold applies, and that funnel math lies unless you track the
furthest stage reached, not just current status. Those lessons are baked in.

## What you get

- **`/jobprep-setup`** - a one-time interview that captures your career history,
  hard constraints, and writing rules into a local `profile/` folder. This is
  the system's only source of personal context. It never leaves your machine.
- **`/jobprep <job URL or JD>`** - the full pipeline: fit score, base-resume pick,
  keyword baseline, honest tailoring, recruiter gut-check, PDF, warm-path
  outreach draft, funnel logging.
- **`funnel/funnel.py`** - a zero-dependency local dashboard (Python stdlib only).
  Conversion funnel, status distribution, weekly volume, inline editing.
- **`tools/match.py`** - a free ATS-style keyword scorer. No accounts, no APIs.

## Quickstart (5 minutes)

```bash
git clone https://github.com/vamsikrishna6891/jobprep-kit.git
cd jobprep-kit
claude                      # open Claude Code in the repo
```

Then, inside Claude Code:

1. `/jobprep-setup` - answer the interview (~20 questions, one time).
2. `/jobprep <paste a job URL or the JD text>` - prep your first application.
3. `python3 funnel/funnel.py` - open the dashboard at http://localhost:8000.

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
- The only network access is Claude Code fetching job descriptions you give it.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.9+ (standard library only)
- Google Chrome (for HTML-to-PDF rendering)
- `pdftotext` (optional, for PDF audits: `brew install poppler` / `apt install poppler-utils`)

## Layout

```
.claude/commands/   jobprep.md, jobprep-setup.md   the pipeline
profile/            YOUR context (gitignored), see profile.example.md
applications/       one folder per company (gitignored)
funnel/funnel.py    local dashboard + funnel.sqlite (gitignored)
tools/match.py      keyword scorer
```

## License

MIT
