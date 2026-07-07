#!/usr/bin/env python3
"""Build, submit, monitor, and import the L3 concept-tagging pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "corpus" / "krishnamurti-corpus.db"
RUNS_DIR = ROOT / "concepts" / "pilot-runs"
EVAL_SET = "pilot-2026-07"
DEFAULT_MODEL = "claude-sonnet-5"
PROMPT_VERSION = "concept-pilot-v2"
CONFIDENCE = {"low": 0.33, "medium": 0.67, "high": 1.0}
RELEVANCE = ("substantive", "mention_only", "not_relevant")
DEFINITION_LIKE = ("yes", "no", "unsure", "not_applicable")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concept_schema import ensure_concept_schema  # noqa: E402
from segment_schema import utc_now  # noqa: E402


@dataclass(frozen=True)
class Concept:
    id: int
    version_id: int
    slug: str
    name: str
    definition: str
    include_criteria: str | None
    exclude_criteria: str | None


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_concepts(
    conn: sqlite3.Connection, slugs: list[str] | tuple[str, ...] | None = None
) -> list[Concept]:
    where = "WHERE c.status IN ('active','pilot')"
    params: tuple[str, ...] = ()
    if slugs is not None:
        if not slugs:
            raise ValueError("concept list is empty")
        placeholders = ",".join("?" for _ in slugs)
        where = f"WHERE c.slug IN ({placeholders})"
        params = tuple(slugs)
    rows = conn.execute(
        f"""SELECT c.id,cv.id,c.slug,c.name,cv.definition,
                   cv.include_criteria,cv.exclude_criteria
              FROM concepts AS c
              JOIN concept_versions AS cv ON cv.id=(
                  SELECT id FROM concept_versions
                   WHERE concept_id=c.id ORDER BY version DESC LIMIT 1)
             {where}
             ORDER BY c.id""",
        params,
    ).fetchall()
    if slugs is None:
        return [Concept(*row) for row in rows]
    by_slug = {row[2]: Concept(*row) for row in rows}
    missing = [slug for slug in slugs if slug not in by_slug]
    if missing:
        raise ValueError(f"missing concepts/current versions: {', '.join(missing)}")
    return [by_slug[slug] for slug in slugs]


def system_prompt(concepts: list[Concept]) -> str:
    sections = [
        "Judge each concept's relevance to the passage. Use substantive when the "
        "passage develops or examines the concept; mention_only when the concept is "
        "named or touched but not developed; and not_relevant when it is absent. "
        "Set definition_like to yes only when the passage gives a crisp definition or "
        "formulation of the concept, no when it does not, unsure when borderline, and "
        "not_applicable when the concept is not relevant. Return only the requested JSON. "
        "Keep each rationale to one short sentence."
    ]
    for concept in concepts:
        sections.append(
            f"Concept: {concept.name} ({concept.slug})\n"
            f"Definition: {concept.definition}\n"
            f"Include: {concept.include_criteria or 'No additional criteria.'}\n"
            f"Exclude: {concept.exclude_criteria or 'No additional criteria.'}"
        )
    return "\n\n".join(sections)


def output_schema(concepts: list[Concept]) -> dict[str, Any]:
    judgment = {
        "type": "object",
        "properties": {
            "relevance": {"type": "string", "enum": list(RELEVANCE)},
            "confidence": {"type": "string", "enum": list(CONFIDENCE)},
            "definition_like": {"type": "string", "enum": list(DEFINITION_LIKE)},
            "rationale": {"type": "string", "maxLength": 300},
        },
        "required": ["relevance", "confidence", "definition_like", "rationale"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {concept.slug: judgment for concept in concepts},
        "required": [concept.slug for concept in concepts],
        "additionalProperties": False,
    }


def load_passages(conn: sqlite3.Connection, eval_set: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT a.id,a.item_code,a.text,a.transcript_kind,
                  a.transcript_language,t.event_type,ep.stratum_json
             FROM eval_sets AS es
             JOIN eval_set_passages AS ep ON ep.eval_set_id=es.id
             JOIN passage_anchors AS a ON a.id=ep.anchor_id
        LEFT JOIN transcripts AS t
               ON t.item_code=a.item_code AND t.kind=a.transcript_kind
              AND t.language=a.transcript_language
            WHERE es.name=? ORDER BY a.id""",
        (eval_set,),
    ).fetchall()
    if not rows:
        raise ValueError(f"eval set {eval_set!r} has no passages")
    return rows


