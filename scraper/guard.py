"""Enforce dashboard permissions on GitHub's side.

Runs first on every push to main. If data/settings.json changed, it checks which
sections changed and whether the person who pushed is allowed to change them
(per the users list *before* the push, so nobody can grant themselves rights).
Sections they may not change are put back as they were.

Exit code is always 0; the result is printed and written to $GITHUB_STEP_SUMMARY.
"""

import json
import os
import subprocess
import sys

from . import settings as settings_mod

PATH = "data/settings.json"


def at(rev):
    try:
        raw = subprocess.run(["git", "show", f"{rev}:{PATH}"], capture_output=True, check=True, text=True).stdout
        return json.loads(raw)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def check(old_raw, new_raw, actor, owner):
    """Return (fixed_settings_or_None, list_of_reverted_sections)."""
    old = settings_mod.normalise(old_raw)
    new = settings_mod.normalise(new_raw)
    allowed = settings_mod.user_permissions(old, actor, owner)
    reverted = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        needed = settings_mod.SECTION_PERMISSION.get(key, "settings")
        if needed not in allowed:
            reverted.append(key)
            if key in old_raw:
                new_raw[key] = old_raw[key]
            else:
                new_raw.pop(key, None)
    return (new_raw if reverted else None), reverted


def main():
    before, actor = os.environ.get("BEFORE", ""), os.environ.get("GITHUB_ACTOR", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    if not before or set(before) == {"0"}:
        print("No previous commit to compare with.")
        return 0
    old_raw, new_raw = at(before), at("HEAD")
    if old_raw is None or new_raw is None or old_raw == new_raw:
        print("Settings unchanged.")
        return 0
    fixed, reverted = check(old_raw, new_raw, actor, owner)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not reverted:
        print(f"Settings change by {actor}: allowed.")
        return 0
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n")
    msg = f"{actor} has no permission to change: {', '.join(reverted)} — these sections were restored."
    print(f"::warning::{msg}")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### ⛔ تم إلغاء تعديل غير مسموح\n\n{msg}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
