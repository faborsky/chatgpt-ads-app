#!/usr/bin/env python3
"""Mechanical CLI ↔ docs ↔ skill consistency checker.

Checks:
 1. Every CLI command appears in README.md.
 2. `## Commands (N` count in CLAUDE.md equals the number of CLI commands.
 3. __version__ appears in README.md and CHANGELOG.md.
 4. No phantom command references (command-shaped tokens that don't exist)
    in README / CLAUDE.md / docs / bundled skill.
 5. The bundled skill still carries the <CHATGPT_ADS_APP_DIR> placeholder.

Parser/dispatch parity is guaranteed by construction (one _cmd() call per
command in oaiads/cli.py). Exit 0 = OK, exit 1 = findings (stderr).
"""

from __future__ import annotations

import glob
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOC_FILES = ["README.md", "CLAUDE.md", "docs/api-notes.md", "skill/INSTALL.md"] + [
    os.path.relpath(p, BASE) for p in glob.glob(os.path.join(BASE, "skill", "chatgpt-ads", "*.md"))
]

COMMAND_PREFIXES = (
    "campaign-", "adgroup-", "ad-", "image-", "file-", "spend-limit", "negative-keywords",
    "account-", "api-", "brand-", "landing-", "conversion-", "audience-", "pixel-", "capi-",
    "event-setting", "feed-", "lead-", "business-agent", "bulk-", "partner-", "geo-",
)

ALLOWED_NON_COMMANDS = {
    "ad-account", "ad-group", "ad-groups", "ad-hoc", "api-notes", "api-key", "api-keys", "feed-id",
    "campaign-id", "ad-id", "ad-group-id", "file-id", "audience-id", "bulk-api", "lead-form", "lead-forms",
    "conversion-optimized", "landing-page", "business-agents", "ad-review-feedback", "geo-targets",
    "api-overview", "api-reference", "spend-limit-windows", "negative-keywords-list",
}


def read(path: str) -> str:
    with open(os.path.join(BASE, path), encoding="utf-8") as f:
        return f.read()


def cli_commands() -> list[str]:
    src = read("oaiads/cli.py")
    names = re.findall(r'_cmd\(sub, "([a-z0-9-]+)"', src)
    # f-string registrations inside loops: f"campaign-{action}" etc.
    for prefix, actions in re.findall(r'_cmd\(sub, f"([a-z0-9-]+)\{action\}", fn, [^)]*?\)\s*\n', src):
        pass
    loops = re.findall(r'for action, fn in \((.*?)\):\s*\n\s*sp = _cmd\(sub, f"([a-z0-9-]+)\{action\}"', src, flags=re.S)
    for tuple_src, prefix in loops:
        for action in re.findall(r'\("([a-z]+)",', tuple_src):
            names.append(f"{prefix}{action}")
    return names


def main() -> int:
    findings: list[str] = []
    commands = cli_commands()
    if not commands:
        print("FATAL: no commands discovered in oaiads/cli.py", file=sys.stderr)
        return 1
    dupes = {c for c in commands if commands.count(c) > 1}
    if dupes:
        findings.append(f"duplicate command registrations: {sorted(dupes)}")

    readme = read("README.md")
    for cmd in commands:
        if f"`{cmd}`" not in readme and f"`{cmd} " not in readme:
            findings.append(f"README.md: command `{cmd}` missing")

    claude = read("CLAUDE.md")
    m = re.search(r"## Commands \((\d+)", claude)
    if not m:
        findings.append("CLAUDE.md: '## Commands (N' heading not found")
    elif int(m.group(1)) != len(commands):
        findings.append(f"CLAUDE.md: command count {m.group(1)} != actual {len(commands)}")

    vm = re.search(r'__version__ = "([^"]+)"', read("oaiads/__init__.py"))
    if not vm:
        findings.append("oaiads/__init__.py: __version__ not found")
    else:
        version = vm.group(1)
        if version not in readme:
            findings.append(f"README.md: version {version} not mentioned")
        if f"[{version}]" not in read("CHANGELOG.md"):
            findings.append(f"CHANGELOG.md: no [{version}] entry")

    known = set(commands) | ALLOWED_NON_COMMANDS
    for doc in DOC_FILES:
        if not os.path.exists(os.path.join(BASE, doc)):
            findings.append(f"missing doc file: {doc}")
            continue
        text = read(doc)
        for token in set(re.findall(r"`([a-z][a-z0-9-]+)`", text)):
            if token.endswith("-") or token in known:
                continue
            if token.startswith(COMMAND_PREFIXES) and "-" in token:
                findings.append(f"{doc}: phantom command-like token `{token}`")

    skill = read("skill/chatgpt-ads/SKILL.md")
    if "<CHATGPT_ADS_APP_DIR>" not in skill:
        findings.append("skill/chatgpt-ads/SKILL.md: placeholder <CHATGPT_ADS_APP_DIR> missing (repo copy must stay generic)")

    if findings:
        print(f"{len(findings)} finding(s):", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"OK: {len(commands)} commands consistent across CLI, README, CLAUDE.md, docs and skill.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
