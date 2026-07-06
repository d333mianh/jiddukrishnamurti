#!/usr/bin/env python3
"""Sync the tracked concept vocabulary into the generated corpus database.

The input is JSONL, one concept object per non-blank line::

    {"slug":"fear","name":"Fear","status":"pilot",
     "definition":"...","include_criteria":"...","exclude_criteria":"...",
     "aliases":[{"alias":"fright","language":"en","period_note":null}],
     "relations":[{"to":"thought","relation":"related","note":"..."}]}

``slug``, ``name``, ``status``, and ``definition`` are required. Criteria may
be null. ``aliases`` and ``relations`` default to empty lists. The JSONL file
is authoritative for aliases and outgoing relations, but concepts omitted
from it are retained and reported.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSONL = ROOT / "concepts" / "concepts.jsonl"
DEFAULT_DB = ROOT / "corpus" / "krishnamurti-corpus.db"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concept_schema import ensure_concept_schema  # noqa: E402
from segment_schema import utc_now  # noqa: E402

STATUSES = {"pilot", "active", "deprecated"}
RELATIONS = {"broader", "related", "contrasts_with"}


class ValidationError(ValueError):
    """An actionable error in the authored JSONL."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    concepts: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_no}: concept must be a JSON object")
            continue
        value["_line"] = line_no
        concepts.append(value)
    if errors:
        raise ValidationError("\n".join(errors))
    return concepts


def validate(concepts: list[dict[str, Any]], existing: set[str]) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    file_slugs: set[str] = set()
    for item in concepts:
        line = item["_line"]
        for field in ("slug", "name", "status", "definition"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"line {line}: {field!r} must be a non-empty string")
        slug = item.get("slug")
        if isinstance(slug, str) and slug.strip():
            key = slug.casefold()
            if key in seen:
                errors.append(f"line {line}: duplicate slug {slug!r} (case-insensitive)")
            seen.add(key)
            file_slugs.add(key)
        if item.get("status") not in STATUSES:
            errors.append(
                f"line {line}: invalid status {item.get('status')!r}; "
                f"expected one of {', '.join(sorted(STATUSES))}"
            )
        for field in ("include_criteria", "exclude_criteria"):
            if item.get(field) is not None and not isinstance(item.get(field), str):
                errors.append(f"line {line}: {field!r} must be a string or null")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            errors.append(f"line {line}: 'aliases' must be a list")
            aliases = []
        alias_seen: set[str] = set()
        for alias in aliases:
            if not isinstance(alias, dict) or not isinstance(alias.get("alias"), str) or not alias["alias"].strip():
                errors.append(f"line {line}: each alias needs a non-empty 'alias' string")
                continue
            key = alias["alias"].casefold()
            if key in alias_seen:
                errors.append(f"line {line}: duplicate alias {alias['alias']!r}")
            alias_seen.add(key)
            if not isinstance(alias.get("language", "en"), str) or not alias.get("language", "en"):
                errors.append(f"line {line}: alias language must be a non-empty string")
            if alias.get("period_note") is not None and not isinstance(alias.get("period_note"), str):
                errors.append(f"line {line}: alias period_note must be a string or null")
        relations = item.get("relations", [])
        if not isinstance(relations, list):
            errors.append(f"line {line}: 'relations' must be a list")
            relations = []
        relation_seen: set[tuple[str, str]] = set()
        for relation in relations:
            if not isinstance(relation, dict):
                errors.append(f"line {line}: each relation must be an object")
                continue
            target, kind = relation.get("to"), relation.get("relation")
            if not isinstance(target, str) or not target.strip():
                errors.append(f"line {line}: relation 'to' must be a non-empty string")
                continue
            target_key = target.casefold()
            if target_key == (slug.casefold() if isinstance(slug, str) else None):
                errors.append(f"line {line}: self-relation for {slug!r} is not allowed")
            if kind not in RELATIONS:
                errors.append(
                    f"line {line}: invalid relation {kind!r}; "
                    f"expected one of {', '.join(sorted(RELATIONS))}"
                )
            key = (target_key, str(kind))
            if key in relation_seen:
                errors.append(f"line {line}: duplicate relation to {target!r} of type {kind!r}")
            relation_seen.add(key)
            if relation.get("note") is not None and not isinstance(relation.get("note"), str):
                errors.append(f"line {line}: relation note must be a string or null")
    known = file_slugs | existing
    for item in concepts:
        for relation in item.get("relations", []) if isinstance(item.get("relations", []), list) else []:
            if isinstance(relation, dict) and isinstance(relation.get("to"), str):
                if relation["to"].casefold() not in known:
                    errors.append(
                        f"line {item['_line']}: relation target {relation['to']!r} "
                        "is not defined in the file or database"
                    )
    if errors:
        raise ValidationError("\n".join(errors))


def existing_slugs(conn: sqlite3.Connection) -> set[str]:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='concepts'"
    ).fetchone()
    if not table:
        return set()
    return {row[0].casefold() for row in conn.execute("SELECT slug FROM concepts")}


