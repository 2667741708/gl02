"""Validate the project-local GL02 Blender skill pack and version locks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


EXPECTED_SKILLS = (
    "bf3d-orchestrate",
    "bf3d-geometry-audit",
    "bf3d-uv-bake",
    "bf3d-industrial-materials",
    "bf3d-light-render",
    "bf3d-gltf-handoff",
    "bf3d-visual-qa",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_ACTIVE_TOKENS = ("allowed-tools:", "mcp__blender__", "Claude Code")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 4 or lines[0] != "---":
        raise ValueError("missing opening YAML frontmatter marker")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing YAML frontmatter marker") from exc
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def parse_repo_args(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected REPO_ID=PATH, got {value!r}")
        repo_id, raw_path = value.split("=", 1)
        result[repo_id] = Path(raw_path).expanduser().resolve()
    return result


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip().lower()


def validate(args: argparse.Namespace) -> list[str]:
    root = Path(__file__).resolve().parent
    repo_root = root.parents[1]
    skills_root = root / "skills"
    errors: list[str] = []

    manifest_path = skills_root / "bundle-manifest.json"
    lock_path = skills_root / "sources.lock.json"
    for required in (manifest_path, lock_path, root / "总设计详细规划.md", root / "THIRD_PARTY_NOTICES.md"):
        if not required.is_file():
            errors.append(f"missing required file: {required}")
    if errors:
        return errors

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    locked = json.loads(lock_path.read_text(encoding="utf-8"))
    if tuple(manifest.get("skills", [])) != EXPECTED_SKILLS:
        errors.append("bundle manifest skill list does not match the expected ordered set")
    if manifest.get("entry_skill") != "bf3d-orchestrate":
        errors.append("bundle entry_skill must be bf3d-orchestrate")

    for skill_name in EXPECTED_SKILLS:
        folder = skills_root / skill_name
        skill_file = folder / "SKILL.md"
        agent_file = folder / "agents" / "openai.yaml"
        if not skill_file.is_file() or not agent_file.is_file():
            errors.append(f"{skill_name}: missing SKILL.md or agents/openai.yaml")
            continue
        text = skill_file.read_text(encoding="utf-8")
        try:
            frontmatter = parse_frontmatter(skill_file)
        except ValueError as exc:
            errors.append(f"{skill_name}: {exc}")
            continue
        if set(frontmatter) != {"name", "description"}:
            errors.append(f"{skill_name}: frontmatter keys must be only name and description")
        if frontmatter.get("name") != skill_name or not SKILL_NAME.fullmatch(skill_name):
            errors.append(f"{skill_name}: invalid or mismatched skill name")
        if not frontmatter.get("description"):
            errors.append(f"{skill_name}: description is empty")
        if len(text.splitlines()) > 500:
            errors.append(f"{skill_name}: SKILL.md exceeds 500 lines")
        for token in FORBIDDEN_ACTIVE_TOKENS:
            if token in text:
                errors.append(f"{skill_name}: contains incompatible active token {token!r}")
        if "TODO" in text:
            errors.append(f"{skill_name}: contains unresolved TODO")
        agent_text = agent_file.read_text(encoding="utf-8")
        if f"${skill_name}" not in agent_text:
            errors.append(f"{skill_name}: default_prompt does not mention ${skill_name}")

    repositories = locked.get("repositories", [])
    repo_ids = {item.get("id") for item in repositories}
    required_repos = {
        "ahujasid-blender-mcp",
        "cc-blender-skill",
        "blender-claude-plugin",
        "blendops",
        "jithinolickal-blender",
        "dcc-mcp-blender",
    }
    if repo_ids != required_repos:
        errors.append("sources lock repository set is incomplete or unexpected")
    for repo in repositories:
        repo_id = repo.get("id", "<unknown>")
        if not HEX40.fullmatch(str(repo.get("commit", ""))):
            errors.append(f"{repo_id}: invalid commit SHA")
        if not HEX40.fullmatch(str(repo.get("tree", ""))):
            errors.append(f"{repo_id}: invalid tree SHA")
        for source in repo.get("selected_files", []):
            if not source.get("path") or not HEX64.fullmatch(str(source.get("sha256", ""))):
                errors.append(f"{repo_id}: invalid selected file lock {source}")

    if not args.skip_local_source_hash:
        for source in locked.get("local_sources", []):
            raw_path = Path(source["path"])
            path = raw_path if raw_path.is_absolute() else repo_root / raw_path
            if not path.is_file():
                errors.append(f"local source missing: {path}")
                continue
            actual = sha256_file(path)
            if actual != source["sha256"]:
                errors.append(f"local source hash drift: {path} expected={source['sha256']} actual={actual}")

    upstream_roots = parse_repo_args(args.upstream_repo)
    by_id = {item["id"]: item for item in repositories}
    for repo_id, path in upstream_roots.items():
        if repo_id not in by_id:
            errors.append(f"unknown upstream repo id: {repo_id}")
            continue
        if not path.is_dir():
            errors.append(f"upstream repo path missing: {path}")
            continue
        expected_repo = by_id[repo_id]
        try:
            actual_head = git_head(path)
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"{repo_id}: cannot read git HEAD: {exc}")
            continue
        if actual_head != expected_repo["commit"]:
            errors.append(f"{repo_id}: HEAD drift expected={expected_repo['commit']} actual={actual_head}")
        for source in expected_repo.get("selected_files", []):
            source_path = path / source["path"]
            if not source_path.is_file():
                errors.append(f"{repo_id}: selected file missing: {source_path}")
            elif sha256_file(source_path) != source["sha256"]:
                errors.append(f"{repo_id}: selected file hash drift: {source_path}")

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the GL02 project-local Blender skill pack.")
    parser.add_argument(
        "--skip-local-source-hash",
        action="store_true",
        help="Skip hashes for D:/文件/pythonCAD and the current project GLB.",
    )
    parser.add_argument(
        "--upstream-repo",
        action="append",
        default=[],
        metavar="REPO_ID=PATH",
        help="Verify a checked-out upstream repository against the pinned commit and file hashes.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        errors = validate(args)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 2
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS: {len(EXPECTED_SKILLS)} skills, source lock, local hashes, and metadata are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
