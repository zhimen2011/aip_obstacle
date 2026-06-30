"""Processing pipeline: connect parsers, services, and result objects."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aip_obstacle.models import Obstacle, ParseResult, ParseStats, TextBlock
from aip_obstacle.services.detector import detect_candidates
from aip_obstacle.services.field_parser import parse_candidate
from aip_obstacle.utils.hashing import sha256_of_file, sha256_of_text

logger = logging.getLogger("aip_obstacle")


def parse_text(
    text: str,
    airport_icao: str = "UNKNOWN",
    source_file: str = "<text>",
) -> ParseResult:
    """Parse obstacle records from plain text."""
    file_hash = sha256_of_text(text)
    block = TextBlock(page=1, text=text, source_file=source_file, airport_icao=airport_icao)
    return _run_pipeline([block], source_file=source_file, file_hash=file_hash)


def parse_file(path: str | Path, airport_icao: Optional[str] = None) -> ParseResult:
    """Parse obstacle records from a PDF or TXT file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{p}")

    suffix = p.suffix.lower()
    file_hash = sha256_of_file(p)

    if suffix == ".txt":
        from aip_obstacle.parsers.txt_parser import parse_txt

        blocks = parse_txt(p)
        if airport_icao:
            for b in blocks:
                b.airport_icao = airport_icao
        return _run_pipeline(blocks, source_file=str(p), file_hash=file_hash)

    if suffix == ".pdf":
        return _parse_pdf_file(p, file_hash=file_hash, airport_icao=airport_icao)

    raise ValueError(f"不支持的文件类型：{suffix}（仅支持 .pdf / .txt）")


def _parse_pdf_file(
    path: Path,
    file_hash: str,
    airport_icao: Optional[str] = None,
) -> ParseResult:
    from aip_obstacle.parsers.pdf_parser import parse_pdf, parse_pdf_tables
    from aip_obstacle.services.aip_parser import parse_aip_table_rows, parse_blocks_aip
    from aip_obstacle.services.quality import merge_table_and_text_results

    table_groups = parse_pdf_tables(path)
    if table_groups:
        table_obstacles, table_failures = parse_aip_table_rows(table_groups)
        if table_obstacles or table_failures:
            text_obstacles: list[Obstacle] = []
            try:
                blocks = parse_pdf(path)
                if not all(not b.text.strip() for b in blocks):
                    if airport_icao:
                        for b in blocks:
                            b.airport_icao = airport_icao
                    text_obstacles, _ = parse_blocks_aip(blocks)
            except Exception as exc:
                logger.warning("%s | PDF text fallback failed: %s", path.name, exc)

            obstacles, failures = merge_table_and_text_results(
                table_obstacles,
                table_failures,
                text_obstacles,
            )
            if airport_icao:
                for obs in obstacles:
                    obs.airport_icao = airport_icao
                for failure in failures:
                    failure.airport_icao = airport_icao

            return _build_parse_result(
                source_file=str(path),
                file_hash=file_hash,
                obstacles=obstacles,
                failures=failures,
                log_name=path.name,
                log_mode="table+text",
            )

    logger.info("%s | table parse empty, falling back to text parser", path.name)
    blocks = parse_pdf(path)
    if all(not b.text.strip() for b in blocks):
        raise ValueError(f"PDF 无文本层，疑似扫描件，本期不支持 OCR：{path.name}")
    if airport_icao:
        for b in blocks:
            b.airport_icao = airport_icao
    return _run_pipeline_aip(blocks, source_file=str(path), file_hash=file_hash)


def _run_pipeline(blocks, source_file: str, file_hash: str) -> ParseResult:
    candidates = detect_candidates(blocks)
    obstacles = []
    failures = []

    for cand in candidates:
        result = parse_candidate(cand)
        if isinstance(result, Obstacle):
            obstacles.append(result)
        else:
            failures.append(result)

    return _build_parse_result(
        source_file=source_file,
        file_hash=file_hash,
        obstacles=obstacles,
        failures=failures,
        log_name=source_file,
        log_mode="text",
    )


def _run_pipeline_aip(blocks, source_file: str, file_hash: str) -> ParseResult:
    """PDF text fallback path using the multi-line AIP parser."""
    from aip_obstacle.services.aip_parser import parse_blocks_aip
    from aip_obstacle.services.quality import apply_quality_scores

    obstacles, failures = parse_blocks_aip(blocks)
    obstacles = apply_quality_scores(obstacles)

    return _build_parse_result(
        source_file=source_file,
        file_hash=file_hash,
        obstacles=obstacles,
        failures=failures,
        log_name=source_file,
        log_mode="aip-text",
    )


def _build_parse_result(
    source_file: str,
    file_hash: str,
    obstacles: list[Obstacle],
    failures,
    log_name: str,
    log_mode: str,
) -> ParseResult:
    from aip_obstacle.services.quality import append_missing_id_failures

    failures = append_missing_id_failures(obstacles, list(failures))

    stats = ParseStats(
        total_candidates=len(obstacles) + len(failures),
        total_success=len(obstacles),
        total_failed=len(failures),
        total_no_coord=sum(
            1 for o in obstacles if o.latitude is None or o.longitude is None
        ),
    )

    logger.info(
        "%s | %s | success %d | failed %d | no coord %d",
        log_name,
        log_mode,
        stats.total_success,
        stats.total_failed,
        stats.total_no_coord,
    )

    return ParseResult(
        source_file=source_file,
        file_hash=file_hash,
        obstacles=obstacles,
        failures=failures,
        stats=stats,
    )
