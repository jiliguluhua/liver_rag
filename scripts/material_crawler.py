from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import fitz
import requests

# Make repo-root imports work when this file is run as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import SessionLocal, init_db
from core.models import MaterialRecord


USER_AGENT = "liver-rag-material-crawler/0.4"
PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class SourceSpec:
    name: str
    enabled: bool
    strategy: str
    base_url: str
    note: str


@dataclass
class QueryProfile:
    procedure_name: str
    topic: str
    source_type: str
    query: str


@dataclass
class MaterialCandidate:
    title: str
    procedure_name: Optional[str]
    topic: str
    source_type: str
    modality: str
    abstract: Optional[str]
    content: Optional[str]
    source: str
    source_url: Optional[str]
    external_id: Optional[str]
    year: Optional[str]
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    content_preview: Optional[str] = None
    candidate_confidence: float = 0.0
    raw_source: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> str:
        seed = "|".join(
            [
                self.external_id or "",
                self.source or "",
                self.procedure_name or "",
                self.topic,
                self.source_type,
                self.title.strip().lower(),
            ]
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()


SOURCE_SPECS = [
    SourceSpec(
        name="pubmed",
        enabled=True,
        strategy="NCBI E-utilities search + summary + abstract fetch",
        base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        note="Suitable for guideline, review, and case metadata plus abstracts.",
    ),
    SourceSpec(
        name="pmc_fulltext",
        enabled=True,
        strategy="Map PubMed records to PMC and fetch open full text when available",
        base_url="https://pmc.ncbi.nlm.nih.gov/",
        note="Used to upgrade abstract-only candidates into fuller text materials.",
    ),
    SourceSpec(
        name="local_documents",
        enabled=True,
        strategy="Scan PDFs under data/documents and extract body text",
        base_url="local://data/documents",
        note="Useful for local guideline, consensus, and textbook-style seed materials.",
    ),
]


QUERY_PROFILES = [
    QueryProfile(
        procedure_name="cholecystectomy",
        topic="anatomy",
        source_type="review",
        query='(cholecystectomy OR "gallbladder surgery") AND anatomy',
    ),
    QueryProfile(
        procedure_name="cholecystectomy",
        topic="complications",
        source_type="case",
        query='cholecystectomy AND ("bile duct injury" OR complication OR bile leak)',
    ),
    QueryProfile(
        procedure_name="cholecystectomy",
        topic="complications",
        source_type="case",
        query='cholecystectomy AND ("case report" OR "case series")',
    ),
    QueryProfile(
        procedure_name="cholecystectomy",
        topic="risk_points",
        source_type="guideline",
        query='cholecystectomy AND guideline',
    ),
    QueryProfile(
        procedure_name="hepatectomy",
        topic="operative_steps",
        source_type="review",
        query='hepatectomy AND ("operative technique" OR "operative steps")',
    ),
    QueryProfile(
        procedure_name="hepatectomy",
        topic="complications",
        source_type="case",
        query='hepatectomy AND (complication OR bleeding OR bile leak)',
    ),
    QueryProfile(
        procedure_name="hepatectomy",
        topic="complications",
        source_type="case",
        query='hepatectomy AND ("case report" OR "case series")',
    ),
    QueryProfile(
        procedure_name="hepatectomy",
        topic="risk_points",
        source_type="guideline",
        query="hepatectomy AND guideline",
    ),
]


def _http_get(url: str, params: dict[str, Any]) -> requests.Response:
    response = requests.get(
        url,
        params=params,
        timeout=30,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().rstrip(".")


def _text_preview(text: Optional[str], limit: int = 280) -> Optional[str]:
    if not text:
        return None
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _chunk_text(text: str, *, max_chars: int, overlap: int) -> list[str]:
    paragraphs = [_normalize_text(block) for block in re.split(r"\n\s*\n+", text) if _normalize_text(block)]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(paragraph) <= max_chars:
            current = paragraph
            continue

        start = 0
        step = max(1, max_chars - overlap)
        while start < len(paragraph):
            piece = paragraph[start : start + max_chars].strip()
            if piece:
                chunks.append(piece)
            start += step
        current = ""

    if current:
        chunks.append(current)
    return chunks


def _format_chunked_content(chunks: list[str]) -> str:
    if not chunks:
        return ""
    total = len(chunks)
    return "\n\n".join(f"[Chunk {index}/{total}]\n{chunk}" for index, chunk in enumerate(chunks, start=1))


def _pubmed_search_ids(query: str, retmax: int) -> list[str]:
    response = _http_get(
        f"{PUBMED_EUTILS_BASE}/esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": retmax,
            "sort": "relevance",
        },
    )
    payload = response.json()
    return payload.get("esearchresult", {}).get("idlist", [])


def _pubmed_fetch_summary(pmids: list[str]) -> dict[str, Any]:
    if not pmids:
        return {}
    response = _http_get(
        f"{PUBMED_EUTILS_BASE}/esummary.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        },
    )
    return response.json()


def _pubmed_fetch_abstract_map(pmids: list[str]) -> dict[str, str]:
    if not pmids:
        return {}
    response = _http_get(
        f"{PUBMED_EUTILS_BASE}/efetch.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        },
    )
    root = ET.fromstring(response.text)
    abstract_map: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID")
        if not pmid:
            continue
        sections: list[str] = []
        for abstract_text in article.findall(".//Abstract/AbstractText"):
            label = (abstract_text.attrib.get("Label") or "").strip()
            text = _normalize_text("".join(abstract_text.itertext()).strip())
            if not text:
                continue
            sections.append(f"{label}: {text}" if label else text)
        if sections:
            abstract_map[pmid.strip()] = "\n".join(sections)
    return abstract_map


def _pubmed_fetch_pmc_map(pmids: list[str]) -> dict[str, str]:
    if not pmids:
        return {}
    response = _http_get(
        f"{PUBMED_EUTILS_BASE}/elink.fcgi",
        {
            "dbfrom": "pubmed",
            "db": "pmc",
            "linkname": "pubmed_pmc",
            "id": ",".join(pmids),
            "retmode": "xml",
        },
    )
    root = ET.fromstring(response.text)
    pmc_map: dict[str, str] = {}
    for linkset in root.findall(".//LinkSet"):
        pmid = linkset.findtext("IdList/Id")
        pmcid = linkset.findtext(".//LinkSetDb/Link/Id")
        if pmid and pmcid:
            pmc_map[pmid.strip()] = pmcid.strip()
    return pmc_map


def _pubmed_fetch_pmc_fulltext(pmcid: str, max_chars: int) -> Optional[str]:
    response = _http_get(
        f"{PUBMED_EUTILS_BASE}/efetch.fcgi",
        {
            "db": "pmc",
            "id": pmcid,
            "retmode": "xml",
        },
    )
    root = ET.fromstring(response.text)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//body//p"):
        text = "".join(paragraph.itertext()).strip()
        if text:
            paragraphs.append(_normalize_text(text))
    if not paragraphs:
        return None
    return "\n".join(paragraphs)[:max_chars]


def _infer_pubmed_labels(
    profile: QueryProfile,
    *,
    title: str,
    abstract_text: Optional[str],
    pub_types: list[Any],
) -> tuple[str, str]:
    haystack = f"{title}\n{abstract_text or ''}".lower()
    lowered_types = " ".join(str(t).lower() for t in pub_types)

    source_type = profile.source_type
    if "case reports" in lowered_types or "case report" in haystack or "case series" in haystack:
        source_type = "case"
    elif "practice guideline" in lowered_types or "guideline" in lowered_types or "consensus" in haystack:
        source_type = "guideline"
    elif "review" in lowered_types or "review" in haystack:
        source_type = "review"

    topic = profile.topic
    if any(keyword in haystack for keyword in ["complication", "bleeding", "bile leak", "cholangitis", "injury"]):
        topic = "complications"
    elif any(keyword in haystack for keyword in ["anatomy", "anatomic", "landmark"]):
        topic = "anatomy"
    elif any(keyword in haystack for keyword in ["operative", "surgical technique", "procedure step", "resection technique"]):
        topic = "operative_steps"
    elif any(keyword in haystack for keyword in ["guideline", "consensus", "recommendation", "risk", "safety"]):
        topic = "risk_points"

    return topic, source_type


def crawl_pubmed(
    profile: QueryProfile,
    retmax: int,
    *,
    fetch_pmc_fulltext: bool,
    pmc_max_chars: int,
) -> list[MaterialCandidate]:
    pmids = _pubmed_search_ids(profile.query, retmax=retmax)
    if not pmids:
        return []

    summary_payload = _pubmed_fetch_summary(pmids)
    abstract_map = _pubmed_fetch_abstract_map(pmids)
    pmc_map = _pubmed_fetch_pmc_map(pmids) if fetch_pmc_fulltext else {}
    candidates: list[MaterialCandidate] = []

    for pmid in pmids:
        item = summary_payload.get("result", {}).get(pmid)
        if not isinstance(item, dict):
            continue

        title = _clean_title(str(item.get("title", "")))
        authors = [author.get("name", "") for author in item.get("authors", []) if isinstance(author, dict)]
        year = str(item.get("pubdate", "")).split(" ")[0] or None
        pub_types = item.get("pubtype", []) or []
        abstract_text = abstract_map.get(pmid)
        topic, source_type = _infer_pubmed_labels(
            profile,
            title=title,
            abstract_text=abstract_text,
            pub_types=pub_types,
        )

        pmcid = pmc_map.get(pmid)
        full_text = None
        if pmcid and fetch_pmc_fulltext:
            try:
                full_text = _pubmed_fetch_pmc_fulltext(pmcid, pmc_max_chars)
            except Exception:
                full_text = None

        external_id = f"PMC{pmcid}" if pmcid else pmid
        source_url = (
            f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/"
            if pmcid
            else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        )
        content = full_text or abstract_text
        confidence = 0.88 if full_text else (0.75 if abstract_text else 0.55)

        candidates.append(
            MaterialCandidate(
                title=title,
                procedure_name=profile.procedure_name,
                topic=topic,
                source_type=source_type,
                modality="text",
                abstract=abstract_text,
                content=content,
                source=f"PubMed:{item.get('fulljournalname') or item.get('source') or 'unknown'}",
                source_url=source_url,
                external_id=external_id,
                year=year,
                authors=[author for author in authors if author],
                tags=[tag for tag in [profile.procedure_name, topic, source_type] if tag],
                content_preview=_text_preview(content),
                candidate_confidence=confidence,
                raw_source={
                    "pubtype": pub_types,
                    "query": profile.query,
                    "journal": item.get("fulljournalname"),
                    "pmid": pmid,
                    "pmcid": f"PMC{pmcid}" if pmcid else None,
                    "has_fulltext": bool(full_text),
                    "content_chars": len(content or ""),
                    "content_origin": "pmc_fulltext" if full_text else ("pubmed_abstract" if abstract_text else "metadata_only"),
                },
            )
        )
        time.sleep(0.1)
    return candidates


def _extract_pdf_text(file_path: Path, max_chars: int) -> str:
    doc = fitz.open(file_path)
    try:
        text_parts: list[str] = []
        total_chars = 0
        for page in doc:
            page_text = page.get_text("text")
            text_parts.append(page_text)
            total_chars += len(page_text)
            if total_chars >= max_chars:
                break
        text = "\n".join(text_parts).strip()
        return text[:max_chars]
    finally:
        doc.close()


def _infer_local_pdf_metadata(file_path: Path) -> tuple[Optional[str], str, str]:
    lower_name = file_path.stem.lower()
    stem = file_path.stem
    procedure_name = None
    if "胆囊" in stem or "chole" in lower_name:
        procedure_name = "cholecystectomy"
    elif "肝" in stem or "hepate" in lower_name:
        procedure_name = "hepatectomy"

    topic = "disease_background"
    source_type = "reference"

    if "指南" in stem or "共识" in stem or "guideline" in lower_name or "consensus" in lower_name:
        source_type = "guideline"
        topic = "risk_points"
    elif "病例" in stem or "case" in lower_name:
        source_type = "case"
        topic = "complications"
    elif "解剖" in stem or "anatomy" in lower_name:
        source_type = "reference"
        topic = "anatomy"
    elif "术式" in stem or "步骤" in stem or "operative" in lower_name:
        source_type = "reference"
        topic = "operative_steps"

    return procedure_name, topic, source_type


def crawl_local_documents(
    documents_dir: Path,
    *,
    max_chars: int,
    chunk_chars: int,
    chunk_overlap: int,
) -> list[MaterialCandidate]:
    candidates: list[MaterialCandidate] = []
    if not documents_dir.exists():
        return candidates

    for file_path in sorted(documents_dir.glob("*.pdf")):
        procedure_name, topic, source_type = _infer_local_pdf_metadata(file_path)
        text_content = _extract_pdf_text(file_path, max_chars=max_chars)
        chunks = _chunk_text(text_content, max_chars=chunk_chars, overlap=chunk_overlap)
        formatted_content = _format_chunked_content(chunks)
        snippet = _text_preview(chunks[0] if chunks else text_content, limit=320)
        candidates.append(
            MaterialCandidate(
                title=file_path.stem,
                procedure_name=procedure_name,
                topic=topic,
                source_type=source_type,
                modality="text",
                abstract=snippet,
                content=formatted_content or text_content or None,
                source="local_documents",
                source_url=str(file_path.resolve()),
                external_id=file_path.name,
                year=None,
                tags=[tag for tag in [procedure_name, topic, source_type] if tag],
                content_preview=snippet,
                candidate_confidence=0.65,
                raw_source={
                    "path": str(file_path.resolve()),
                    "content_chars": len(text_content),
                    "chunk_count": len(chunks),
                    "chunk_chars": chunk_chars,
                    "chunk_overlap": chunk_overlap,
                },
            )
        )
    return candidates


def dedupe_candidates(candidates: list[MaterialCandidate]) -> list[MaterialCandidate]:
    kept: dict[str, MaterialCandidate] = {}
    for candidate in candidates:
        key = candidate.dedupe_key()
        previous = kept.get(key)
        if previous is None or candidate.candidate_confidence > previous.candidate_confidence:
            kept[key] = candidate
    return list(kept.values())


def candidate_to_material_payload(candidate: MaterialCandidate) -> dict[str, Any]:
    content = candidate.content or candidate.abstract
    return {
        "external_id": candidate.external_id,
        "procedure_name": candidate.procedure_name,
        "topic": candidate.topic,
        "source_type": candidate.source_type,
        "modality": candidate.modality,
        "title": candidate.title,
        "content": content,
        "source": candidate.source_url or candidate.source,
        "tags_json": json.dumps(candidate.tags, ensure_ascii=False),
    }


def write_jsonl(candidates: list[MaterialCandidate], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for candidate in candidates:
            f.write(json.dumps(asdict(candidate), ensure_ascii=False) + "\n")


def import_candidates_to_db(candidates: list[MaterialCandidate]) -> tuple[int, int]:
    init_db()
    db = SessionLocal()
    inserted = 0
    skipped = 0
    try:
        for candidate in candidates:
            payload = candidate_to_material_payload(candidate)
            existing = None
            if payload["external_id"]:
                existing = db.query(MaterialRecord).filter(MaterialRecord.external_id == payload["external_id"]).first()
            if existing is None:
                existing = (
                    db.query(MaterialRecord)
                    .filter(MaterialRecord.title == payload["title"])
                    .filter(MaterialRecord.procedure_name == payload["procedure_name"])
                    .filter(MaterialRecord.topic == payload["topic"])
                    .first()
                )
            if existing is not None:
                skipped += 1
                continue
            db.add(MaterialRecord(**payload))
            inserted += 1
        db.commit()
        return inserted, skipped
    finally:
        db.close()


def print_source_review() -> None:
    print("=== Source Review ===")
    for source in SOURCE_SPECS:
        print(f"- name: {source.name}")
        print(f"  enabled: {source.enabled}")
        print(f"  strategy: {source.strategy}")
        print(f"  base_url: {source.base_url}")
        print(f"  note: {source.note}")

    print("\n=== Output Schema ===")
    print(
        json.dumps(
            asdict(
                MaterialCandidate(
                    title="example title",
                    procedure_name="cholecystectomy",
                    topic="complications",
                    source_type="case",
                    modality="text",
                    abstract="example abstract",
                    content="[Chunk 1/2]\nexample full text chunk one\n\n[Chunk 2/2]\nexample full text chunk two",
                    source="PubMed:Example Journal",
                    source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/",
                    external_id="PMC1234567",
                    year="2025",
                    authors=["Author A", "Author B"],
                    tags=["cholecystectomy", "complications", "case"],
                    content_preview="example full text chunk one...",
                    candidate_confidence=0.88,
                    raw_source={
                        "pmid": "12345678",
                        "pmcid": "PMC1234567",
                        "has_fulltext": True,
                        "content_chars": 2048,
                        "chunk_count": 2,
                    },
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed crawler for hepatobiliary text materials.")
    parser.add_argument("--review-only", action="store_true", help="Only print data sources and output schema.")
    parser.add_argument("--retmax", type=int, default=10, help="PubMed candidate limit per query.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "raw" / "material_candidates.jsonl",
        help="Output JSONL file for crawled candidates.",
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=Path("data") / "documents",
        help="Local PDF document directory.",
    )
    parser.add_argument(
        "--pdf-max-chars",
        type=int,
        default=6000,
        help="Maximum extracted body text length per local PDF before chunking.",
    )
    parser.add_argument(
        "--pdf-chunk-chars",
        type=int,
        default=1200,
        help="Target size for each rendered PDF content chunk.",
    )
    parser.add_argument(
        "--pdf-chunk-overlap",
        type=int,
        default=150,
        help="Overlap size between long PDF chunks.",
    )
    parser.add_argument(
        "--fetch-pmc-fulltext",
        action="store_true",
        help="Fetch PMC full text when a PubMed record has a linked PMC article.",
    )
    parser.add_argument(
        "--pmc-max-chars",
        type=int,
        default=20000,
        help="Maximum body text length to keep from PMC full text.",
    )
    parser.add_argument(
        "--import-db",
        action="store_true",
        help="Import deduped candidates directly into the materials table.",
    )
    args = parser.parse_args()

    print_source_review()
    if args.review_only:
        return

    all_candidates: list[MaterialCandidate] = []
    all_candidates.extend(
        crawl_local_documents(
            args.documents_dir,
            max_chars=args.pdf_max_chars,
            chunk_chars=args.pdf_chunk_chars,
            chunk_overlap=args.pdf_chunk_overlap,
        )
    )

    for profile in QUERY_PROFILES:
        try:
            all_candidates.extend(
                crawl_pubmed(
                    profile,
                    retmax=args.retmax,
                    fetch_pmc_fulltext=args.fetch_pmc_fulltext,
                    pmc_max_chars=args.pmc_max_chars,
                )
            )
        except Exception as exc:
            print(f"[warn] pubmed crawl failed for {profile.query}: {exc}")

    deduped = dedupe_candidates(all_candidates)
    write_jsonl(deduped, args.output)
    print(f"\nWrote {len(deduped)} candidates to {args.output}")

    if args.import_db:
        inserted, skipped = import_candidates_to_db(deduped)
        print(f"Imported into materials table: inserted={inserted}, skipped={skipped}")


if __name__ == "__main__":
    main()