def assemble_requests(
    conn: sqlite3.Connection, eval_set: str = EVAL_SET,
    model: str = DEFAULT_MODEL, concept_slugs: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[Concept], str]:
    concepts = load_concepts(conn, concept_slugs)
    prompt = system_prompt(concepts)
    schema = output_schema(concepts)
    requests = []
    for row in load_passages(conn, eval_set):
        metadata = [f"item_code: {row['item_code']}"]
        if row["event_type"]:
            metadata.append(f"event_type: {row['event_type']}")
        try:
            stratum = json.loads(row["stratum_json"] or "{}")
        except json.JSONDecodeError:
            stratum = {}
        if stratum.get("decade"):
            metadata.append(f"decade: {stratum['decade']}")
        requests.append({
            "custom_id": str(row["id"]),
            "params": {
                "model": model,
                "max_tokens": 8000,
                "thinking": {"type": "disabled"},
                "system": [{
                    "type": "text", "text": prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                "messages": [{
                    "role": "user",
                    "content": "\n".join(metadata) + "\n\nPassage:\n" + row["text"],
                }],
                "output_config": {
                    "format": {"type": "json_schema", "schema": schema}
                },
            },
        })
    return requests, concepts, prompt


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_state(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "state.json"
    if not path.is_file():
        raise ValueError(f"state file not found: {path}; run --submit first")
    return json.loads(path.read_text(encoding="utf-8"))


def require_client() -> Any:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY is unset")
    try:
        import anthropic
    except ImportError as exc:
        raise ValueError("anthropic package is not installed; install it in .venv") from exc
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def sdk_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"unsupported SDK result object: {type(value).__name__}")


def parse_result(value: Any) -> tuple[str, str, dict[str, Any] | None, str | None]:
    row = sdk_dict(value)
    custom_id = str(row.get("custom_id", ""))
    result = row.get("result") or {}
    result_type = result.get("type")
    if result_type != "succeeded":
        return custom_id, "api_error", None, json.dumps(result, sort_keys=True)
    message = result.get("message") or {}
    blocks = message.get("content") or []
    text = next((block.get("text") for block in blocks
                 if block.get("type") == "text" and isinstance(block.get("text"), str)), None)
    if text is None:
        return custom_id, "parse_error", None, "successful result has no text block"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return custom_id, "parse_error", None, f"invalid JSON: {exc}"
    return custom_id, "completed", payload, None


def validate_payload(payload: dict[str, Any], concepts: list[Concept]) -> None:
    expected = {concept.slug for concept in concepts}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("result concept keys do not match requested concepts")
    for slug, judgment in payload.items():
        if not isinstance(judgment, dict) or set(judgment) != {
            "relevance", "confidence", "definition_like", "rationale"
        }:
            raise ValueError(f"invalid judgment shape for {slug}")
        if not isinstance(judgment["relevance"], str) or judgment["relevance"] not in RELEVANCE:
            raise ValueError(f"invalid relevance for {slug}")
        if not isinstance(judgment["confidence"], str) or judgment["confidence"] not in CONFIDENCE:
            raise ValueError(f"invalid confidence for {slug}")
        if not isinstance(judgment["definition_like"], str) or judgment["definition_like"] not in DEFINITION_LIKE:
            raise ValueError(f"invalid definition_like value for {slug}")
        if not isinstance(judgment["rationale"], str) or len(judgment["rationale"]) > 300:
            raise ValueError(f"invalid rationale for {slug}")


def ensure_run(
    conn: sqlite3.Connection, run_name: str, concepts: list[Concept], prompt: str,
    model: str = DEFAULT_MODEL, eval_set: str = EVAL_SET,
    batch_id: str | None = None,
) -> int:
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    params = json.dumps({
        "eval_set": eval_set, "model": model, "max_tokens": 8000,
        "thinking": {"type": "disabled"},
        "concept_version_ids": {c.slug: c.version_id for c in concepts},
    }, sort_keys=True)
    conn.execute(
        """INSERT INTO model_runs(
               run_key,purpose,model,prompt_sha256,prompt_version,params_json,status,started_at)
           VALUES(?,'eval',?,?,?,?, 'running',?)
           ON CONFLICT(run_key) DO UPDATE SET
               model=excluded.model,prompt_sha256=excluded.prompt_sha256,
               prompt_version=excluded.prompt_version,params_json=excluded.params_json,
               status='running',started_at=COALESCE(model_runs.started_at,excluded.started_at)""",
        (run_name, model, prompt_hash, PROMPT_VERSION, params, utc_now()),
    )
    run_id = int(conn.execute("SELECT id FROM model_runs WHERE run_key=?", (run_name,)).fetchone()[0])
    if batch_id:
        conn.execute(
            """INSERT INTO model_batches(run_id,batch_id,submitted_at,status)
               VALUES(?,?,?,'submitted') ON CONFLICT(run_id,batch_id) DO NOTHING""",
            (run_id, batch_id, utc_now()),
        )
    return run_id


def import_results(
    conn: sqlite3.Connection, run_name: str, batch_id: str,
    results: Iterable[Any], raw_path: Path | None = None,
    model: str = DEFAULT_MODEL, eval_set: str = EVAL_SET,
    concept_slugs: list[str] | None = None,
) -> dict[str, int]:
    concepts = load_concepts(conn, concept_slugs)
    prompt = system_prompt(concepts)
    run_id = ensure_run(conn, run_name, concepts, prompt, model, eval_set, batch_id)
    anchor_ids = {str(row[0]) for row in conn.execute(
        """SELECT ep.anchor_id FROM eval_sets es JOIN eval_set_passages ep
             ON ep.eval_set_id=es.id WHERE es.name=?""", (eval_set,)
    )}
    counts = {"completed": 0, "api_error": 0, "parse_error": 0, "unknown_custom_id": 0}
    raw_handle = raw_path.open("w", encoding="utf-8") if raw_path else None
    try:
        for value in results:
            raw = sdk_dict(value)
            if raw_handle:
                raw_handle.write(json.dumps(raw, sort_keys=True) + "\n")
            custom_id, outcome, payload, error = parse_result(raw)
            if custom_id not in anchor_ids:
                counts["unknown_custom_id"] += 1
                continue
            if outcome == "completed":
                try:
                    assert payload is not None
                    validate_payload(payload, concepts)
                except (AssertionError, ValueError) as exc:
                    outcome, error = "parse_error", str(exc)
            for concept in concepts:
                judgment = payload[concept.slug] if outcome == "completed" and payload else None
                conn.execute(
                    """INSERT INTO concept_predictions(
                           run_id,concept_id,anchor_id,custom_id,outcome,
                           relevance_label,relevance_confidence,definition_like,
                           definition_confidence,rationale,error_detail,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(run_id,concept_id,anchor_id) DO UPDATE SET
                           custom_id=excluded.custom_id,outcome=excluded.outcome,
                           relevance_label=excluded.relevance_label,
                           relevance_confidence=excluded.relevance_confidence,
                           definition_like=excluded.definition_like,
                           definition_confidence=excluded.definition_confidence,
                           rationale=excluded.rationale,error_detail=excluded.error_detail,
                           created_at=excluded.created_at""",
                    (run_id, concept.id, int(custom_id), custom_id, outcome,
                     judgment["relevance"] if judgment else None,
                     CONFIDENCE[judgment["confidence"]] if judgment else None,
                     judgment["definition_like"] if judgment else None,
                     (CONFIDENCE[judgment["confidence"]]
                      if judgment and judgment["definition_like"] != "not_applicable" else None),
                     judgment["rationale"] if judgment else None, error, utc_now()),
                )
            counts[outcome] += 1
        status = "complete" if counts["api_error"] == counts["parse_error"] == 0 else "failed"
        conn.execute("UPDATE model_runs SET status=?,completed_at=? WHERE id=?", (status, utc_now(), run_id))
        conn.execute(
            "UPDATE model_batches SET status=?,raw_results_path=? WHERE run_id=? AND batch_id=?",
            (status, str(raw_path.relative_to(ROOT)) if raw_path else None, run_id, batch_id),
        )
        conn.commit()
    finally:
        if raw_handle:
            raw_handle.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", action="store_true", help="write auditable request JSONL")
    action.add_argument("--submit", action="store_true", help="submit requests as a Message Batch")
    action.add_argument("--poll", action="store_true", help="print batch processing status")
    action.add_argument("--fetch", action="store_true", help="stream and import batch results")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--eval-set", default=EVAL_SET)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--concepts", help="comma-separated concept slugs (default: all active/pilot)"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    concept_slugs = args.concepts.split(",") if args.concepts else None
    if concept_slugs is not None and any(not slug for slug in concept_slugs):
        parser.error("--concepts must be a comma-separated list of non-empty slugs")
    run_dir = RUNS_DIR / args.run_name
    requests_path = run_dir / "requests.jsonl"
    try:
        if args.build:
            conn = connect(args.db)
            requests, _, _ = assemble_requests(
                conn, args.eval_set, args.model, concept_slugs
            )
            run_dir.mkdir(parents=True, exist_ok=True)
            with requests_path.open("w", encoding="utf-8") as handle:
                for request in requests:
                    handle.write(json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n")
            print(f"Wrote {len(requests)} requests to {requests_path}")
            return 0
        state = read_state(run_dir) if not args.submit else {}
        if args.submit:
            if not requests_path.is_file():
                raise ValueError(f"requests file not found: {requests_path}; run --build first")
            requests = [json.loads(line) for line in requests_path.read_text(encoding="utf-8").splitlines() if line]
            if args.dry_run:
                print(f"Would submit {len(requests)} requests from {requests_path}")
                return 0
            batch = require_client().messages.batches.create(requests=requests)
            batch_data = sdk_dict(batch)
            conn = connect(args.db)
            concepts = load_concepts(conn, concept_slugs)
            state = {"run_name": args.run_name, "batch_id": batch_data["id"],
                     "model": args.model,
                     "concept_slugs": [concept.slug for concept in concepts],
                     "eval_set": args.eval_set, "request_count": len(requests),
                     "submitted_at": utc_now()}
            write_json(run_dir / "state.json", state)
            ensure_run(conn, args.run_name, concepts, system_prompt(concepts),
                       args.model, args.eval_set, state["batch_id"])
            conn.commit()
            print(f"Submitted batch {state['batch_id']} with {len(requests)} requests")
            return 0
        if args.poll:
            client = require_client()
            batch_data = sdk_dict(client.messages.batches.retrieve(state["batch_id"]))
            state["processing_status"] = batch_data.get("processing_status")
            state["request_counts"] = batch_data.get("request_counts")
            state["polled_at"] = utc_now()
            write_json(run_dir / "state.json", state)
            conn = connect(args.db)
            conn.execute(
                """UPDATE model_batches SET status=? WHERE batch_id=? AND run_id=(
                       SELECT id FROM model_runs WHERE run_key=?)""",
                (batch_data.get("processing_status") or "unknown",
                 state["batch_id"], args.run_name),
            )
            conn.commit()
            print(json.dumps({"processing_status": batch_data.get("processing_status"),
                              "request_counts": batch_data.get("request_counts")}, indent=2))
            return 0 if batch_data.get("processing_status") == "ended" else 1
        if args.dry_run:
            print(f"Would fetch batch {state['batch_id']} into {args.db}")
            return 0
        client = require_client()
        run_dir.mkdir(parents=True, exist_ok=True)
        conn = connect(args.db)
        counts = import_results(conn, args.run_name, state["batch_id"],
                                client.messages.batches.results(state["batch_id"]),
                                run_dir / "results.jsonl",
                                state.get("model", args.model),
                                state.get("eval_set", args.eval_set),
                                state.get("concept_slugs"))
        print("Fetch results:", json.dumps(counts, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
