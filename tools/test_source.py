#!/usr/bin/env python3
"""Offline tests for tools/source.py. No network.  Run: python3 tools/test_source.py"""
import json, sqlite3, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import source


def config(**over):
    d = tempfile.mkdtemp()
    p = Path(d) / "search.json"
    base = {"archetypes": {"DS": ["data scientist"], "Analytics": ["product analy*"]},
            "exclude_titles": ["intern", "director"], "locations": ["austin", "tx"], "remote": True,
            "remote_regions": ["us", "united states"], "base_pay_floor": 150000}
    base.update(over)
    p.write_text(json.dumps(base))
    source.ROOT = Path(d)  # load_config prints paths relative to ROOT on error
    return source.load_config(p)


class Titles(unittest.TestCase):
    def test_archetype_match(self):
        cfg = config()
        self.assertEqual(source.archetype("Senior Data Scientist, Growth", cfg), "DS")
        self.assertEqual(source.archetype("Product Analyst II", cfg), "Analytics")
        self.assertEqual(source.archetype("Product Analytics Lead", cfg), "Analytics")
        self.assertIsNone(source.archetype("Software Engineer", cfg))

    def test_whole_word_only(self):
        cfg = config()
        self.assertIsNone(source.archetype("Metadata Scientists Liaison", cfg))  # "data scientist" inside other words
        self.assertTrue(cfg["_exclude"].search("Data Science Intern"))
        self.assertFalse(cfg["_exclude"].search("Data Scientist, Internal Tools"))

    def test_workday_queries_come_from_phrases(self):
        self.assertEqual(config()["_workday_queries"], ["data scientist", "product analy"])


class Locations(unittest.TestCase):
    def test_place_and_remote(self):
        cfg = config()
        ok = lambda loc, text="": source.location_ok(loc, text, cfg)
        self.assertTrue(ok("Austin, TX"))
        self.assertTrue(ok("Remote - US"))
        self.assertTrue(ok("Remote"))
        self.assertTrue(ok("United States"))
        self.assertFalse(ok("Remote - UK"))
        self.assertFalse(ok("Remote, Australia"))  # "us" must not match inside "Australia"
        self.assertFalse(ok("San Francisco, CA"))
        self.assertTrue(ok("", "This role is based in Austin."))
        self.assertFalse(ok("", "This role is based in Paris."))

    def test_remote_off(self):
        cfg = config(remote=False)
        self.assertFalse(source.location_ok("Remote - US", "", cfg))
        self.assertTrue(source.location_ok("Austin, TX", "", cfg))

    def test_no_filter_means_everywhere(self):
        cfg = config(locations=[], remote=False)
        self.assertTrue(source.location_ok("Paris, France", "", cfg))

    def test_any_remote_when_no_regions(self):
        cfg = config(remote_regions=[])
        self.assertTrue(source.location_ok("Remote - UK", "", cfg))


class Pay(unittest.TestCase):
    def test_text_ranges(self):
        t = source.text_pay("The base salary range is $180,000 - $240,000 per year.")
        self.assertEqual((t[0]["min"], t[0]["max"]), (180000, 240000))
        t = source.text_pay("$225K - $255K")
        self.assertEqual((t[0]["min"], t[0]["max"]), (225000, 255000))
        self.assertEqual(source.text_pay("We pay $45 - $60 per hour."), [])
        self.assertEqual(source.text_pay("No numbers here."), [])

    def test_total_comp_is_not_base(self):
        t = source.text_pay("Base $100k-$120k. Total compensation $180k-$220k.")
        self.assertEqual([x["max"] for x in t], [120000])
        self.assertEqual(source.text_pay("On-target earnings: $200,000 - $300,000"), [])
        self.assertEqual(source.text_pay("$180k-$220k total compensation."), [])
        self.assertEqual(source.text_pay("$200k-$300k OTE."), [])
        self.assertEqual(source.text_pay("$150k - $190k plus equity and bonus.")[0]["max"], 190000)
        t = source.text_pay("The base salary, plus bonus and equity, is $150,000 - $190,000.")
        self.assertEqual(t[0]["max"], 190000)

    def test_classify(self):
        cfg = config()
        self.assertEqual(source.classify_pay([], cfg)[0], "unknown")
        self.assertEqual(source.classify_pay([{"min": 100000, "max": 140000, "label": ""}], cfg)[0], "below-floor")
        self.assertEqual(source.classify_pay([{"min": 100000, "max": 160000, "label": ""}], cfg)[0], "meets-floor")

    def test_prefers_your_location_tier(self):
        cfg = config()
        tiers = [{"min": 1, "max": 250000, "label": "San Francisco"}, {"min": 1, "max": 140000, "label": "Austin, TX"}]
        cls, info = source.classify_pay(tiers, cfg)
        self.assertEqual((cls, info["max"], info["basis"]), ("below-floor", 140000, "your-location"))


