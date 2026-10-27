"""Tiny, read-only GitHub REST client using the Python standard library."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubError(Exception):
    """Safe errors that never quote response bodies or tokens."""


class GitHubClient:
    def __init__(self, repo, token=None):
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo)
                or repo.split("/")[1] in {".", ".."}):
            raise ValueError("Repository must be OWNER/REPO.")
        self.repo = repo
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN")

    def get(self, suffix, params=None):
        if not re.fullmatch(r"[A-Za-z0-9/_-]+", suffix):
            raise ValueError("Invalid API resource path.")
        url = "https://api.github.com/repos/" + self.repo + "/" + suffix
        if params:
            url += "?" + urlencode(params)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "smergeon/0.1",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            with urlopen(Request(url, headers=headers), timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            raise GitHubError("GitHub HTTP " + str(exc.code)
                              + ": check permissions, repository and rate limits.") from None
        except (URLError, TimeoutError, ValueError):
            raise GitHubError("Unable to read GitHub API response.") from None

    def pr(self, number):
        return self.get("pulls/" + str(number))

    def run(self, number):
        return self.get("actions/runs/" + str(number))

    def runs(self, sha):
        return self.get("actions/runs", {"head_sha": sha, "per_page": 100})

    def checks(self, sha):
        return self.get("commits/" + sha + "/check-runs", {"per_page": 100})

    def jobs(self, run_id):
        return self.get("actions/runs/" + str(run_id) + "/jobs", {"per_page": 100})

    def job_log(self, job_id, max_bytes=262144):
        """Fetch at most max_bytes from a job log, stripping auth on redirects.

        GitHub job logs typically redirect to a different HTTPS host.
        The bearer token must never follow that cross-host redirect.
        """
        from urllib.parse import urlsplit
        from urllib.request import build_opener, HTTPRedirectHandler

        class SafeLogRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                dest = urlsplit(newurl)
                if dest.scheme != "https":
                    raise GitHubError("Refusing a non-HTTPS job log redirect.")
                redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
                if redirected is not None and dest.netloc.lower() != urlsplit(req.full_url).netloc.lower():
                    redirected.remove_header("Authorization")
                return redirected

        if not isinstance(job_id, int) or job_id < 1:
            raise ValueError("Job ID must be a positive integer.")
        if not 1024 <= max_bytes <= 1048576:
            raise ValueError("Log budget must be between 1 KiB and 1 MiB.")
        url = "https://api.github.com/repos/" + self.repo + "/actions/jobs/" + str(job_id) + "/logs"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "smergeon/0.2"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            opener = build_opener(SafeLogRedirect)
            with opener.open(Request(url, headers=headers), timeout=15) as response:
                raw = response.read(max_bytes + 1)
        except HTTPError as exc:
            raise GitHubError("Job logs returned HTTP " + str(exc.code) + ".") from None
        except (URLError, TimeoutError) as exc:
            raise GitHubError("Could not read job logs: " + type(exc).__name__) from None
        truncated = len(raw) > max_bytes
        return raw[:max_bytes].decode("utf-8", errors="replace"), truncated
