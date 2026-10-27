"""Explicitly authenticated write transport, separate from read-only diagnostics.

Only the operating_room.create_draft function uses this transport. No redirects,
no arbitrary hosts, no URL parameters on writes, and no token logging.
"""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .github import GitHubError, GitHubClient


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise GitHubError("Refusing redirected GitHub write or metadata request.")


class GitHubDraftWriter:
    """Small GitHub API transport. Callers must opt in to every write separately."""

    def __init__(self, repo, token=None):
        GitHubClient(repo, token=token)  # Reuse strict repository validation.
        self.repo = repo
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise GitHubError("A write-scoped GITHUB_TOKEN is required for draft PR creation.")

    def _request(self, method, resource, payload=None, params=None):
        if (not isinstance(resource, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", resource)
                or any(part in (".", "..") for part in resource.split("/"))):
            raise GitHubError("Rejected unsafe API resource path.")
        if method != "GET" and (method != "POST" or params is not None):
            raise GitHubError("Only GET and parameter-free POST are supported.")
        url = "https://api.github.com/repos/" + self.repo + "/" + resource
        if params:
            url += "?" + urlencode(params)
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "smergeon/0.5",
            "Authorization": "Bearer " + self.token,
        }
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8") \
            if method == "POST" else None
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with build_opener(_NoRedirect).open(request, timeout=15) as response:
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise GitHubError("Unexpectedly large GitHub API response.")
                return json.loads(data)
        except HTTPError as exc:
            raise GitHubError("GitHub returned HTTP " + str(exc.code)
                              + " for " + method
                              + ". Inspect access, branch state or naming collisions.") from None
        except (URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
            raise GitHubError("GitHub " + method + " failed: " + type(exc).__name__) from None

    def get(self, resource, params=None):
        return self._request("GET", resource, params=params)

    def post(self, resource, payload):
        return self._request("POST", resource, payload=payload)
