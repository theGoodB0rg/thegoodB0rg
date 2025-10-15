import base64
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

GITHUB_API = "https://api.github.com"
TOKEN = os.getenv("GITHUB_TOKEN", "")
USER = os.getenv("GH_PROFILE_USER", "").strip() or os.getenv("GITHUB_REPOSITORY_OWNER", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/vnd.github+json", **HEADERS})

def gh_get(url, params=None):
    r = SESSION.get(url, params=params or {})
    r.raise_for_status()
    return r.json()

def gh_paged(url, params=None):
    params = params or {}
    params.setdefault("per_page", 100)
    page = 1
    while True:
        params["page"] = page
        r = SESSION.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        for item in data:
            yield item
        if len(data) < params["per_page"]:
            break
        page += 1

def list_public_repos(user):
    return list(gh_paged(f"{GITHUB_API}/users/{user}/repos", {"type": "owner", "sort": "updated", "direction": "desc"}))

def repo_languages(owner, repo):
    try:
        return gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/languages")
    except requests.HTTPError:
        return {}

def get_file_json(owner, repo, path):
    try:
        data = gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
        if isinstance(data, dict) and "content" in data:
            content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            return json.loads(content)
    except Exception:
        pass
    return None

def file_exists(owner, repo, path):
    try:
        r = SESSION.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
        r.raise_for_status()
        return True
    except Exception:
        return False

def list_repo_paths(owner, repo, path=""):
    try:
        data = gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
        if isinstance(data, list):
            return [item.get("path", "") for item in data]
        return []
    except Exception:
        return []

def detect_stack(owner, repo):
    stacks = set()
    if file_exists(owner, repo, "Dockerfile") or file_exists(owner, repo, "docker-compose.yml"):
        stacks.add("Docker")
    if any(p.startswith(".github/workflows/") for p in list_repo_paths(owner, repo, ".github/workflows")):
        stacks.add("GitHub Actions (CI/CD)")
    tf_present = any(p.endswith(".tf") for p in list_repo_paths(owner, repo))
    if tf_present:
        stacks.add("Terraform")
    for candidate in ["k8s", "deploy", "deployments", "manifests"]:
        if file_exists(owner, repo, candidate):
            stacks.add("Kubernetes")
            break

    pkg = get_file_json(owner, repo, "package.json")
    if pkg:
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        keys = {k.lower() for k in deps.keys()}
        if "react" in keys:
            stacks.add("React")
        if "next" in keys or "nextjs" in keys or "next.js" in keys:
            stacks.add("Next.js")
        if "vue" in keys or "nuxt" in keys:
            stacks.add("Vue")
        if any(k in keys for k in ["angular", "@angular/core"]):
            stacks.add("Angular")
        if any(k in keys for k in ["svelte", "@sveltejs/kit"]):
            stacks.add("Svelte")
        if any(k in keys for k in ["express", "fastify", "koa", "nestjs", "@nestjs/core"]):
            stacks.add("Node.js API")
        if any(k in keys for k in ["typeorm", "prisma", "mongoose", "pg", "mysql", "sqlite3", "redis"]):
            stacks.add("Databases")
        if any(k in keys for k in ["tailwindcss", "vite", "webpack", "rollup"]):
            stacks.add("Frontend Tooling")

    for f in ["requirements.txt", "pyproject.toml", "Pipfile"]:
        if file_exists(owner, repo, f):
            stacks.add("Python")
            try:
                data = SESSION.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/requirements.txt").json()
                if isinstance(data, dict) and "content" in data:
                    content = base64.b64decode(data["content"]).decode("utf-8
