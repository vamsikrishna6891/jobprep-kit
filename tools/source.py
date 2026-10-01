#!/usr/bin/env python3
"""Find open roles straight from company job boards. No accounts, no API keys, no LLM tokens.

  python3 tools/source.py                     fetch, filter, write sourcing/<date>/
  python3 tools/source.py --add "Company"     find a company's board and save it to profile/companies.json
  python3 tools/source.py --add "Company" --board workday:host|tenant|site
  python3 tools/source.py --add-url URL [URL ...]   save the boards behind any job links (used by /jobhunt discovery)

Reads  profile/search.json    what you are looking for (see profile/search.example.json)
       tools/companies.json   starter list of boards, merged with profile/companies.json (yours wins)
       funnel/funnel.sqlite   roles you already prepped or applied to are skipped
       sourcing/skipped.json  posting URLs you told /jobhunt to stop showing

Writes sourcing/<date>/
       candidates.json   survivors, freshest first, balanced across your archetypes
       jd/<key>.txt      plain-text JD per candidate, ready for /jobprep
       excluded.jsonl    every dropped on-target posting with the reason
       coverage.json     per-board status, so a silently empty board is visible

Platforms: Greenhouse, Ashby, Lever, Workday, Workable, SmartRecruiters, YC (Work at a Startup).
Python standard library only.
"""
import argparse, concurrent.futures as cf, datetime as dt, html, json, re, sqlite3, sys, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTER = ROOT / "tools" / "companies.json"
USER_COMPANIES = ROOT / "profile" / "companies.json"
CONFIG = ROOT / "profile" / "search.json"
FUNNEL = ROOT / "funnel" / "funnel.sqlite"
OUT = ROOT / "sourcing"
SKIPPED = OUT / "skipped.json"

UA = {"User-Agent": "Mozilla/5.0 (compatible; jobprep-kit/1.0; +https://github.com/vamsikrishna6891/jobprep-kit)"}
ACTIVE = {"prepped", "applied", "screen", "interview", "onsite", "offer", "unconfirmed"}
YC_ROLES = {"software-engineer", "designer", "product-manager", "recruiting-hr", "sales-manager", "marketing",
            "support", "operations", "science"}
SR_MAX_POSTINGS = 2000  # SmartRecruiters boards can hold thousands of reqs, page through this many at most
DEFAULTS = {
    "archetypes": {}, "exclude_titles": [], "locations": [], "remote": True, "remote_regions": [],
    "base_pay_floor": 0, "unknown_pay": "keep", "needs_sponsorship": False, "max_age_days": 30,
    "reapply_days": 90, "yc_roles": [], "limit": 150,
}

NO_SPONSOR = re.compile(r"(?i)[^.]{0,160}(not (be )?able to sponsor|unable to sponsor|will not sponsor|won't sponsor|"
                        r"do(es)? not (offer |provide )?(visa |immigration )?sponsor|cannot sponsor|can't sponsor|"
                        r"no (visa|immigration) sponsorship|not eligible for (visa |immigration )?sponsorship|"
                        r"without (the need for )?(current or future |now or in the future )?(visa |employment )?sponsorship|"
                        r"must be a u\.?s\.? citizen|u\.?s\.? citizenship (is )?required)[^.]{0,120}")
CLEARANCE = re.compile(r"(?i)[^.]{0,80}(requires?|must (have|hold|obtain|possess)|ability to obtain|active|eligible for)"
                       r"[^.]{0,40}security clearance[^.]{0,60}")
NEGATED = re.compile(r"(?i)\b(no|not(?! only)|never|without)\b[^.]{0,25}(requir|need|necessary)|n't[^.]{0,25}(requir|need)|"
                     r"clearance[^.]{0,20}not (required|needed|necessary)")
PAY_RANGE = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})+(?:\.\d+)?|\d{2,3}(?:\.\d+)?\s?[kK])\s*(?:USD\s*)?(?:/\s?(?:yr|year)|per year|annually)?\s*"
                       r"(?:-|–|—|to|and|[^$]{0,70}?up to)\s*(?:USD\s*)?\$?\s?(\d{2,3}(?:,\d{3})+(?:\.\d+)?|\d{2,3}(?:\.\d+)?\s?[kK])")
NOT_BASE = re.compile(r"(?i)total (target |cash |annual )*comp|on[- ]target|\bote\b|equity|bonus|commission")
NOT_BASE_AFTER = re.compile(r"(?i)^[\s,(]*(usd )?(in |of |as )?(total (target |cash |annual )*comp|on[- ]target|ote\b)")
WD_PAGE, WD_MAX_PER_QUERY, WD_MAX_QUERIES = 20, 100, 12  # Workday search: page size, results read per phrase, phrases used
LEVEL = re.compile(r"(?i)\b(junior|jr|associate|senior|sr|staff|principal|lead|manager|director|head|ii|iii|iv|v)\b")


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def fetch(url, data=None, timeout=25, retries=2):
    """GET (or POST when data is given) and return the body as text."""
    body = json.dumps(data).encode() if data is not None else None
    hdr = dict(UA, Accept="application/json, text/html")
    if body:
        hdr["Content-Type"] = "application/json"
    last = None
    for i in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=hdr), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404, 410):
                raise
            last = e
            if e.code == 429:
                time.sleep(10 * (i + 1))
        except Exception as e:  # network blips
            last = e
        time.sleep(1.5 * (i + 1))
    raise last


