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
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
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