class Dates(unittest.TestCase):
    def test_relative(self):
        age = lambda s: source.age_days({"posted": source.relative_date(s)})
        self.assertAlmostEqual(age("Posted 3 Days Ago"), 3, places=1)
        self.assertAlmostEqual(age("Posted 30+ Days Ago"), 30, places=1)  # fetch_workday marks this one open-ended
        self.assertAlmostEqual(age("about 5 hours"), 0, places=1)
        self.assertAlmostEqual(age("2 months"), 60, places=1)
        self.assertAlmostEqual(age("Posted Yesterday"), 1, places=1)
        self.assertIsNone(source.relative_date("soon"))
        self.assertIsNone(source.relative_date(1700000000))
        self.assertIsNone(source.relative_date(None))

    def test_iso(self):
        self.assertIsNone(source.age_days({"posted": None}))
        self.assertIsNone(source.age_days({"posted": "not a date"}))
        self.assertIsNone(source.age_days({"posted": 1700000000}))
        self.assertGreater(source.age_days({"posted": "2020-01-01"}), 1000)
        self.assertGreater(source.age_days({"posted": "2020-01-01T00:00:00Z"}), 1000)


class Funnel(unittest.TestCase):
    def test_similar(self):
        self.assertTrue(source.similar("Senior Data Scientist, Growth", "Sr. Data Scientist - Growth"))
        self.assertFalse(source.similar("Senior Data Scientist, Growth", "Staff Data Scientist, Growth"))
        self.assertFalse(source.similar("Data Scientist, Growth", "Data Scientist, Payments Risk"))

    def test_check(self):
        rows = [("acme-ds", "Acme Inc", "Senior Data Scientist, Growth", "applied", "2026-01-10"),
                ("beta-ds", "Beta", "Data Scientist", "rejected", "2026-01-01"),
                ("gamma-pa", "Gamma", "Product Analyst", "rejected", "2025-06-01")]
        chk = lambda co, title: source.funnel_check({"company": co, "title": title}, rows, "2026-02-01", 90)
        self.assertIn("already applied", chk("Acme", "Senior Data Scientist - Growth")[0])
        self.assertIn("reapply after", chk("Beta", "Data Scientist")[0])
        blocked, flags = chk("Gamma", "Product Analyst")
        self.assertIsNone(blocked)
        self.assertTrue(flags[0].startswith("REAPPLY"))
        blocked, flags = chk("Acme", "Staff Product Analyst")
        self.assertIsNone(blocked)
        self.assertTrue(flags[0].startswith("ACTIVE-AT-COMPANY"))
        self.assertEqual(chk("Nobody", "Data Scientist"), (None, []))

    def test_missing_date_does_not_block_forever(self):
        rows = [("old-ds", "Delta", "Data Scientist", "rejected", ""), ("old-ds2", "Delta", "Data Scientist", "rejected", None)]
        blocked, flags = source.funnel_check({"company": "Delta", "title": "Data Scientist"}, rows, "2026-02-01", 90)
        self.assertIsNone(blocked)
        self.assertEqual(len(flags), 3)

    def test_missing_or_empty_db(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(source.funnel_rows(d / "none.sqlite"), [])
        sqlite3.connect(d / "empty.sqlite").close()
        self.assertEqual(source.funnel_rows(d / "empty.sqlite"), [])


class Config(unittest.TestCase):
    def test_rejects_bad_input(self):
        for bad in ({"archetypes": {}}, {"unknown_pay": "maybe"}, {"yc_roles": ["data-scientist"]}, {"locatoins": []},
                    {"archetypes": {"DS": "data scientist"}}, {"locations": "austin"}, {"remote": "yes"},
                    {"base_pay_floor": "150k"}, {"max_age_days": 0}, {"limit": True}):
            with self.assertRaises(SystemExit):
                config(**bad)

    def test_example_file_loads(self):
        example = Path(__file__).resolve().parent.parent / "profile" / "search.example.json"
        self.assertTrue(source.load_config(example)["_archetypes"])

    def test_starter_list_shape(self):
        starter = json.loads((Path(__file__).resolve().parent / "companies.json").read_text())
        for name, srcs in starter.items():
            for s in srcs:
                self.assertIn(s["ats"], source.FETCHERS, name)
                self.assertTrue(s["slug"], name)
                if s["ats"] == "workday":
                    self.assertEqual(s["slug"].count("|"), 2, name)


class BoardUrls(unittest.TestCase):
    def test_parse(self):
        ok = source.parse_board_url
        self.assertEqual(ok("https://boards.greenhouse.io/lightspeedsystems/jobs/5545692003"), ("greenhouse", "lightspeedsystems"))
        self.assertEqual(ok("https://job-boards.greenhouse.io/Discord/jobs/1"), ("greenhouse", "discord"))
        self.assertEqual(ok("https://boards.greenhouse.io/embed/job_app?for=branchmetrics&token=6878966"), ("greenhouse", "branchmetrics"))
        self.assertIsNone(ok("https://boards.greenhouse.io/embed/job_app?token=4900481008"))
        self.assertEqual(ok("https://jobs.ashbyhq.com/hostinger/7e22c963"), ("ashby", "hostinger"))
        self.assertEqual(ok("https://jobs.lever.co/CollectlyInc/d28eb014"), ("lever", "CollectlyInc"))
        self.assertEqual(ok("jobs.lever.co/gohighlevel?lever-via=x"), ("lever", "gohighlevel"))
        self.assertEqual(ok("https://apply.workable.com/huggingface/j/F4C096B22E/"), ("workable", "huggingface"))
        self.assertIsNone(ok("https://apply.workable.com/j/F4C096B22E"))
        self.assertEqual(ok("https://jobs.smartrecruiters.com/ServiceNow/744000153020371-x"), ("smartrecruiters", "ServiceNow"))
        self.assertEqual(ok("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA/X_JR1"),
                         ("workday", "nvidia.wd5.myworkdayjobs.com|nvidia|NVIDIAExternalCareerSite"))
        self.assertEqual(ok("https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External"),
                         ("workday", "zillow.wd5.myworkdayjobs.com|zillow|Zillow_Group_External"))

    def test_rejects_other_sites_and_odd_ids(self):
        for bad in ("https://www.linkedin.com/jobs/view/123", "https://jobs.lever.co/", "not a url", "https://[::1",
                    "https://jobs.lever.co\u2100/acme", "", "https://[::1]/boards.greenhouse.io/acme",
                    "https://jobs.ashbyhq.com/acme%2F..%2Fx", "https://evil.example/boards.greenhouse.io/acme",
                    "https://jobs.lever.co/a?b/../../c d", "https://nvidia.wd5.myworkdayjobs.com/en-US"):
            got = source.parse_board_url(bad)
            self.assertTrue(got is None or source.SLUG_OK.fullmatch(got[1]), bad)
        self.assertIsNone(source.parse_board_url("https://www.linkedin.com/jobs/view/123"))
        self.assertIsNone(source.parse_board_url("https://jobs.ashbyhq.com/acme%2F..%2Fx"))
        self.assertIsNone(source.parse_board_url("https://evil.example/boards.greenhouse.io/acme"))

    def test_add_urls_respects_your_file(self):
        d = Path(tempfile.mkdtemp())
        keep = (source.STARTER, source.USER_COMPANIES, source.OUT, source.probe, source.board_name)
        try:
            source.STARTER, source.USER_COMPANIES, source.OUT = d / "starter.json", d / "mine.json", d / "sourcing"
            source.STARTER.write_text(json.dumps({"Beta Inc": [{"ats": "lever", "slug": "beta"}]}))
            source.USER_COMPANIES.write_text(json.dumps({"Acme": [], "Gamma": [{"ats": "lever", "slug": "gamma"}]}))
            source.probe = lambda ats, slug: 0 if slug == "deadco" else 5
            source.board_name = lambda ats, slug: {"acme": "ACME", "beta2": "beta", "gamma2": "gamma", "newco": "Newco"}[slug]
            source.add_urls(["https://jobs.ashbyhq.com/acme", "https://jobs.ashbyhq.com/beta2", "https://jobs.ashbyhq.com/gamma2",
                             "https://jobs.ashbyhq.com/newco", "https://jobs.ashbyhq.com/deadco", "https://jobs.lever.co/gamma/1",
                             "https://[::1", "https://example.com/x"])
            mine = json.loads(source.USER_COMPANIES.read_text())
            self.assertEqual(mine["Acme"], [])  # disabled by the user, stays disabled
            self.assertEqual([x["slug"] for x in mine["Beta Inc"]], ["beta", "beta2"])  # starter board carried over
            self.assertEqual([x["slug"] for x in mine["Gamma"]], ["gamma", "gamma2"])
            self.assertEqual(mine["Newco"], [{"ats": "ashby", "slug": "newco"}])
            self.assertEqual(sorted(mine), ["Acme", "Beta Inc", "Gamma", "Newco"])
            log = json.loads((source.OUT / "discovery-log.jsonl").read_text().splitlines()[-1])
            self.assertEqual((log["boards"], log["already_scanned"], log["dead"], log["disabled_by_you"], len(log["added"])), (6, 1, 1, 1, 3))
        finally:
            source.STARTER, source.USER_COMPANIES, source.OUT, source.probe, source.board_name = keep

    def test_fallback_name(self):
        self.assertEqual(source.board_name("lever", "clarify-health"), "Clarify Health")
        self.assertEqual(source.board_name("lever", "CollectlyInc"), "Collectly Inc")
        self.assertEqual(source.board_name("workday", "acme.wd5.myworkdayjobs.com|acme_corp|External"), "Acme Corp")


class Misc(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(source.strip_html("<p>Hi&amp;nbsp;there</p><script>x()</script><li>One</li>"), "Hi there\nOne")
        self.assertEqual(source.strip_html("&lt;strong&gt;Visa:&lt;/strong&gt; yes"), "Visa: yes")

    def test_slug_candidates(self):
        self.assertEqual(source.slug_candidates("Hugging Face")[:3], ["huggingface", "hugging-face", "HuggingFace"])
        self.assertIn("scale", source.slug_candidates("Scale AI"))

    def test_sponsorship_phrases(self):
        self.assertTrue(source.no_sponsor("We are unable to sponsor visas for this role."))
        self.assertTrue(source.no_sponsor("Candidates must be a US citizen."))
        self.assertIsNone(source.no_sponsor("We sponsor visas for this role."))
        self.assertIsNone(source.no_sponsor("No security clearance is required."))
        self.assertIsNone(source.no_sponsor("This position does not require security clearance."))
        self.assertIsNone(source.no_sponsor("An active security clearance is not required."))
        self.assertTrue(source.no_sponsor("This role requires an active security clearance."))
        self.assertTrue(source.no_sponsor("You must hold a Secret security clearance."))
        self.assertTrue(source.no_sponsor("This role not only requires security clearance."))


if __name__ == "__main__":
    unittest.main()