def get(url, data=None, timeout=25, retries=2):
    return json.loads(fetch(url, data, timeout, retries))


def strip_html(s):
    s = html.unescape(html.unescape(s or ""))  # Greenhouse double-escapes, so unescape before removing tags
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


# ---------------------------------------------------------------- config

def phrases_rx(phrases):
    """Case-insensitive whole-word match for a list of plain phrases. A trailing * matches a prefix:
    "product analy*" hits "Product Analyst" and "Product Analytics". Returns None for an empty list."""
    parts = []
    for p in phrases:
        p = p.strip()
        if not p:
            continue
        prefix = p.endswith("*")
        body = r"\s+".join(re.escape(w) for w in p.rstrip("*").split())
        parts.append(r"(?<![a-z0-9])" + body + ("" if prefix else r"(?![a-z0-9])"))
    return re.compile("(?i)" + "|".join(parts)) if parts else None


def load_config(path=CONFIG):
    if not path.exists():
        sys.exit(f"Missing {path.relative_to(ROOT)}. Run /jobprep-setup, or copy profile/search.example.json "
                 f"to profile/search.json and edit it.")
    raw = json.loads(path.read_text())
    unknown = sorted(k for k in raw if k not in DEFAULTS and not k.startswith("_"))
    if unknown:
        sys.exit(f"Unknown keys in {path.name}: {', '.join(unknown)}. Allowed: {', '.join(DEFAULTS)}")
    cfg = dict(DEFAULTS, **{k: v for k, v in raw.items() if not k.startswith("_")})

    def str_list(v):
        return isinstance(v, list) and all(isinstance(x, str) for x in v)

    def number(v, low):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= low

    arch = cfg["archetypes"]
    if not isinstance(arch, dict) or not arch or not all(str_list(v) and any(x.strip("* ") for x in v) for v in arch.values()):
        sys.exit(f'{path.name}: "archetypes" must map each name to a list of title phrases, e.g. {{"DS": ["data scientist"]}}')
    for k in ("exclude_titles", "locations", "remote_regions", "yc_roles"):
        if not str_list(cfg[k]):
            sys.exit(f'{path.name}: "{k}" must be a list of strings, e.g. ["one", "two"]')
    for k in ("remote", "needs_sponsorship"):
        if not isinstance(cfg[k], bool):
            sys.exit(f'{path.name}: "{k}" must be true or false')
    for k, low in (("base_pay_floor", 0), ("max_age_days", 1), ("reapply_days", 0), ("limit", 1)):
        if not number(cfg[k], low):
            sys.exit(f'{path.name}: "{k}" must be a number, {low} or more')
    if cfg["unknown_pay"] not in ("keep", "drop"):
        sys.exit(f'{path.name}: "unknown_pay" must be "keep" or "drop"')
    bad = sorted(set(cfg["yc_roles"]) - YC_ROLES)
    if bad:
        sys.exit(f'{path.name}: unknown yc_roles {bad}. Valid: {sorted(YC_ROLES)}')
    cfg["_archetypes"] = [(name, phrases_rx(ph)) for name, ph in cfg["archetypes"].items() if phrases_rx(ph)]
    cfg["_exclude"] = phrases_rx(cfg["exclude_titles"])
    cfg["_locations"] = phrases_rx(cfg["locations"])
    cfg["_regions"] = phrases_rx(cfg["remote_regions"])
    # Workday has no "list everything" endpoint, so it is searched with your own title phrases
    # (the first WD_MAX_QUERIES of them, WD_MAX_PER_QUERY results each).
    seen, queries = set(), []
    for ph in cfg["archetypes"].values():
        for p in ph:
            q = p.rstrip("*").strip().lower()
            if q and q not in seen:
                seen.add(q)
                queries.append(q)
    cfg["_workday_queries"] = queries[:WD_MAX_QUERIES]
    return cfg


def load_companies():
    out = json.loads(STARTER.read_text()) if STARTER.exists() else {}
    if USER_COMPANIES.exists():
        out.update(json.loads(USER_COMPANIES.read_text()))
    return {name: src for name, src in out.items() if src}


# ---------------------------------------------------------------- fetchers
# Each yields dicts with: ats, slug, ext_id, url, title, location, posted (ISO string or None), text, pay.
# "pay" is a list of {"min", "max", "label"} USD base ranges, or None when the board has no structured pay.

