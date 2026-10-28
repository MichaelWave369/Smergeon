"""Static security checks for Smergeon's optional GitHub Pages clinic."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


class PagesSiteTests(unittest.TestCase):
    def test_local_static_assets_exist(self):
        for path in ("index.html", "styles.css", "favicon.svg",
                     "app.mjs", "clinic-core.mjs", "code-brown.mjs", ".nojekyll"):
            self.assertTrue((WEB / path).exists(), path)

    def test_no_remote_script_or_font_dependency(self):
        html = (WEB / "index.html").read_text()
        self.assertIn('src="./app.mjs"', html)
        self.assertIn('href="./styles.css"', html)
        self.assertNotIn("<iframe", html)
        self.assertNotIn("fonts.googleapis", html)
        self.assertNotIn("cdn.jsdelivr", html)
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', html):
            self.assertTrue(src.startswith("./"), src)

    def test_browser_intake_has_no_token_or_mutation(self):
        source = (WEB / "app.mjs").read_text()
        for unsafe in ("localStorage", "sessionStorage", "eval(",
                       "Authorization:", 'method: "POST"',
                       'method: "PATCH"', 'method: "DELETE"',
                       "gh pr merge", "pull_request_target"):
            self.assertNotIn(unsafe, source)
        self.assertIn("https://api.github.com/repos/", source)
        self.assertIn('credentials: "omit"', source)

    def test_verdict_has_no_merge_authorization(self):
        core = (WEB / "clinic-core.mjs").read_text()
        self.assertIn("mergeApproval: false", core)
        self.assertIn("writes: false", core)
        self.assertIn("drafts: false", core)
        self.assertIn("parseTarget", core)
        self.assertIn("validateFreshPR", core)

    def test_code_brown_requires_explicit_click_and_never_grants_authority(self):
        html = (WEB / "index.html").read_text()
        browser = (WEB / "app.mjs").read_text()
        logic = (WEB / "code-brown.mjs").read_text()
        self.assertIn('id="brown-button"', html)
        self.assertIn('id="brown-results" hidden', html)
        self.assertIn('brownButton.addEventListener("click"', browser)
        self.assertIn("confirmSameCodeBrownSource", browser)
        self.assertIn("encodeURIComponent(source.branch)", browser)
        self.assertIn("READ-ONLY TREND INSPECTION COMPLETE", browser)
        for forbidden in ('method: "POST"', 'method: "PATCH"', 'method: "DELETE"',
                          "Authorization:", "localStorage", "sessionStorage"):
            self.assertNotIn(forbidden, browser + logic)
        self.assertIn("merge_authorization: false", logic)
        self.assertIn("causal_equivalence_proven: false", logic)

    def test_pages_deploy_only_from_main(self):
        deploy = (ROOT / ".github/workflows/pages.yml").read_text()
        self.assertIn("branches: [main]", deploy)
        self.assertIn("actions/upload-pages-artifact@v3", deploy)
        self.assertIn("actions/deploy-pages@v4", deploy)
        self.assertIn("path: web", deploy)
        self.assertIn("pages: write", deploy)
        self.assertNotIn("pull_request_target:", deploy)
        self.assertNotIn("\n  pull_request:", deploy)
        self.assertNotIn("git push", deploy)

    def test_ci_has_separate_web_clinic_suite(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("pages-clinic-tests:", ci)
        self.assertIn("node --test web/tests/*.test.mjs", ci)


if __name__ == "__main__":
    unittest.main()
