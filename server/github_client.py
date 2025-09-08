# server/github_client.py
import aiohttp
import os
from typing import Optional, Dict, Any, List

GITHUB_API = "https://api.github.com"

class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self._token = token or os.getenv("GITHUB_TOKEN", "").strip()

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get(self, session: aiohttp.ClientSession, url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        async with session.get(url, headers=self._headers(), params=params) as r:
            r.raise_for_status()
            return await r.json()

    async def repo_summary(self, session: aiohttp.ClientSession, owner: str, repo: str) -> Dict[str, Any]:
        data = await self._get(session, f"{GITHUB_API}/repos/{owner}/{repo}")
        return {
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "default_branch": data.get("default_branch"),
            "visibility": data.get("visibility"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "open_issues": data.get("open_issues_count"),
            "watchers": data.get("subscribers_count"),
            "archived": data.get("archived", False),
            "license": (data.get("license") or {}).get("spdx_id"),
            "topics": data.get("topics", []),
            "updated_at": data.get("updated_at"),
        }

    async def list_issues(
        self,
        session: aiohttp.ClientSession,
        owner: str, repo: str,
        state: str = "open",
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        params = {"state": state, "per_page": min(limit, 100)}
        if labels:
            params["labels"] = ",".join(labels)
        if assignee:
            params["assignee"] = assignee
        items = await self._get(session, f"{GITHUB_API}/repos/{owner}/{repo}/issues", params=params)
        out = []
        for it in items:
            if "pull_request" in it:
                continue
            out.append({
                "number": it["number"],
                "title": it["title"],
                "state": it["state"],
                "labels": [l["name"] for l in it.get("labels", [])],
                "author": (it.get("user") or {}).get("login"),
                "created_at": it["created_at"],
                "url": it["html_url"],
            })
            if len(out) >= limit:
                break
        return out

    async def search_issues(self, session: aiohttp.ClientSession, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        params = {"q": query, "per_page": min(limit, 100)}
        data = await self._get(session, f"{GITHUB_API}/search/issues", params=params)
        out = []
        for it in data.get("items", []):
            out.append({
                "number": it.get("number"),
                "title": it.get("title"),
                "state": it.get("state"),
                "repo": it.get("repository_url", "").split("/repos/")[-1],
                "url": it.get("html_url"),
            })
            if len(out) >= limit:
                break
        return out

    async def pr_status(self, session: aiohttp.ClientSession, owner: str, repo: str, number: int) -> Dict[str, Any]:
        pr = await self._get(session, f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}")
        sha = (pr.get("head") or {}).get("sha")
        checks = {}
        if sha:
            checks = await self._get(session, f"{GITHUB_API}/repos/{owner}/{repo}/commits/{sha}/check-runs")
        return {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "mergeable": pr.get("mergeable"),
            "draft": pr.get("draft"),
            "head_branch": (pr.get("head") or {}).get("ref"),
            "base_branch": (pr.get("base") or {}).get("ref"),
            "checks_summary": {
                "total": checks.get("total_count", 0),
                "statuses": [c["conclusion"] for c in checks.get("check_runs", []) if c.get("conclusion")],
            },
            "url": pr.get("html_url"),
        }

    async def get_file(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None
    ) -> Dict[str, Any]:
        params = {"ref": ref} if ref else None
        try:
            data = await self._get(
                session,
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                params=params
            )
        except aiohttp.ClientResponseError as e:
            # fallback: si pidieron README y no existe esa variante, usar endpoint oficial
            if e.status == 404 and path.lower() in ("readme", "readme.md", "readme.rst"):
                data = await self._get(
                    session,
                    f"{GITHUB_API}/repos/{owner}/{repo}/readme",
                    params=params
                )
            else:
                raise

        if data.get("encoding") == "base64":
            import base64
            decoded = base64.b64decode(data.get("content", "")).decode("utf-8", errors="ignore")
        else:
            decoded = data.get("content", "")

        return {
            "path": data.get("path"),
            "type": data.get("type"),
            "size": data.get("size"),
            "sha": data.get("sha"),
            "content": decoded,
        }

    async def compare(self, session: aiohttp.ClientSession, owner: str, repo: str, base: str, head: str) -> Dict[str, Any]:
        data = await self._get(session, f"{GITHUB_API}/repos/{owner}/{repo}/compare/{base}...{head}")
        files = [{
            "filename": f.get("filename"),
            "status": f.get("status"),
            "additions": f.get("additions"),
            "deletions": f.get("deletions"),
            "changes": f.get("changes"),
        } for f in data.get("files", [])]
        return {
            "ahead_by": data.get("ahead_by"),
            "behind_by": data.get("behind_by"),
            "total_commits": data.get("total_commits"),
            "files": files
        }
