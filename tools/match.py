#!/usr/bin/env python3
"""
match.py - free ATS-style keyword match scorer. Python stdlib only.

Usage:
    python3 tools/match.py <jd.txt> <resume.(txt|md|html)>

Scores how well a resume covers the top keywords of a job description.
Weighted coverage: score = covered term weight / total term weight * 100.
Prints the score plus ranked missing terms so you know what to add.

Semantics (from real funnel data, ~100 applications):
  - 80 is the floor: below it, tailor more.
  - 85 is the ceiling: past it, keyword polish buys nothing.
    Spend the time on referrals and hiring-manager outreach instead.
"""
import html.parser
import re
import sys
from collections import Counter

STOPWORDS = set("""
a about above after again all also am an and any are as at be because been
before being below between both but by can could did do does doing down during
each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no
nor not now of off on once only or other our ours ourselves out over own same
she should so some such than that the their theirs them themselves then there
these they this those through to too under until up very was we were what when
where which while who whom why will with you your yours yourself yourselves
work working works team teams role position candidate candidates experience
years year including include includes strong ability able etc plus new help
join company opportunity opportunities looking seeking ideal preferred required
requirements responsibilities qualifications benefits salary equal employer
diversity applicants apply application job title day days month months per
across within without via using use used well highly must may many various
location employment type full-time part-time hybrid remote onsite offer offers
range base bonus equity compensation pay paid benefits insurance leave pto
eeo race religion gender origin veteran disability accommodation accommodations
privacy policy notice agency agencies recruiter recruiters sponsorship
""".split())

# Generic verbs and filler that inflate JD term lists without signal.
WEAK = set("""
build building built drive driving driven lead leading led manage managing
managed develop developing developed create creating created deliver delivering
delivered ensure ensuring support supporting collaborate collaborating
communicate communication skills environment fast paced dynamic passionate
mission culture impact growth success successful
""".split())


class _Stripper(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def read_text(path):
    raw = open(path, encoding="utf-8", errors="ignore").read()
    if path.lower().endswith((".html", ".htm")) or "<html" in raw[:500].lower():
        s = _Stripper()
        s.feed(raw)
        raw = " ".join(s.parts)
    return raw


def tokens(text):
    # keep c++, c#, .net, node.js style tokens intact
    return [t for t in re.findall(r"[a-z0-9][a-z0-9+#.\-]*", text.lower())
            if len(t) > 1 and not t.replace(".", "").replace("-", "").isdigit()]


def ngrams(toks, n):
    grams = []
    for i in range(len(toks) - n + 1):
        gram = toks[i:i + n]
        if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
            continue
        if any(g in WEAK for g in gram):
            continue
        grams.append(" ".join(gram))
    return grams


def jd_terms(text, top_uni=40, top_bi=25, min_terms=20):
    """Top JD terms with frequency weights. Bigrams weigh double:
    a matched phrase ("machine learning") is stronger evidence than a word.
    Short JDs rarely repeat words, so if the repeated-term set is thin we
    backfill with single-occurrence unigrams until min_terms is reached."""
    toks = tokens(text)
    uni = Counter(t for t in toks if t not in STOPWORDS and t not in WEAK)
    bi = Counter(ngrams(toks, 2))
    terms = {}
    for term, freq in bi.most_common(top_bi):
        if freq >= 2:
            terms[term] = freq * 2
    in_bigram = {w for b in terms for w in b.split()}
    for term, freq in uni.most_common(top_uni):
        if freq >= 2 and term not in in_bigram:
            terms[term] = freq
    if len(terms) < min_terms:
        for term, freq in uni.most_common(top_uni * 2):
            if term not in terms and term not in in_bigram:
                terms[term] = freq
            if len(terms) >= min_terms:
                break
    return terms


def stem(t):
    """Crude suffix stripper so 'analyses'/'analysis', 'modeling'/'models',
    'designed'/'design' count as the same evidence."""
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    for suf in ("ing", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3 and not t.endswith("ss"):
            return t[: -len(suf)]
    return t


def score(jd_text, resume_text):
    terms = jd_terms(jd_text)
    if not terms:
        return 0, [], []
    resume_toks = tokens(resume_text)
    resume_uni = {stem(t) for t in resume_toks}
    resume_bi = {" ".join(stem(w) for w in b.split()) for b in ngrams(resume_toks, 2)}
    covered, missing = [], []
    total = sum(terms.values())
    got = 0.0
    for term, weight in sorted(terms.items(), key=lambda kv: -kv[1]):
        if " " in term:
            stemmed = " ".join(stem(w) for w in term.split())
            if stemmed in resume_bi:
                got += weight
                covered.append(term)
            elif all(stem(w) in resume_uni for w in term.split()):
                # both words present but not adjacent: half credit
                got += weight / 2
                covered.append(term + " (split)")
            else:
                missing.append(term)
        elif stem(term) in resume_uni:
            got += weight
            covered.append(term)
        else:
            missing.append(term)
    return round(got / total * 100), covered, missing


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    jd_text = read_text(sys.argv[1])
    resume_text = read_text(sys.argv[2])
    pct, covered, missing = score(jd_text, resume_text)
    print(f"\nMatch score: {pct}%   (floor 80, stop polishing at 85)\n")
    if missing:
        print("Missing terms (ranked by JD weight):")
        for t in missing[:15]:
            print(f"  - {t}")
    else:
        print("No missing terms in the JD's top keyword set.")
    print(f"\nCovered {len(covered)} of {len(covered) + len(missing)} weighted terms.")
    if pct >= 85:
        print("Verdict: stop polishing keywords. Work the warm path instead.")
    elif pct >= 80:
        print("Verdict: good enough to send. Further tailoring optional.")
    else:
        print("Verdict: below the 80 floor. Add honest coverage for missing terms.")


if __name__ == "__main__":
    main()