def fetch_greenhouse(slug, cfg):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    for j in d.get("jobs", []):
        if not j.get("id"):
            continue  # one malformed posting must not cost the whole board
        yield {
            "ats": "greenhouse", "slug": slug, "ext_id": str(j["id"]), "url": j.get("absolute_url"),
            "title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
            "posted": j.get("first_published"),  # updated_at resets on any edit, so it is never a posting date
            "text": strip_html(j.get("content", "")), "pay": None,
        }


def greenhouse_pay(slug, ext_id):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{ext_id}?pay_transparency=true")
    tiers = []
    for r in d.get("pay_input_ranges") or []:
        if (r.get("currency_type") or "USD") != "USD":
            continue
        lo, hi = (r.get("min_cents") or 0) / 100, (r.get("max_cents") or 0) / 100
        if hi >= 20_000:
            tiers.append({"min": lo, "max": hi, "label": f"{r.get('title') or ''} {strip_html(r.get('blurb') or '')[:200]}"})
    return tiers


def fetch_lever(slug, cfg):
    d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    for j in d:
        if not j.get("id"):
            continue
        cats = j.get("categories") or {}
        sal = j.get("salaryRange") or {}
        pay = None
        if sal.get("max") and (sal.get("currency") or "USD") == "USD" and (sal.get("interval") or "per-year-salary").startswith("per-year"):
            pay = [{"min": sal.get("min") or 0, "max": sal["max"], "label": "salaryRange"}]
        text = "\n".join([j.get("descriptionPlain") or "", j.get("additionalPlain") or ""] +
                         [f"{l.get('text', '')}\n{strip_html(l.get('content', ''))}" for l in j.get("lists") or []])
        created = j.get("createdAt")
        yield {
            "ats": "lever", "slug": slug, "ext_id": j["id"], "url": j.get("hostedUrl"), "title": j.get("text", ""),
            "location": " / ".join(dict.fromkeys(l for l in [cats.get("location")] + (cats.get("allLocations") or []) if l)),
            "posted": dt.datetime.fromtimestamp(created / 1000, dt.timezone.utc).isoformat() if created else None,
            "text": text, "pay": pay,
        }


def fetch_ashby(slug, cfg):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    for j in d.get("jobs", []):
        if j.get("isListed") is False or not j.get("id"):
            continue
        tiers = []
        for t in (j.get("compensation") or {}).get("compensationTiers") or []:
            for c in t.get("components") or []:
                if c.get("compensationType") == "Salary" and c.get("currencyCode") == "USD" \
                        and (c.get("interval") or "").upper() == "1 YEAR" and c.get("maxValue"):
                    tiers.append({"min": c.get("minValue") or 0, "max": c["maxValue"],
                                  "label": f"{t.get('title') or ''} {t.get('tierSummary') or ''}"})
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        if j.get("isRemote"):
            locs.append("Remote")
        yield {
            "ats": "ashby", "slug": slug, "ext_id": j["id"], "url": j.get("jobUrl"), "title": j.get("title", ""),
            "location": " / ".join(l for l in locs if l), "posted": j.get("publishedAt"),
            "text": j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", "")), "pay": tiers or None,
        }


def fetch_workday(slug, cfg):
    host, tenant, site = slug.split("|")
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    seen = set()
    for q in cfg["_workday_queries"]:
        off, total = 0, None
        while off < WD_MAX_PER_QUERY:
            d = get(f"{base}/jobs", data={"appliedFacets": {}, "limit": WD_PAGE, "offset": off, "searchText": q})
            rows = d.get("jobPostings") or []
            if total is None:
                total = d.get("total") or 0  # some tenants report the total on the first page only
            for p in rows:
                path = p.get("externalPath")
                if not path or path in seen:
                    continue
                seen.add(path)
                yield {
                    "ats": "workday", "slug": slug, "ext_id": path.rsplit("_", 1)[-1], "url": f"https://{host}/en-US/{site}{path}",
                    "title": p.get("title", ""), "location": p.get("locationsText") or "",
                    "posted": relative_date(p.get("postedOn")), "text": "", "pay": None, "_detail": f"{base}{path}",
                    "_open_ended": "+" in str(p.get("postedOn") or ""),  # "Posted 30+ Days Ago" hides the real age
                }
            off += WD_PAGE
            if len(rows) < WD_PAGE or off >= total:
                break


def workday_detail(url):
    info = get(url).get("jobPostingInfo") or {}
    locs = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
    return strip_html(info.get("jobDescription", "")), " / ".join(l for l in locs if l)


