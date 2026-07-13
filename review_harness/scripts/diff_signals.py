from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.core.schemas import ReviewRequest

SIGNAL_RULES = {
    "api_contract": {
        "paths": ("/api/", "main.py", "schema", "router", "endpoint", "controller"),
        "patch": ("status_code", "response", "request", "webhook", "http", "json"),
    },
    "security": {
        "paths": ("auth", "security", "permission", "oauth", "jwt", "secret", "token"),
        "patch": ("authorization", "credential", "password", "private_key", "secret", "token"),
    },
    "test_impact": {
        "paths": ("test", "spec", "fixture", "routing", "publisher", "prompt", "workflow"),
        "patch": ("pytest", "assert", "mock", "exception", "fallback", "return"),
    },
    "performance": {
        "paths": ("performance", "cache", "query", "database", "storage", "rag"),
        "patch": (
            "for ",
            "while ",
            "select ",
            "join ",
            "sort(",
            "sorted(",
            "list(",
            "cache",
            "batch",
            "executor",
        ),
    },
    "reliability": {
        "paths": ("workflow", "deploy", "docker", "compose", "observability", "events", "llm"),
        "patch": ("timeout", "retry", "health", "logging", "exception", "api", "database"),
    },
    "input_boundary": {
        "paths": (
            "/api/",
            "controller",
            "handler",
            "parser",
            "upload",
            "proxy",
            "subprocess",
            "query",
        ),
        "patch": (
            "request.",
            "payload",
            "execute(",
            "shell=true",
            "subprocess",
            "eval(",
            "redirect",
            "requests.get",
            "httpx",
        ),
        "require_patch": True,
    },
    "data_integrity": {
        "paths": (
            "migration",
            "schema",
            "model",
            "repository",
            "database",
            "storage",
            "sql",
        ),
        "patch": (
            "transaction",
            "commit",
            "rollback",
            "alter table",
            "foreign key",
            "unique",
            "for update",
            "insert ",
            "update ",
            "delete ",
        ),
    },
    "dependency_workflow": {
        "paths": (
            ".github/workflows/",
            "dockerfile",
            "pyproject.toml",
            "requirements",
            "package.json",
            "package-lock.json",
            "action.yml",
            "action.yaml",
        ),
        "patch": (
            "uses:",
            "permissions:",
            "from ",
            "dependencies",
            "pip install",
            "npm install",
            "image:",
        ),
    },
    "frontend": {
        "paths": (
            ".html",
            ".css",
            ".tsx",
            ".jsx",
            ".vue",
            ".svelte",
            "/components/",
            "/pages/",
            "templates/",
            "frontend/",
        ),
        "patch": (
            "onclick",
            "onkeydown",
            "aria-",
            "<button",
            "<input",
            "tabindex",
            "focus(",
        ),
    },
    "documentation_contract": {
        "paths": ("readme", "docs/", ".env.example", "openapi", "changelog", "config", "cli"),
        "patch": (
            "environment",
            "endpoint",
            "deploy",
            "rollback",
            "webhook",
            "default",
            "status_code",
            "argument",
            "command",
        ),
    },
}


def reviewable_patch_text(patch: str) -> str:
    lines: list[str] = []
    for raw_line in patch.splitlines():
        if raw_line.startswith(("@@", "+++", "---", "\\ No newline")):
            continue
        if raw_line.startswith("-"):
            continue
        if raw_line.startswith(("+", " ")):
            raw_line = raw_line[1:]
        lines.append(raw_line)
    return "\n".join(lines)


def analyze_diff(request: ReviewRequest) -> dict[str, list[str]]:
    signals: dict[str, list[str]] = {}
    failed_checks = sorted({check.kind for check in request.checks if check.is_failed})
    if failed_checks:
        signals["ci_failure"] = [f"failed_check:{kind}" for kind in failed_checks[:5]]

    for changed_file in request.changed_files:
        path = changed_file.path.lower()
        patch = reviewable_patch_text(changed_file.patch).lower()
        for signal, rules in SIGNAL_RULES.items():
            path_match = next((marker for marker in rules["paths"] if marker in path), None)
            patch_match = next((marker for marker in rules["patch"] if marker in patch), None)
            if rules.get("require_patch") and not patch_match:
                continue
            if not path_match and not patch_match:
                continue
            evidence = signals.setdefault(signal, [])
            marker = path_match or patch_match
            item = f"{changed_file.path}:{marker}"
            if item not in evidence and len(evidence) < 5:
                evidence.append(item)
    return signals


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m review_harness.scripts.diff_signals <review-request.json>")
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(analyze_diff(ReviewRequest.from_dict(payload)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
