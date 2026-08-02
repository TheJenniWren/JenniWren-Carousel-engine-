#!/usr/bin/env python3
"""
JenniWren Studio 3.9 — Phase 1 Baseline Protection

Run from the repository root:
    python start_studio_3_9_phase1.py

This script:
1. Runs the existing ten-template certification before any source changes.
2. Records SHA-256 hashes for the current production engine.
3. Creates a recoverable full-repository archive outside the repo.
4. Copies the locked 3.8 production modules into a separate baseline folder.
5. Commits the current working tree as the Studio 3.8 final baseline.
6. Creates the annotated tag studio-3.8-final.
7. Creates and switches to the studio-3.9-dev branch.
8. Verifies that no source files changed during the process.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINE_TAG = "studio-3.8-final"
DEV_BRANCH = "studio-3.9-dev"
BASELINE_COMMIT_MESSAGE = "Studio 3.8 final baseline"

# These files collectively preserve the reviewed production templates plus
# their registry, adapters, renderer, layout helpers, and shared drawing code.
LOCKED_CANDIDATES = [
    "explainer_templates.py",       # Standard Explainer + Timeline
    "data_templates.py",            # Stat Grid + Big Number
    "comparison_templates.py",      # Call Block + Split Screen
    "document_templates.py",        # Document Card
    "cover_templates.py",
    "carousel_lib.py",              # Sources and shared rendering
    "registry.py",
    "renderer.py",
    "render_carousel.py",
    "carousel_dashboard.py",
    "text_fitting_engine.py",
    "graph_constants.py",
    "graph_layout_helpers.py",
    "graph_draw_node.py",
    "graph_draw_connector.py",
    "DESIGN RULES.md",
]


class PhaseOneError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        detail = "\n".join(part for part in (stdout, stderr) if part)
        raise PhaseOneError(
            f"Command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd=repo, check=check).stdout.strip()


def locate_repo() -> Path:
    here = Path.cwd().resolve()
    try:
        root = run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=here,
        ).stdout.strip()
    except PhaseOneError as exc:
        raise PhaseOneError(
            "Run this script from inside the JenniWren Studio Git repository."
        ) from exc
    repo = Path(root).resolve()
    required = ["carousel_dashboard.py", "render_carousel.py"]
    missing = [name for name in required if not (repo / name).is_file()]
    if missing:
        raise PhaseOneError(
            "Repository root does not look like JenniWren Studio. Missing: "
            + ", ".join(missing)
        )
    return repo


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_snapshot(repo: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for pattern in ("*.py", "*.md", "*.json"):
        for path in sorted(repo.glob(pattern)):
            if path.is_file():
                snapshot[path.name] = sha256(path)
    return snapshot


def run_certification(repo: Path, report_dir: Path) -> dict[str, Any]:
    """
    Invoke the same production certification path used by the Studio button.
    This renders one production PNG for every supported template.
    """
    sys.path.insert(0, str(repo))
    old_cwd = Path.cwd()
    os.chdir(repo)
    try:
        import carousel_dashboard as dashboard  # type: ignore

        static_report = dashboard.certify_template_engine()
        if not static_report.get("ok"):
            raise PhaseOneError(
                "Template registry certification failed before rendering:\n"
                + json.dumps(static_report, indent=2, default=str)
            )

        payload = dashboard.template_engine_sample_story()
        story_dir = dashboard.safe_child(
            dashboard.STORIES_DIR,
            dashboard.PREVIEW_FOLDER,
        )
        dashboard.ensure_template_engine_test_asset(story_dir)

        result = dashboard.render_carousel_payload(payload)
        (
            exit_code,
            log,
            output_slug,
            render_token,
            production_payload,
            trace,
            diagnostics,
            environment,
            verdict,
            images,
        ) = result

        expected_count = len(dashboard.SUPPORTED_TEMPLATE_IDS)
        image_paths = [Path(path) for path in images if Path(path).is_file()]
        image_rows = [
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in image_paths
        ]

        report: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ok": exit_code == 0 and len(image_rows) == expected_count,
            "exit_code": exit_code,
            "expected_template_count": expected_count,
            "rendered_slide_count": len(image_rows),
            "supported_template_ids": list(dashboard.SUPPORTED_TEMPLATE_IDS),
            "output_slug": output_slug,
            "render_token": render_token,
            "images": image_rows,
            "certification": static_report,
            "verdict": verdict,
            "diagnostics": diagnostics,
            "environment": environment,
            "trace": trace,
            "production_payload": production_payload,
            "editorial_payload": payload,
            "log": log,
        }

        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "ten-template-certification.json").write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        (report_dir / "ten-template-certification.log").write_text(
            str(log),
            encoding="utf-8",
        )

        if not report["ok"]:
            raise PhaseOneError(
                "The ten-template certification did not pass. "
                f"Rendered {len(image_rows)} of {expected_count} slides. "
                f"See {report_dir / 'ten-template-certification.json'}"
            )
        return report
    finally:
        os.chdir(old_cwd)
        try:
            sys.path.remove(str(repo))
        except ValueError:
            pass


def create_archive(repo: Path, destination: Path) -> None:
    """
    Create a full recoverable repository archive, including .git and ignored
    local assets, while omitting generated output and caches.
    """
    excluded_parts = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "venv",
        "output",
    }

    def tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        relative = Path(info.name)
        if any(part in excluded_parts for part in relative.parts):
            return None
        return info

    with tarfile.open(destination, "w:gz") as archive:
        archive.add(
            repo,
            arcname=repo.name,
            recursive=True,
            filter=tar_filter,
        )


def preserve_locked_modules(repo: Path, baseline_dir: Path) -> list[dict[str, str]]:
    locked_dir = baseline_dir / "locked-production-files"
    locked_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []

    for name in LOCKED_CANDIDATES:
        source = repo / name
        if not source.is_file():
            continue
        destination = locked_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        records.append(
            {
                "file": name,
                "sha256": sha256(source),
                "purpose": "Studio 3.8 locked production baseline",
            }
        )

    if not records:
        raise PhaseOneError("No production files were found to preserve.")

    (baseline_dir / "locked-production-manifest.json").write_text(
        json.dumps(records, indent=2),
        encoding="utf-8",
    )
    return records


def ensure_identity(repo: Path) -> None:
    name = git(repo, "config", "--get", "user.name", check=False)
    email = git(repo, "config", "--get", "user.email", check=False)
    if not name:
        git(repo, "config", "user.name", "JenniWren Studio")
    if not email:
        git(repo, "config", "user.email", "studio-baseline@local.invalid")


def commit_baseline(repo: Path) -> str:
    ensure_identity(repo)
    git(repo, "add", "-A")
    staged = git(repo, "diff", "--cached", "--name-only")
    if staged:
        git(repo, "commit", "-m", BASELINE_COMMIT_MESSAGE)
    return git(repo, "rev-parse", "HEAD")


def create_exact_tag(repo: Path, baseline_commit: str) -> None:
    existing = git(
        repo,
        "rev-parse",
        "-q",
        "--verify",
        f"refs/tags/{BASELINE_TAG}",
        check=False,
    )
    if existing:
        peeled = git(repo, "rev-list", "-n", "1", BASELINE_TAG)
        if peeled != baseline_commit:
            raise PhaseOneError(
                f"Tag {BASELINE_TAG!r} already exists at {peeled}, "
                f"not the current baseline {baseline_commit}. "
                "Nothing was overwritten."
            )
        return
    git(
        repo,
        "tag",
        "-a",
        BASELINE_TAG,
        "-m",
        "JenniWren Studio 3.8 final recoverable baseline",
        baseline_commit,
    )


def create_dev_branch(repo: Path, baseline_commit: str) -> None:
    existing = git(
        repo,
        "rev-parse",
        "-q",
        "--verify",
        f"refs/heads/{DEV_BRANCH}",
        check=False,
    )
    if existing and existing != baseline_commit:
        raise PhaseOneError(
            f"Branch {DEV_BRANCH!r} already exists at {existing}, "
            f"not the new baseline {baseline_commit}. Nothing was overwritten."
        )
    if existing:
        git(repo, "switch", DEV_BRANCH)
    else:
        git(repo, "switch", "-c", DEV_BRANCH, baseline_commit)


def main() -> int:
    repo = locate_repo()
    parent = repo.parent
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    baseline_dir = parent / f"{repo.name}-studio-3.8-final-{timestamp}"
    archive_path = parent / f"{repo.name}-studio-3.8-final-{timestamp}.tar.gz"
    baseline_dir.mkdir(parents=True, exist_ok=False)

    initial_branch = git(repo, "branch", "--show-current") or "(detached HEAD)"
    before_snapshot = source_snapshot(repo)

    print("\nJenniWren Studio 3.9 — Phase 1")
    print("=" * 44)
    print(f"Repository:     {repo}")
    print(f"Starting branch:{initial_branch}")
    print("\n[1/7] Running ten-template production certification...")
    certification = run_certification(repo, baseline_dir)
    print(
        f"      PASS: {certification['rendered_slide_count']} of "
        f"{certification['expected_template_count']} templates rendered."
    )

    print("[2/7] Preserving locked Studio 3.8 production files...")
    locked = preserve_locked_modules(repo, baseline_dir)
    print(f"      Preserved {len(locked)} production/engine files.")

    print("[3/7] Writing source hash manifest...")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repository": str(repo),
        "starting_branch": initial_branch,
        "source_files": before_snapshot,
    }
    (baseline_dir / "source-sha256-manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("[4/7] Creating full recoverable repository archive...")
    create_archive(repo, archive_path)
    print(f"      Archive: {archive_path}")

    print("[5/7] Committing the Studio 3.8 final baseline...")
    baseline_commit = commit_baseline(repo)
    print(f"      Baseline commit: {baseline_commit}")

    print(f"[6/7] Creating tag {BASELINE_TAG!r}...")
    create_exact_tag(repo, baseline_commit)

    print(f"[7/7] Creating and switching to branch {DEV_BRANCH!r}...")
    create_dev_branch(repo, baseline_commit)

    after_snapshot = source_snapshot(repo)
    if before_snapshot != after_snapshot:
        changed = sorted(
            set(before_snapshot) | set(after_snapshot)
        )
        changed = [
            name
            for name in changed
            if before_snapshot.get(name) != after_snapshot.get(name)
        ]
        raise PhaseOneError(
            "Source files changed during Phase 1, which is not allowed: "
            + ", ".join(changed)
        )

    status = git(repo, "status", "--short")
    current_branch = git(repo, "branch", "--show-current")
    tag_commit = git(repo, "rev-list", "-n", "1", BASELINE_TAG)

    final_report = {
        "ok": True,
        "repository": str(repo),
        "baseline_commit": baseline_commit,
        "baseline_tag": BASELINE_TAG,
        "baseline_tag_commit": tag_commit,
        "development_branch": current_branch,
        "archive": str(archive_path),
        "baseline_folder": str(baseline_dir),
        "certified_templates": certification["supported_template_ids"],
        "rendered_slide_count": certification["rendered_slide_count"],
        "source_files_unchanged": True,
        "git_status_after": status,
    }
    (baseline_dir / "phase-1-completion-report.json").write_text(
        json.dumps(final_report, indent=2),
        encoding="utf-8",
    )

    print("\nPHASE 1 COMPLETE")
    print("=" * 44)
    print(f"✓ Ten-template certification: PASS")
    print(f"✓ Recoverable archive:        {archive_path.name}")
    print(f"✓ Baseline tag:               {BASELINE_TAG}")
    print(f"✓ Development branch:         {current_branch}")
    print(f"✓ Source files unchanged:      YES")
    if status:
        print("\nGit status contains generated or ignored-state changes:")
        print(status)
    else:
        print("✓ Git working tree:            CLEAN")
    print(f"\nReports and locked copies:\n{baseline_dir}")
    print("\nNo Studio 3.9 source changes have been applied.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PhaseOneError as exc:
        print("\nPHASE 1 STOPPED SAFELY", file=sys.stderr)
        print("=" * 44, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(
            "\nNo tag, branch, or existing file was force-overwritten.",
            file=sys.stderr,
        )
        raise SystemExit(1)
