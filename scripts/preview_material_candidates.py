from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL parse failed at line {line_number}: {exc}") from exc
    return records


def _source_bucket(record: dict[str, Any]) -> str:
    source = str(record.get("source") or "").lower()
    raw_source = record.get("raw_source") or {}
    if source == "local_documents" or "path" in raw_source:
        return "pdf"
    if str(raw_source.get("content_origin") or "").lower() == "pmc_fulltext":
        return "pmc"
    if source.startswith("pubmed:"):
        return "pubmed"
    return "other"


def _match_filters(
    record: dict[str, Any],
    *,
    source_filter: str | None,
    topic_filter: str | None,
    procedure_filter: str | None,
) -> bool:
    if source_filter and _source_bucket(record) != source_filter:
        return False
    if topic_filter and str(record.get("topic") or "") != topic_filter:
        return False
    if procedure_filter and str(record.get("procedure_name") or "") != procedure_filter:
        return False
    return True


def _shorten(text: str | None, limit: int) -> str:
    if not text:
        return "(empty)"
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _print_record(record: dict[str, Any], *, index: int, show_content: bool, content_chars: int) -> None:
    raw_source = record.get("raw_source") or {}
    authors = record.get("authors") or []
    tags = record.get("tags") or []
    preview = record.get("content_preview") or record.get("abstract") or record.get("content")

    print("=" * 88)
    print(f"[{index}] {record.get('title') or '(untitled)'}")
    print(
        " | ".join(
            [
                f"procedure={record.get('procedure_name') or '-'}",
                f"topic={record.get('topic') or '-'}",
                f"type={record.get('source_type') or '-'}",
                f"source={_source_bucket(record)}",
                f"year={record.get('year') or '-'}",
                f"confidence={record.get('candidate_confidence') or '-'}",
            ]
        )
    )
    print(f"origin: {record.get('source') or '-'}")
    if record.get("source_url"):
        print(f"url: {record.get('source_url')}")
    if authors:
        shown_authors = ", ".join(str(author) for author in authors[:8])
        if len(authors) > 8:
            shown_authors += f", ... (+{len(authors) - 8})"
        print(f"authors: {shown_authors}")
    if tags:
        print(f"tags: {', '.join(str(tag) for tag in tags)}")
    print(f"preview: {_shorten(str(preview) if preview is not None else None, 320)}")

    meta_parts = [
        f"external_id={record.get('external_id') or '-'}",
        f"content_chars={raw_source.get('content_chars') or len(str(record.get('content') or ''))}",
    ]
    if "chunk_count" in raw_source:
        meta_parts.append(f"chunk_count={raw_source.get('chunk_count')}")
    if raw_source.get("content_origin"):
        meta_parts.append(f"content_origin={raw_source.get('content_origin')}")
    if raw_source.get("query"):
        meta_parts.append(f"query={raw_source.get('query')}")
    print("meta: " + " | ".join(meta_parts))

    if show_content:
        content = record.get("content")
        print("content:")
        print(_shorten(str(content) if content is not None else None, content_chars))


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview material_candidates.jsonl in a readable format.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data") / "raw" / "material_candidates.jsonl",
        help="Input JSONL path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of matched records to print.",
    )
    parser.add_argument(
        "--source",
        choices=["pdf", "pubmed", "pmc", "other"],
        help="Filter by source bucket.",
    )
    parser.add_argument(
        "--topic",
        help="Filter by topic, for example operative_steps or complications.",
    )
    parser.add_argument(
        "--procedure",
        help="Filter by procedure name, for example hepatectomy.",
    )
    parser.add_argument(
        "--show-content",
        action="store_true",
        help="Print a shortened content field in addition to the preview.",
    )
    parser.add_argument(
        "--content-chars",
        type=int,
        default=1200,
        help="Maximum number of content characters to print when --show-content is used.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    records = _load_jsonl(args.input)
    matched = [
        record
        for record in records
        if _match_filters(
            record,
            source_filter=args.source,
            topic_filter=args.topic,
            procedure_filter=args.procedure,
        )
    ]

    print(f"Loaded {len(records)} records from {args.input}")
    print(f"Matched {len(matched)} records")

    for index, record in enumerate(matched[: args.limit], start=1):
        _print_record(
            record,
            index=index,
            show_content=args.show_content,
            content_chars=args.content_chars,
        )

    if not matched:
        print("No records matched the filters.")


if __name__ == "__main__":
    main()
