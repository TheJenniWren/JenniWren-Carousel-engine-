#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "document_templates.py"
BACKUP = ROOT / "document_templates.py.before_evidence_document_card_v3_8_34_hotfix"


def main() -> int:
    if not TARGET.exists():
        print("ERROR: Run this file from the repository root beside document_templates.py.")
        return 1

    text = TARGET.read_text(encoding="utf-8")

    if "import re\n" in text or "import re\r\n" in text:
        print("Hotfix already applied: document_templates.py already imports re.")
        return 0

    marker = "from __future__ import annotations\n\n"
    if marker not in text:
        print("ERROR: Could not safely locate the import section in document_templates.py. No changes written.")
        return 1

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"Backup created: {BACKUP.name}")

    updated = text.replace(marker, marker + "import re\n\n", 1)
    TARGET.write_text(updated, encoding="utf-8")

    print("Evidence — Document Card v3.8.34 hotfix applied successfully.")
    print("Added the missing 're' import required by supporting-body inline emphasis parsing.")
    print("Run: python render_carousel.py stories/_studio_live_preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
