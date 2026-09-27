"""Drafts the GitHub release for the version that just landed on main.

A draft, never a published release: the notes come from the pull request's
"What this changes", and a person reads them before anybody else can. Nothing
is drafted when the version already has a release or a draft, which is every
merge that did not raise it (docs, tests, CI).

    uv run --no-project python tools/release_draft.py

Reads REPO (owner/name) and SHA (the merge commit) from the environment, and
needs an authenticated `gh`.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from version_bumped import Version, parse  # noqa: E402

TAG_PREFIX = "bea-v"
TAG = re.compile(r"^bea-v(\d+)\.(\d+)\.(\d+)$")
COMMENT = re.compile(r"<!--.*?-->", re.S)
MERGE = re.compile(r"^Merge pull request #(\d+) ")


def tag_of(version: Version) -> str:
    return TAG_PREFIX + ".".join(map(str, version))


def previous_tag(tags: List[str], version: Version) -> Optional[str]:
    """The newest app tag older than this version; mod tags never match."""
    older: List[Tuple[Version, str]] = []
    for tag in tags:
        match = TAG.match(tag.strip())
        if match:
            v = (int(match[1]), int(match[2]), int(match[3]))
            if v < version:
                older.append((v, tag.strip()))
    return max(older)[1] if older else None


def what_changes(body: str) -> str:
    """The "What this changes" section of a pull request, without the template's comments."""
    text = COMMENT.sub("", body or "").replace("\r\n", "\n")
    match = re.search(r"^##\s+What this changes\s*$(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    section = match.group(1) if match else text
    return section.strip()


def pr_numbers(subjects: List[str]) -> List[int]:
    """The pull requests merged in these first-parent commit subjects, oldest first."""
    found = [int(m[1]) for m in (MERGE.match(s) for s in subjects) if m]
    return sorted(set(found), key=found.index)


def notes(version: Version, repo: str, pr: Optional[dict], previous: Optional[str],
          sha: str, merged: Optional[List[Tuple[int, str]]] = None) -> Tuple[str, str]:
    """The title and the markdown of the draft."""
    number = f"v{'.'.join(map(str, version))}"
    if pr:
        title = f"ProjectBEA {number}: {pr['title']}"
        body = what_changes(pr.get("body") or "") or pr["title"]
        source = f"From #{pr['number']}."
    else:
        title = f"ProjectBEA {number}"
        body = "(no pull request: pushed straight to main)"
        source = f"From commit {sha[:7]}."
    lines = [body, "", "---", source]
    if merged:
        lines += ["", "**Pull requests in this version:**"]
        lines += [f"- #{number} {title}" for number, title in merged]
        lines.append("")
    if previous:
        lines.append(f"**Full changelog:** https://github.com/{repo}/compare/"
                     f"{previous}...{tag_of(version)}")
    return title, "\n".join(lines) + "\n"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True)


def _merged_pr(repo: str, sha: str) -> Optional[dict]:
    out = _run("gh", "api", f"repos/{repo}/commits/{sha}/pulls")
    if out.returncode != 0:
        print(f"could not look up the pull request: {out.stderr.strip()}", file=sys.stderr)
        return None
    merged = [p for p in json.loads(out.stdout) if p.get("merged_at")]
    return merged[0] if merged else None


def _merged_since(repo: str, previous: Optional[str], sha: str) -> List[Tuple[int, str]]:
    if previous is None:
        return []
    log = _run("git", "log", "--first-parent", "--reverse", "--format=%s", f"{previous}..{sha}")
    merged = []
    for number in pr_numbers(log.stdout.splitlines()):
        out = _run("gh", "pr", "view", str(number), "-R", repo, "--json", "title", "--jq", ".title")
        merged.append((number, out.stdout.strip() if out.returncode == 0 else ""))
    return merged


def main() -> int:
    repo, sha = os.environ.get("REPO", ""), os.environ.get("SHA", "")
    if not repo or not sha:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    version = parse((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    tag = tag_of(version)
    # gh finds drafts by tag name too, so a re-run never drafts twice
    if _run("gh", "release", "view", tag, "-R", repo).returncode == 0:
        print(f"{tag} already has a release or a draft: nothing to do.")
        return 0
    previous = previous_tag(_run("git", "tag", "-l", f"{TAG_PREFIX}*").stdout.split(), version)
    title, text = notes(version, repo, _merged_pr(repo, sha), previous, sha,
                        _merged_since(repo, previous, sha))
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
    out = _run("gh", "release", "create", tag, "-R", repo, "--draft", "--target", sha,
               "--title", title, "--notes-file", f.name)
    os.unlink(f.name)
    if out.returncode != 0:
        print(out.stderr.strip(), file=sys.stderr)
        return 1
    print(f"drafted {tag}: {out.stdout.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
