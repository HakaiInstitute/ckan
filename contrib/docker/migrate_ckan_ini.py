#!/usr/bin/env python3
"""Apply the CKAN 2.9 -> 2.12 config edits to a ckan.ini.

Run this on the ckan.ini exported from a running 2.9 container:

    docker cp ckan:/srv/app/ckan.ini contrib/docker/ckan.ini
    python3 contrib/docker/migrate_ckan_ini.py contrib/docker/ckan.ini

The edits are the ones listed in step 2 of docs/UPGRADE_2.9_TO_2.12.md:

  removed   who.config_file, who.log_level, who.log_file,
            beaker.session.key, beaker.session.secret
            (repoze.who was replaced by flask-login in 2.10, and the beaker
            session settings by SECRET_KEY)
  added     SECRET_KEY, left blank so start_ckan.sh generates it on first boot
  changed   ckan.views.default_views, dropping recline_view for
            datatables_view

It edits line by line rather than going through configparser, because
configparser would discard every comment in the file. It is idempotent: a
second run reports no changes, so it is safe on an already-migrated file.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

SECTION = "app:main"

# Settings that no longer exist in CKAN 2.12.
REMOVE_KEYS = (
    "who.config_file",
    "who.log_level",
    "who.log_file",
    "beaker.session.key",
    "beaker.session.secret",
)

SECRET_KEY_BLOCK = """\
# Left blank: the base image's start_ckan.sh generates SECRET_KEY,
# WTF_CSRF_SECRET_KEY and the api_token.jwt secrets on first boot when it
# finds this key present but empty.
SECRET_KEY =
"""

DEFAULT_VIEWS_KEY = "ckan.views.default_views"
DEFAULT_VIEWS_VALUE = (
    "image_view text_view datatables_view geo_view geojson_view wmts_view"
)

# CKAN loads ckan.plugins from the ini *before* any plugin runs
# (ckan/config/environment.py calls p.load_all(), which reads
# config['ckan.plugins']). ckanext-envvars then runs as an IConfigurer and only
# loads names from CKAN__PLUGINS that are not already loaded - it never unloads
# anything. So a full list left in the ini becomes a floor the env var cannot
# lower, and a 2.9 list keeps dragging recline_view in, which has no entry
# point in 2.12. Reducing it to `envvars` hands control to CKAN__PLUGINS.
PLUGINS_KEY = "ckan.plugins"
PLUGINS_VALUE = "envvars"

SECTION_RE = re.compile(r"^\s*\[(?P<name>[^]]+)\]\s*$")


def assignment_key(line: str) -> str | None:
    """Return the key an active (uncommented) `key = value` line assigns."""
    if not line.strip() or line.lstrip().startswith(("#", ";")):
        return None
    key, sep, _ = line.partition("=")
    return key.strip() if sep else None


def migrate(text: str) -> tuple[str, list[str], list[str]]:
    """Return (new_text, changes_made, warnings)."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changes: list[str] = []
    warnings: list[str] = []

    section: str | None = None
    secret_key_seen = False
    views_seen = False
    secret_key_insert_at: int | None = None

    for line in lines:
        match = SECTION_RE.match(line)
        if match:
            section = match.group("name")
            out.append(line)
            continue

        if section != SECTION:
            out.append(line)
            continue

        key = assignment_key(line)

        if key in REMOVE_KEYS:
            changes.append(f"removed  {key}")
            # SECRET_KEY replaces the beaker session settings, so put it where
            # the first of them was rather than at the end of the section.
            if secret_key_insert_at is None and key.startswith("beaker.session."):
                secret_key_insert_at = len(out)
            continue

        if key == "SECRET_KEY":
            secret_key_seen = True
            if line.partition("=")[2].strip():
                warnings.append(
                    "SECRET_KEY already has a value; left as is. Blank it only "
                    "if you want start_ckan.sh to generate a new one, which "
                    "invalidates existing sessions."
                )
            out.append(line)
            continue

        if key == PLUGINS_KEY:
            current = line.partition("=")[2].strip()
            if current == PLUGINS_VALUE:
                out.append(line)
                continue
            if "envvars" not in current.split():
                warnings.append(
                    f"{PLUGINS_KEY} does not list `envvars`, so this "
                    f"deployment does not drive plugins from the environment. "
                    f"Left as is — remove recline_view by hand."
                )
                out.append(line)
                continue
            changes.append(
                f"changed  {PLUGINS_KEY}\n"
                f"           from: {current}\n"
                f"           to:   {PLUGINS_VALUE}\n"
                f"           (CKAN__PLUGINS now governs; the ini list was a\n"
                f"            floor the env var could not lower)"
            )
            out.append(f"{PLUGINS_KEY} = {PLUGINS_VALUE}\n")
            continue

        if key == DEFAULT_VIEWS_KEY:
            views_seen = True
            current = line.partition("=")[2].strip()
            if current == DEFAULT_VIEWS_VALUE:
                out.append(line)
                continue
            dropped = [
                v for v in current.split()
                if v not in DEFAULT_VIEWS_VALUE.split() and v != "recline_view"
            ]
            if dropped:
                warnings.append(
                    f"{DEFAULT_VIEWS_KEY} dropped non-standard view(s): "
                    f"{' '.join(dropped)}. Re-add them by hand if still wanted."
                )
            changes.append(
                f"changed  {DEFAULT_VIEWS_KEY}\n"
                f"           from: {current}\n"
                f"           to:   {DEFAULT_VIEWS_VALUE}"
            )
            out.append(f"{DEFAULT_VIEWS_KEY} = {DEFAULT_VIEWS_VALUE}\n")
            continue

        out.append(line)

    if section is None:
        raise SystemExit("error: no ini sections found - is this a ckan.ini?")

    if not secret_key_seen:
        if secret_key_insert_at is None:
            # No beaker settings to replace; put it after the section header.
            for i, line in enumerate(out):
                m = SECTION_RE.match(line)
                if m and m.group("name") == SECTION:
                    secret_key_insert_at = i + 1
                    break
        if secret_key_insert_at is None:
            raise SystemExit(f"error: no [{SECTION}] section found")
        out[secret_key_insert_at:secret_key_insert_at] = [SECRET_KEY_BLOCK]
        changes.append("added    SECRET_KEY (blank)")

    if not views_seen:
        warnings.append(
            f"{DEFAULT_VIEWS_KEY} not found; CKAN will fall back to its "
            f"default. Add it explicitly if this deployment relies on a "
            f"specific set."
        )

    return "".join(out), changes, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the CKAN 2.9 -> 2.12 config edits to a ckan.ini.")
    parser.add_argument(
        "path", nargs="?", default="contrib/docker/ckan.ini", type=Path,
        help="ini file to edit (default: contrib/docker/ckan.ini)")
    parser.add_argument(
        "-n", "--dry-run", action="store_true",
        help="report what would change without writing")
    parser.add_argument(
        "--no-backup", action="store_true",
        help="do not write a .bak alongside the edited file")
    args = parser.parse_args()

    if not args.path.is_file():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 1

    original = args.path.read_text()
    migrated, changes, warnings = migrate(original)

    for change in changes:
        print(f"  {change}")
    for warning in warnings:
        print(f"  warning: {warning}")

    if not changes:
        print(f"  no changes needed - {args.path} is already on 2.12 settings")
        return 0

    if args.dry_run:
        print(f"\ndry run: {args.path} not written")
        return 0

    if not args.no_backup:
        backup = args.path.with_suffix(args.path.suffix + ".bak")
        shutil.copy2(args.path, backup)
        print(f"\n  backup   {backup}")

    args.path.write_text(migrated)
    print(f"  wrote    {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