def fetch_workable(slug, cfg):
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    for j in d.get("jobs", []):
        if not j.get("shortcode"):
            continue
        locs = [", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x) for l in j.get("locations") or []]
        if not locs:
            locs = [", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)]
        if j.get("telecommuting"):
            locs.append("Remote")
        yield {
            "ats": "workable", "slug": slug, "ext_id": j["shortcode"], "url": j.get("url"), "title": j.get("title", ""),
            "location": " / ".join(dict.fromkeys(l for l in locs if l)),
            "posted": j.get("published_on") or j.get("created_at"),
            "text": strip_html(j.get("description", "")), "pay": None,
        }


def fetch_smartrecruiters(slug, cfg):
    off = 0
    while off < SR_MAX_POSTINGS:
        d = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={off}")
        rows = d.get("content") or []
        for j in rows:
            if not j.get("id"):
                continue
            loc = j.get("location") or {}
            where = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
            yield {
                "ats": "smartrecruiters", "slug": slug, "ext_id": str(j["id"]),
                "url": f"https://jobs.smartrecruiters.com/{slug}/{j['id']}", "title": j.get("name", ""),
                "location": where + (" / Remote" if loc.get("remote") else ""), "posted": j.get("releasedDate"),
                "text": "", "pay": None, "_detail": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{j['id']}",
            }
        off += 100
        if len(rows) < 100 or off >= (d.get("totalFound") or 0):
            break


def smartrecruiters_detail(url):
    d = get(url)
    secs = (d.get("jobAd") or {}).get("sections") or {}
    parts = [f"{s.get('title') or ''}\n{strip_html(s.get('text') or '')}"
             for k in ("jobDescription", "qualifications", "additionalInformation") for s in [secs.get(k) or {}] if s.get("text")]
    return "\n\n".join(parts), d.get("postingUrl")


def page_props(page_html):
    m = re.search(r'data-page="([^"]+)"', page_html)
    return json.loads(html.unescape(m.group(1)))["props"] if m else {}


def fetch_yc(role, cfg):
    """YC's public job pages, one per role family. Covers every YC company, so it needs no company list."""
    for j in page_props(fetch(f"https://www.ycombinator.com/jobs/role/{role}")).get("jobPostings") or []:
        if not j.get("id") or not j.get("url"):
            continue
        yield {
            "ats": "yc", "slug": role, "ext_id": str(j["id"]), "company": j.get("companyName") or "YC company",
            "url": "https://www.ycombinator.com" + j["url"], "title": j.get("title", ""),
            "location": j.get("location") or "", "posted": relative_date(j.get("createdAt")), "text": "",
            "pay": text_pay(j.get("salaryRange") or "") or None, "_visa": j.get("visa") or "",
        }


def yc_detail(url):
    job = page_props(fetch(url)).get("job") or {}
    return "\n\n".join(x for x in (job.get("companyOneLiner"), strip_html(job.get("description") or "")) if x)


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby, "workday": fetch_workday,
            "workable": fetch_workable, "smartrecruiters": fetch_smartrecruiters, "yc": fetch_yc}


# ---------------------------------------------------------------- add a company

def slug_candidates(name):
    base = re.sub(r"\(.*?\)", "", name).strip()
    words = re.findall(r"[a-z0-9]+", base.lower())
    joined, hyph = "".join(words), "-".join(words)
    out = [joined, hyph, re.sub(r"[^A-Za-z0-9]", "", base)]  # SmartRecruiters ids are case-sensitive ("ServiceNow")
    if words and words[-1] == "ai":
        out += ["".join(words[:-1]), "-".join(words[:-1])]
    else:
        out += [joined + "ai", joined + "hq", joined + "inc"]
    return [s for s in dict.fromkeys(out) if s]


BOARD_URL = {
    "greenhouse": "https://boards.greenhouse.io/{}", "ashby": "https://jobs.ashbyhq.com/{}",
    "lever": "https://jobs.lever.co/{}", "workable": "https://apply.workable.com/{}",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{}",
}


def probe(ats, slug):
    """Number of open jobs on a board, or -1 when the board does not exist."""
    try:
        if ats == "greenhouse":
            return len(get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", retries=0).get("jobs", []))
        if ats == "lever":
            d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=200", retries=0)
            return len(d) if isinstance(d, list) else -1
        if ats == "ashby":
            return len(get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", retries=0).get("jobs", []))
        if ats == "workable":
            return len(get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", retries=0).get("jobs", []))
        if ats == "smartrecruiters":
            # Unknown companies answer 200 with zero postings, so zero means "not found" here.
            return get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", retries=0).get("totalFound") or -1
        if ats == "workday":
            host, tenant, site = slug.split("|")
            d = get(f"https://{host}/wday/cxs/{tenant}/{site}/jobs", retries=0,
                    data={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
            return d.get("total") or len(d.get("jobPostings") or [])
    except Exception:
        return -1
    return -1


def add_company(name, board=None):
    found = []
    if board:
        ats, _, slug = board.partition(":")
        if ats not in FETCHERS or ats == "yc" or not slug:
            sys.exit('--board must look like "greenhouse:acme" or "workday:host|tenant|site"')
        if ats == "workday" and slug.count("|") != 2:
            sys.exit('Workday boards need "workday:host|tenant|site", e.g. workday:acme.wd5.myworkdayjobs.com|acme|External')
        found = [{"ats": ats, "slug": slug}]
    else:
        for ats in BOARD_URL:
            for slug in slug_candidates(name):
                n = probe(ats, slug)
                if n > 0:
                    found.append({"ats": ats, "slug": slug})
                    print(f"  {ats}: {n} open jobs at {BOARD_URL[ats].format(slug)}")
                    break
    if not found:
        print(f'No board found for "{name}". Open the company careers page, look at the URL of any job, then run:\n'
              f'  python3 tools/source.py --add "{name}" --board <platform>:<id>\n'
              f"Platforms: {', '.join(k for k in FETCHERS if k != 'yc')}. Workday id is host|tenant|site.")
        return 1
    mine = json.loads(USER_COMPANIES.read_text()) if USER_COMPANIES.exists() else {}
    mine[name] = found
    USER_COMPANIES.parent.mkdir(exist_ok=True)
    USER_COMPANIES.write_text(json.dumps(mine, indent=1, sort_keys=True) + "\n")
    print(f'Saved "{name}" to {USER_COMPANIES.relative_to(ROOT)}.' +
          ("" if board else " Board ids are guessed from the name, so open the link above and confirm it is the right company."))
    return 0


SLUG_OK = re.compile(r"[A-Za-z0-9_.-]{1,80}")  # board ids go into request URLs, so nothing else is accepted


def parse_board_url(url):
    """Any job or board link on a supported platform -> (platform, board id), else None."""
    try:
        u = urllib.parse.urlparse(url.strip() if "//" in url else "https://" + url.strip())
        host = (u.hostname or "").lower()
    except ValueError:  # search results can carry malformed links, one must not sink the batch
        return None
    parts = [urllib.parse.unquote(x) for x in u.path.split("/") if x]
    first = parts[0] if parts else ""
    ats = slug = None
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io"):
        # Embedded boards carry the id in ?for=, and some embed links carry no id at all.
        ats, slug = "greenhouse", ((urllib.parse.parse_qs(u.query).get("for") or [""])[0] if first == "embed" else first).lower()
    elif host == "jobs.ashbyhq.com":
        ats, slug = "ashby", first
    elif host == "jobs.lever.co":
        ats, slug = "lever", first
    elif host == "apply.workable.com":
        ats, slug = "workable", "" if first == "j" else first  # /j/<code> links do not name the company
    elif host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"):
        ats, slug = "smartrecruiters", first
    else:
        m = re.fullmatch(r"([a-z0-9_-]+)\.wd\d+\.myworkdayjobs\.com", host)
        site = next((x for x in parts if not re.fullmatch(r"[a-z]{2}-[A-Za-z]{2}", x)), "")
        if m and SLUG_OK.fullmatch(site) and site != "wday":
            return "workday", f"{host}|{m.group(1)}|{site}"
        return None
    return (ats, slug) if SLUG_OK.fullmatch(slug or "") else None


def board_name(ats, slug):
    """The company name a board reports for itself, else a readable form of the board id."""
    try:
        if ats == "greenhouse":
            name = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}", retries=0).get("name")
        elif ats == "workable":
            name = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", retries=0).get("name")
        elif ats == "smartrecruiters":
            rows = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", retries=0).get("content") or [{}]
            name = (rows[0].get("company") or {}).get("name")
        else:
            name = None
    except Exception:
        name = None
    if isinstance(name, str) and name.strip():
        return name.strip()
    base = slug.split("|")[1] if ats == "workday" else slug
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", re.sub(r"[-_.]+", " ", base)).split()  # CollectlyInc -> Collectly Inc
    return " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words) or slug


def add_urls(urls):
    """Save the boards behind a batch of job links. Only live boards that are not already scanned are added."""
    starter = json.loads(STARTER.read_text()) if STARTER.exists() else {}
    mine = json.loads(USER_COMPANIES.read_text()) if USER_COMPANIES.exists() else {}
    known = {(x["ats"], x["slug"].lower()) for srcs in list(starter.values()) + list(mine.values()) for x in srcs}
    parsed = list(dict.fromkeys(b for b in map(parse_board_url, urls) if b))
    fresh = [b for b in parsed if (b[0], b[1].lower()) not in known]

    def check(b):
        n = probe(*b)
        return b, n, board_name(*b) if n > 0 else None

    def same_name(name, table):
        return next((k for k in table if norm_co(k) == norm_co(name)), None)

    added, dead, disabled = [], 0, 0
    with cf.ThreadPoolExecutor(8) as ex:
        for (ats, slug), n, name in ex.map(check, fresh):
            if n <= 0:
                dead += 1  # search results outlive the boards they point to
                continue
            src = {"ats": ats, "slug": slug}
            key = same_name(name, mine)
            if key is not None and not mine[key]:
                disabled += 1  # {"Acme": []} in your file means "never scan Acme", discovery must not undo that
                continue
            if key is not None:
                mine[key].append(src)
            else:
                # Your file replaces a starter entry of the same name, so carry the starter boards over.
                old = same_name(name, starter)
                key = old or name
                mine[key] = list(starter.get(old, [])) + [src]
            added.append(key)
            print(f"  added {key}: {ats}, {n} open jobs")
    if added:
        USER_COMPANIES.parent.mkdir(exist_ok=True)
        USER_COMPANIES.write_text(json.dumps(mine, indent=1, sort_keys=True) + "\n")
    OUT.mkdir(exist_ok=True)
    with (OUT / "discovery-log.jsonl").open("a") as f:
        f.write(json.dumps({"date": dt.date.today().isoformat(), "links": len(urls), "boards": len(parsed),
                            "already_scanned": len(parsed) - len(fresh), "dead": dead, "disabled_by_you": disabled,
                            "added": added}) + "\n")
    print(f"links={len(urls)} boards={len(parsed)} already_scanned={len(parsed) - len(fresh)} dead={dead} "
          f"disabled_by_you={disabled} added={len(added)}")
    return 0


# ---------------------------------------------------------------- funnel

def norm_co(s):
    s = re.sub(r"\(.*?\)", "", s or "").lower()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\b(inc|llc|corp|the)\b", "", s))


def funnel_rows(path=FUNNEL):
    if not path.exists():
        return []
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10) as c:
            return c.execute("select id, company, role, status, date from apps").fetchall()
    except sqlite3.Error:
        return []


def levels(title):
    return {{"sr": "senior", "jr": "junior"}.get(m.group(1).lower(), m.group(1).lower()) for m in LEVEL.finditer(title or "")}


def tokens(s):
    stop = {"the", "and", "of", "for", "a", "an", "in", "at"}
    return {t for t in re.findall(r"[a-z]+", LEVEL.sub(" ", (s or "").lower())) if t not in stop and len(t) > 1}


def similar(a, b):
    """Same role, for dedupe against the funnel. A different level is a different req (Senior rejected, Staff open)."""
    if levels(a) != levels(b):
        return False
    ta, tb = tokens(a), tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.8


def funnel_check(p, rows, today, reapply_days):
    """Returns (blocked_reason or None, flags)."""
    flags = []
    same_co = [r for r in rows if norm_co(r[1]) == norm_co(p["company"])]
    for rid, _, role, status, date in same_co:
        if not similar(role, p["title"]):
            continue
        if status in ACTIVE:
            return f"same role already {status} in your funnel ({rid})", flags
        try:
            since = (dt.date.fromisoformat(today) - dt.date.fromisoformat((date or "")[:10])).days
        except (TypeError, ValueError):
            flags.append(f"REAPPLY: {rid} {status}, date missing in your funnel")  # unknown is not "today"
            continue
        if since < reapply_days:
            return f"same role {status} {since}d ago ({rid}), reapply after {reapply_days}d", flags
        flags.append(f"REAPPLY: {rid} {status} {since}d ago")
    if any(r[3] in ACTIVE for r in same_co):
        flags.append("ACTIVE-AT-COMPANY: " + ", ".join(f"{r[0]} {r[3]}" for r in same_co if r[3] in ACTIVE))
    elif same_co:
        flags.append(f"PRIOR-AT-COMPANY: {len(same_co)} earlier application(s)")
    return None, flags


# ---------------------------------------------------------------- filtering

def no_sponsor(text):
    """The sentence that rules out visa sponsorship, or None. A clearance line counts only when it is a requirement."""
    m = NO_SPONSOR.search(text or "")
    if m:
        return m.group(0).strip()
    for m in CLEARANCE.finditer(text or ""):
        if not NEGATED.search(m.group(0)):
            return m.group(0).strip()
    return None


def relative_date(s):
    """'Posted 3 Days Ago', 'Posted 30+ Days Ago', 'about 5 hours', '2 months' -> ISO timestamp, else None."""
    if not isinstance(s, str):
        return None
    s = s.lower()
    if "today" in s or "just" in s:
        return now_utc().isoformat()
    if "yesterday" in s:
        return (now_utc() - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*(minute|hour|day|week|month|year)", s)
    if not m:
        return None
    days = int(m.group(1)) * {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)]
    return (now_utc() - dt.timedelta(days=days)).isoformat()


def age_days(p):
    if not isinstance(p.get("posted"), str) or not p["posted"]:
        return None
    try:
        t = dt.datetime.fromisoformat(p["posted"].replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return max(0.0, (now_utc() - t).total_seconds() / 86400)


def archetype(title, cfg):
    for name, rx in cfg["_archetypes"]:
        if rx.search(title):
            return name
    return None


def location_ok(loc, text, cfg):
    """True when the posting is in one of your locations, or is remote in a region you accept.
    With no locations and remote off there is nothing to filter on, so everything passes."""
    loc = (loc or "").strip()
    places, regions = cfg["_locations"], cfg["_regions"]
    if not places and not cfg["remote"]:
        return True
    if places and places.search(loc):
        return True
    if cfg["remote"] and re.search(r"(?i)\bremote\b", loc):
        if not regions or regions.search(loc):
            return True
        if re.fullmatch(r"(?i)[\s\-(),/]*remote[\s\-(),/]*", loc):
            return True  # a bare "Remote" names no region to rule out
    if cfg["remote"] and regions and regions.fullmatch(loc):
        return True  # boards often list remote reqs as just the country, e.g. "United States"
    if not loc and places:
        return bool(places.search((text or "")[:1500]))
    return False


def text_pay(text):
    tiers = []
    for m in PAY_RANGE.finditer(text or ""):
        vals = []
        for g in m.groups():
            g = g.replace(",", "").replace(" ", "")
            vals.append(float(g[:-1]) * 1000 if g[-1] in "kK" else float(g))
        lo, hi = vals
        if 30_000 <= hi <= 1_500_000 and lo <= hi:
            before, after = text[max(0, m.start() - 80):m.start()], text[m.end():m.end() + 30]
            if re.search(r"(?i)per hour|/\s?hr|hourly|^\s*(in|of) (equity|stock|rsus?)|sign[- ]on", after):
                continue
            # The floor is a base-pay floor. A range introduced as total comp, OTE, bonus, or equity is not base,
            # unless the same lead-in also says base or salary ("base salary, plus bonus and equity, is ...").
            lead = re.split(r"[.;\n]", before)[-1]
            if not re.search(r"(?i)\bbase\b|salary", lead) and (NOT_BASE.search(lead) or NOT_BASE_AFTER.search(after)):
                continue
            tiers.append({"min": lo, "max": hi, "label": text[max(0, m.start() - 160):m.end() + 60].replace("\n", " ")})
    return tiers


def classify_pay(tiers, cfg):
    """Returns (class, info). Uses the range labelled with one of your locations when a posting lists
    several geo tiers, else the highest range. Class is meets-floor, below-floor, or unknown."""
    if not tiers:
        return "unknown", None
    mine = [t for t in tiers if cfg["_locations"] and cfg["_locations"].search(t["label"])]
    t = max(mine or tiers, key=lambda x: x["max"])
    info = {"min": int(t["min"]), "max": int(t["max"]), "basis": "your-location" if mine else ("single-range" if len(tiers) == 1 else "max-of-ranges")}
    return ("meets-floor" if t["max"] >= cfg["base_pay_floor"] else "below-floor"), info


def enrich(p):
    """Boards whose list view has no description get one detail call, only for postings that passed the title gate."""
    try:
        if p["ats"] == "workday":
            p["text"], loc = workday_detail(p.pop("_detail"))
            if not p["location"] or re.fullmatch(r"\d+ Locations", p["location"].strip()):
                p["location"] = loc  # the list view collapses multi-city reqs to "N Locations"
        elif p["ats"] == "smartrecruiters":
            p["text"], url = smartrecruiters_detail(p.pop("_detail"))
            p["url"] = url or p["url"]
        elif p["ats"] == "yc":
            p["text"] = yc_detail(p["url"])
            if p.get("_visa"):
                p["text"] += f"\n\nVisa: {p['_visa']}"
        elif p["ats"] == "greenhouse":
            p["pay"] = greenhouse_pay(p["slug"], p["ext_id"]) or None
    except Exception as e:
        p["enrich_error"] = f"{type(e).__name__}: {e}"[:160]
    return p


def run(run_date, cfg, companies):
    out = OUT / run_date
    (out / "jd").mkdir(parents=True, exist_ok=True)
    jobs = [(name, s) for name, srcs in companies.items() for s in srcs if s.get("ats") in FETCHERS and s["ats"] != "yc"]
    jobs += [(None, {"ats": "yc", "slug": role}) for role in cfg["yc_roles"]]

    def pull(item):
        name, s = item
        t0 = time.time()
        try:
            rows = list(FETCHERS[s["ats"]](s["slug"], cfg))
            for r in rows:
                r["company"] = r.get("company") or name
            return name, s, rows, None, time.time() - t0
        except Exception as e:
            return name, s, [], f"{type(e).__name__}: {e}"[:200], time.time() - t0

    coverage, raw = [], []
    with cf.ThreadPoolExecutor(16) as ex:
        for name, s, rows, err, secs in ex.map(pull, jobs):
            coverage.append({"company": name or f"YC ({s['slug']})", "ats": s["ats"], "slug": s["slug"],
                             "jobs": len(rows), "error": err, "secs": round(secs, 1)})
            raw.extend(rows)

    excluded = []

    def drop(p, why):
        excluded.append({"company": p["company"], "title": p["title"], "location": p.get("location"), "url": p.get("url"), "why": why})

    stage1 = []
    for p in raw:
        arch = archetype(p["title"], cfg)
        if not arch:
            continue  # off-target titles are the bulk of every board, not worth logging
        if cfg["_exclude"] and cfg["_exclude"].search(p["title"]):
            drop(p, "title excluded")
            continue
        a = age_days(p)
        if a is None:
            drop(p, "no posting date")
            continue
        if p.get("_open_ended"):
            drop(p, f"posted {a:.0f}+ days ago, the board does not say how old")
            continue
        if a > cfg["max_age_days"]:
            drop(p, f"posted {a:.0f}d ago, older than max_age_days {cfg['max_age_days']}")
            continue
        p["archetype"], p["age_days"] = arch, round(a, 1)
        # Cheap check first, so detail calls go only to plausible reqs. Deferred when the list view
        # carries neither a description nor a usable location (Workday shows "3 Locations").
        vague = not p["text"] and (not p["location"].strip() or re.fullmatch(r"\d+ Locations", p["location"].strip()))
        if not vague and not location_ok(p["location"], p["text"], cfg):
            drop(p, f"location: {p['location']}")
            continue
        stage1.append(p)

    with cf.ThreadPoolExecutor(8) as ex:
        stage1 = list(ex.map(enrich, stage1))

    frows = funnel_rows()
    skipped = set(json.loads(SKIPPED.read_text())) if SKIPPED.exists() else set()
    survivors, seen = [], {}
    for p in stage1:
        if p["url"] in skipped:
            continue
        dup = (norm_co(p["company"]), re.sub(r"[^a-z0-9]", "", p["title"].lower()))
        if dup in seen:
            # Usually one req posted once per city or on two boards. Logged, in case it is a second team.
            drop(p, f"same title already kept for this company ({seen[dup]})")
            continue
        if not location_ok(p["location"], p["text"], cfg):
            drop(p, f"location: {p['location']}")
            continue
        if len(p["text"] or "") < 400:
            drop(p, "job description missing or too short" + (f" ({p['enrich_error']})" if p.get("enrich_error") else ""))
            continue
        if cfg["needs_sponsorship"]:
            why = no_sponsor(p["text"]) or ("US citizen/visa only" if re.search(r"(?i)us citizen/visa only", p.get("_visa", "")) else None)
            if why:
                drop(p, f"no sponsorship: {why[:220]}")
                continue
        pay_class, pay = classify_pay(p["pay"] or text_pay(p["text"]), cfg)
        if pay_class == "below-floor" or (pay_class == "unknown" and cfg["unknown_pay"] == "drop" and cfg["base_pay_floor"]):
            drop(p, f"pay {pay_class}: {pay}")
            continue
        blocked, flags = funnel_check(p, frows, run_date, cfg["reapply_days"])
        if blocked:
            drop(p, blocked)
            continue
        seen[dup] = p["url"]
        p["pay_class"], p["pay_info"], p["flags"] = pay_class, pay, flags
        survivors.append(p)

    # Freshest first, round-robin across archetypes so one busy title family cannot crowd out the rest.
    survivors.sort(key=lambda p: p["age_days"])
    buckets = {}
    for p in survivors:
        buckets.setdefault(p["archetype"], []).append(p)
    keep = []
    while len(keep) < cfg["limit"] and any(buckets.values()):
        for arch in list(buckets):
            if buckets[arch] and len(keep) < cfg["limit"]:
                keep.append(buckets[arch].pop(0))
    for rest in buckets.values():
        for p in rest:
            drop(p, f"cut by limit ({cfg['limit']})")

    cands = []
    for p in keep:
        key = re.sub(r"[^a-z0-9]+", "-", f"{norm_co(p['company'])}-{p['title']}".lower()).strip("-")[:70] + f"-{p['ext_id'][-6:]}"
        (out / "jd" / f"{key}.txt").write_text(
            f"Company: {p['company']}\nTitle: {p['title']}\nLocation: {p['location']}\nURL: {p['url']}\n"
            f"Posted: {p['posted']}\nPay: {p['pay_class']} {json.dumps(p['pay_info'])}\n\n{p['text']}\n")
        c = {k: p.get(k) for k in ("company", "title", "location", "url", "ats", "archetype", "posted", "age_days",
                                   "pay_class", "pay_info", "flags")}
        c["key"] = key
        cands.append(c)

    (out / "candidates.json").write_text(json.dumps(cands, indent=1))
    with (out / "excluded.jsonl").open("w") as f:
        for e in excluded:
            f.write(json.dumps(e) + "\n")
    errs = [c for c in coverage if c["error"]]
    (out / "coverage.json").write_text(json.dumps({
        "boards": len(coverage), "board_errors": len(errs), "postings_fetched": len(raw),
        "on_target_and_fresh": len(stage1), "candidates": len(cands), "detail": coverage}, indent=1))
    print(f"boards={len(coverage)} errors={len(errs)} fetched={len(raw)} on_target={len(stage1)} "
          f"candidates={len(cands)} -> {out.relative_to(ROOT)}")
    for c in errs:
        print(f"  board error: {c['company']} ({c['ats']}:{c['slug']}) {c['error']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Find open roles on company job boards.")
    ap.add_argument("--add", metavar="COMPANY", help="find this company's job board and save it")
    ap.add_argument("--board", metavar="PLATFORM:ID", help="with --add, skip the lookup and save this board")
    ap.add_argument("--add-url", metavar="URL", nargs="+", help="save the boards behind these job or board links")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="output folder name, default today")
    a = ap.parse_args()
    if a.add:
        sys.exit(add_company(a.add, a.board))
    if a.add_url:
        sys.exit(add_urls(a.add_url))
    sys.exit(run(a.date, load_config(), load_companies()))