def sync(conn: sqlite3.Connection, concepts: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"concepts": 0, "versions": 0, "aliases_added": 0,
              "aliases_deleted": 0, "relations_added": 0, "relations_deleted": 0}
    now = utc_now()
    # Pass one creates every file-defined concept, enabling forward references.
    for item in concepts:
        row = conn.execute("SELECT id,name,status FROM concepts WHERE slug=?", (item["slug"],)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO concepts(slug,name,status,created_at) VALUES(?,?,?,?)",
                (item["slug"], item["name"], item["status"], now),
            )
            counts["concepts"] += 1
        elif (row[1], row[2]) != (item["name"], item["status"]):
            conn.execute("UPDATE concepts SET name=?,status=? WHERE id=?", (item["name"], item["status"], row[0]))
            counts["concepts"] += 1

    ids = {row[0].casefold(): row[1] for row in conn.execute("SELECT slug,id FROM concepts")}
    for item in concepts:
        concept_id = ids[item["slug"].casefold()]
        latest = conn.execute(
            "SELECT version,definition,include_criteria,exclude_criteria FROM concept_versions "
            "WHERE concept_id=? ORDER BY version DESC LIMIT 1", (concept_id,),
        ).fetchone()
        triple = (item["definition"], item.get("include_criteria"), item.get("exclude_criteria"))
        if latest is None or tuple(latest[1:]) != triple:
            conn.execute(
                "INSERT INTO concept_versions(concept_id,version,definition,include_criteria,exclude_criteria,created_at) "
                "VALUES(?,?,?,?,?,?)", (concept_id, 1 if latest is None else latest[0] + 1, *triple, now),
            )
            counts["versions"] += 1

        desired_aliases = {a["alias"].casefold(): a for a in item.get("aliases", [])}
        current_aliases = {row[1].casefold(): row for row in conn.execute(
            "SELECT id,alias,language,period_note FROM concept_aliases WHERE concept_id=?", (concept_id,)
        )}
        for key, row in current_aliases.items():
            if key not in desired_aliases:
                conn.execute("DELETE FROM concept_aliases WHERE id=?", (row[0],))
                counts["aliases_deleted"] += 1
        for key, alias in desired_aliases.items():
            row = current_aliases.get(key)
            values = (alias.get("language", "en"), alias.get("period_note"))
            if row is None:
                conn.execute("INSERT INTO concept_aliases(concept_id,alias,language,period_note) VALUES(?,?,?,?)",
                             (concept_id, alias["alias"], *values))
                counts["aliases_added"] += 1
            elif (row[1], row[2], row[3]) != (alias["alias"], *values):
                conn.execute("UPDATE concept_aliases SET alias=?,language=?,period_note=? WHERE id=?",
                             (alias["alias"], *values, row[0]))

        desired_relations = {(ids[r["to"].casefold()], r["relation"]): r for r in item.get("relations", [])}
        current_relations = {(row[1], row[2]): row for row in conn.execute(
            "SELECT id,dst_concept_id,relation,note FROM concept_relations WHERE src_concept_id=?", (concept_id,)
        )}
        for key, row in current_relations.items():
            if key not in desired_relations:
                conn.execute("DELETE FROM concept_relations WHERE id=?", (row[0],))
                counts["relations_deleted"] += 1
        for key, relation in desired_relations.items():
            row = current_relations.get(key)
            if row is None:
                conn.execute("INSERT INTO concept_relations(src_concept_id,dst_concept_id,relation,note,created_at) VALUES(?,?,?,?,?)",
                             (concept_id, key[0], key[1], relation.get("note"), now))
                counts["relations_added"] += 1
            elif row[3] != relation.get("note"):
                conn.execute("UPDATE concept_relations SET note=? WHERE id=?", (relation.get("note"), row[0]))
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync tracked concept JSONL into the corpus DB")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        concepts = load_jsonl(args.jsonl)
        connection_target: str | Path = (
            ":memory:" if args.dry_run and not args.db.exists() else args.db
        )
        conn = sqlite3.connect(connection_target)
        conn.execute("PRAGMA foreign_keys = ON")
        existing = existing_slugs(conn)
        validate(concepts, existing)
        missing = sorted(existing - {item["slug"].casefold() for item in concepts})
        for slug in missing:
            print(f"WARNING: concept {slug!r} is absent from JSONL; retaining it (use status 'deprecated' instead)")
        if args.dry_run:
            work = sqlite3.connect(":memory:")
            work.execute("PRAGMA foreign_keys = ON")
            conn.backup(work)
            ensure_concept_schema(work)
            work.commit()
            work.execute("BEGIN")
            counts = sync(work, concepts)
            work.rollback()
            work.close()
            prefix = "Dry run; planned changes"
        else:
            ensure_concept_schema(conn)
            conn.commit()
            conn.execute("BEGIN")
            counts = sync(conn, concepts)
            conn.commit()
            prefix = "Imported changes"
        print(prefix + ": " + ", ".join(f"{key}={value}" for key, value in counts.items()))
        return 0
    except (ValidationError, sqlite3.IntegrityError) as exc:
        if "conn" in locals():
            conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
