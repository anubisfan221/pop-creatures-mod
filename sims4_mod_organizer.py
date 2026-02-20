#!/usr/bin/env python3
"""AI-assisted Sims 4 mods folder scanner and organizer.

The script walks a Sims 4 Mods directory, builds an inventory report, and can
optionally move files into categorized folders. Categories are inferred using:
1) deterministic filename/path rules
2) optional OpenAI-compatible model classification fallback

Supported file types:
- .package
- .ts4script
- .zip/.rar/.7z (archives)
- images/text/readme metadata files
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib import error, request

RULES: Dict[str, Sequence[str]] = {
    "Gameplay": ("gameplay", "overhaul", "tuning", "autonomy", "behavior"),
    "CAS": ("cas", "hair", "skin", "makeup", "eyebrow", "beard", "lashes"),
    "BuildBuy": ("build", "buy", "furniture", "decor", "object", "wall", "floor"),
    "Script": ("script", "ts4script", "python", "injector", "core"),
    "Traits": ("trait", "personality", "aspiration"),
    "Careers": ("career", "job", "promotion"),
    "Events": ("holiday", "festival", "event", "party"),
    "Animations": ("animation", "pose", "walkstyle"),
    "Presets": ("preset", "slider"),
    "UI": ("ui", "interface", "hud", "menu"),
    "Worlds": ("world", "map", "lot", "venue"),
    "Unsorted": (),
}

MOVEABLE_EXTENSIONS = {".package", ".ts4script", ".zip", ".rar", ".7z"}
REPORT_EXTENSIONS = MOVEABLE_EXTENSIONS | {".txt", ".md", ".png", ".jpg", ".jpeg", ".gif"}


@dataclass
class ModFile:
    path: Path
    relative_path: Path
    extension: str
    size: int
    sha256: str
    category: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan and organize The Sims 4 Mods folder with optional AI classification."
    )
    parser.add_argument("mods_dir", type=Path, help="Path to The Sims 4 Mods folder")
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("mod_scan_report.json"),
        help="Where to write the JSON report (default: mod_scan_report.json)",
    )
    parser.add_argument(
        "--organize",
        action="store_true",
        help="Move files into category subfolders (dry-run unless --apply is set)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform file moves. Without this flag, moves are only previewed.",
    )
    parser.add_argument(
        "--max-ai-calls",
        type=int,
        default=30,
        help="Maximum number of files to send to AI fallback classification.",
    )
    parser.add_argument(
        "--ai-model",
        default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        help="Model name for AI fallback. Uses OpenAI-compatible chat completions API.",
    )
    return parser.parse_args()


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and ".organizer" not in path.parts:
            yield path


def file_sha256(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def rule_based_category(path: Path) -> Tuple[str, str]:
    haystack = str(path).lower()

    if path.suffix.lower() == ".ts4script":
        return "Script", "extension=.ts4script"

    for category, keywords in RULES.items():
        for keyword in keywords:
            if keyword in haystack:
                return category, f"keyword={keyword}"
    return "Unsorted", "no-rule-match"


def ai_category(path: Path, model: str) -> Optional[Tuple[str, str]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    url = f"{base_url.rstrip('/')}/chat/completions"

    prompt = (
        "Classify this Sims 4 mod file path into one category: "
        + ", ".join(RULES.keys())
        + ". Respond only as JSON like {\"category\":\"CAS\"}.\n"
        + f"path: {path}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You classify Sims 4 mods."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }

    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    try:
        content = body["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        category = parsed.get("category", "Unsorted")
        if category not in RULES:
            category = "Unsorted"
        return category, "ai-fallback"
    except (KeyError, IndexError, json.JSONDecodeError, AttributeError):
        return None


def planned_destination(mods_dir: Path, file: ModFile) -> Path:
    name = file.path.name
    return mods_dir / file.category / name


def ensure_unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    parent = dest.parent
    idx = 2
    while True:
        candidate = parent / f"{stem} ({idx}){suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def move_files(mods_dir: Path, files: Sequence[ModFile], apply: bool) -> List[str]:
    actions: List[str] = []
    for file in files:
        if file.extension not in MOVEABLE_EXTENSIONS:
            continue

        destination = ensure_unique_destination(planned_destination(mods_dir, file))
        if destination.resolve() == file.path.resolve():
            continue

        actions.append(f"{file.relative_path} -> {destination.relative_to(mods_dir)}")
        if apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file.path), str(destination))

    return actions


def build_report(mods_dir: Path, files: Sequence[ModFile], actions: Sequence[str]) -> dict:
    by_category = Counter(file.category for file in files)
    by_extension = Counter(file.extension for file in files)

    duplicates: Dict[str, List[str]] = defaultdict(list)
    for file in files:
        duplicates[file.sha256].append(str(file.relative_path))
    duplicate_groups = [paths for paths in duplicates.values() if len(paths) > 1]

    return {
        "scanned_at": datetime.utcnow().isoformat() + "Z",
        "mods_dir": str(mods_dir),
        "total_files": len(files),
        "category_breakdown": dict(by_category),
        "extension_breakdown": dict(by_extension),
        "duplicates": duplicate_groups,
        "actions": list(actions),
        "files": [
            {
                "path": str(file.relative_path),
                "extension": file.extension,
                "size": file.size,
                "sha256": file.sha256,
                "category": file.category,
                "reason": file.reason,
            }
            for file in files
        ],
    }


def main() -> int:
    args = parse_args()
    mods_dir = args.mods_dir.expanduser().resolve()

    if not mods_dir.exists() or not mods_dir.is_dir():
        print(f"Error: invalid mods directory: {mods_dir}", file=sys.stderr)
        return 2

    discovered_files: List[ModFile] = []
    ai_attempts = 0

    for path in iter_files(mods_dir):
        extension = path.suffix.lower()
        if extension not in REPORT_EXTENSIONS:
            continue

        category, reason = rule_based_category(path)
        if category == "Unsorted" and ai_attempts < args.max_ai_calls:
            ai_result = ai_category(path.relative_to(mods_dir), args.ai_model)
            if ai_result:
                category, reason = ai_result
            ai_attempts += 1

        discovered_files.append(
            ModFile(
                path=path,
                relative_path=path.relative_to(mods_dir),
                extension=extension,
                size=path.stat().st_size,
                sha256=file_sha256(path),
                category=category,
                reason=reason,
            )
        )

    actions: List[str] = []
    if args.organize:
        actions = move_files(mods_dir, discovered_files, apply=args.apply)

    report = build_report(mods_dir, discovered_files, actions)
    args.output_report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Scanned {report['total_files']} files in: {mods_dir}")
    print(f"Report written to: {args.output_report.resolve()}")
    if args.organize:
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"Organize mode: {mode}; actions={len(actions)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
