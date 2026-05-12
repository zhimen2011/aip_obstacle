"""处理管线（pipeline）：把 parsers / services / storage 串联起来。

公共 API：
    parse_file(path, airport_icao=None) -> ParseResult
    parse_text(text, airport_icao, source_file="<text>") -> ParseResult
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aip_obstacle.models import Obstacle, ParseFailure, ParseResult, ParseStats
from aip_obstacle.services.detector import detect_candidates
from aip_obstacle.services.field_parser import parse_candidate
from aip_obstacle.utils.hashing import sha256_of_file, sha256_of_text
from aip_obstacle.models import TextBlock

logger = logging.getLogger("aip_obstacle")


def parse_text(
    text: str,
    airport_icao: str = "UNKNOWN",
    source_file: str = "<text>",
) -> ParseResult:
    """从纯文本字符串解析障碍物，用于测试或 TXT 已读入内存的场景。"""
    file_hash = sha256_of_text(text)
    block = TextBlock(page=1, text=text, source_file=source_file, airport_icao=airport_icao)
    return _run_pipeline([block], source_file=source_file, file_hash=file_hash)


def parse_file(path: str | Path, airport_icao: Optional[str] = None) -> ParseResult:
    """从文件路径解析障碍物（自动判断 PDF / TXT）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{p}")

    suffix = p.suffix.lower()
    file_hash = sha256_of_file(p)

    if suffix == ".txt":
        from aip_obstacle.parsers.txt_parser import parse_txt
        blocks = parse_txt(p)
    elif suffix == ".pdf":
        from aip_obstacle.parsers.pdf_parser import parse_pdf, parse_pdf_tables
        from aip_obstacle.services.aip_parser import parse_aip_table_rows, parse_blocks_aip

        # 优先尝试表格提取（中国 AIP PDF 通常是 Excel 导出的表格）
        table_groups = parse_pdf_tables(p)
        if table_groups:
            obstacles, failures = parse_aip_table_rows(table_groups)
            if obstacles:
                # 如果调用方指定了 airport_icao，覆盖
                if airport_icao:
                    for obs in obstacles:
                        obs.airport_icao = airport_icao
                    for f in failures:
                        f.airport_icao = airport_icao

                stats = ParseStats(
                    total_candidates=len(obstacles) + len(failures),
                    total_success=len(obstacles),
                    total_failed=len(failures),
                    total_no_coord=sum(
                        1 for o in obstacles if o.latitude is None or o.longitude is None
                    ),
                )
                logger.info(
                    "%s | 表格解析 | 成功 %d | 失败 %d | 无经纬度 %d",
                    p.name,
                    stats.total_success,
                    stats.total_failed,
                    stats.total_no_coord,
                )
                return ParseResult(
                    source_file=str(p),
                    file_hash=file_hash,
                    obstacles=obstacles,
                    failures=failures,
                    stats=stats,
                )

        # 表格提取无结果或全失败 → 回退到文本行级解析
        logger.info("%s | 表格解析无结果，回退到行级解析", p.name)
        try:
            blocks = parse_pdf(p)
        except Exception as exc:
            logger.error("PDF 解析失败：%s — %s", p.name, exc)
            raise
        if all(not b.text.strip() for b in blocks):
            raise ValueError(
                f"PDF 无文本层，疑似扫描件，本期不支持 OCR：{p.name}"
            )
        if airport_icao:
            for b in blocks:
                b.airport_icao = airport_icao
        return _run_pipeline_aip(blocks, source_file=str(p), file_hash=file_hash)
    else:
        raise ValueError(f"不支持的文件类型：{suffix}（仅支持 .pdf / .txt）")

    # 如果调用方指定了 airport_icao，覆盖 parser 识别的值
    if airport_icao:
        for b in blocks:
            b.airport_icao = airport_icao

    return _run_pipeline(blocks, source_file=str(p), file_hash=file_hash)


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

    stats = ParseStats(
        total_candidates=len(candidates),
        total_success=len(obstacles),
        total_failed=len(failures),
        total_no_coord=sum(
            1 for o in obstacles if o.latitude is None or o.longitude is None
        ),
    )

    logger.info(
        "%s | 候选 %d 条 | 成功 %d | 失败 %d | 无经纬度 %d",
        source_file,
        stats.total_candidates,
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


def _run_pipeline_aip(blocks, source_file: str, file_hash: str) -> ParseResult:
    """PDF 路径：使用多行 AIP 解析器。"""
    from aip_obstacle.services.aip_parser import parse_blocks_aip

    obstacles, failures = parse_blocks_aip(blocks)

    stats = ParseStats(
        total_candidates=len(obstacles) + len(failures),
        total_success=len(obstacles),
        total_failed=len(failures),
        total_no_coord=sum(
            1 for o in obstacles if o.latitude is None or o.longitude is None
        ),
    )

    logger.info(
        "%s | 成功 %d | 失败 %d | 无经纬度 %d",
        source_file,
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
