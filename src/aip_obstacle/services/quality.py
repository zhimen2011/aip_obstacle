"""Quality checks and fallback merge for AIP obstacle parsing.

This module keeps parser output structural and applies business-level checks
after both table and text parsers have had a chance to read the PDF.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from aip_obstacle.models import Obstacle, ParseFailure

INNER_RADIUS_M = 15000.0
MIN_REASONABLE_DISTANCE_M = 100.0
CONFIDENCE_OK = 1.0
CONFIDENCE_HIGH_RISK = 0.4
MIN_SEQUENTIAL_ID_COUNT = 10

_ID_RE = re.compile(r"\b([A-Za-z]*\d{1,4}[A-Za-z0-9_-]*)\b")
_THREE_DIGIT_ID_RE = re.compile(r"\b(\d{3})\b")


def merge_table_and_text_results(
    table_obstacles: list[Obstacle],
    table_failures: list[ParseFailure],
    text_obstacles: list[Obstacle],
) -> tuple[list[Obstacle], list[ParseFailure]]:
    """Merge table-parser output with text-parser fallback output.

    Table rows remain authoritative unless they are missing core fields or have
    obviously bad values. Text rows are used by matching obstacle_id only.
    """
    text_index = _index_obstacles(text_obstacles)

    merged: list[Obstacle] = []
    for obs in table_obstacles:
        text_obs = text_index.get(_normal_id(obs.obstacle_id))
        repaired = replace(obs)
        if text_obs is not None and _needs_text_repair(repaired):
            repaired = _repair_core_fields(repaired, text_obs)
        merged.append(repaired)

    unresolved_failures: list[ParseFailure] = []
    for failure in table_failures:
        obstacle_id = _failure_obstacle_id(failure)
        text_obs = text_index.get(obstacle_id)
        if text_obs is None:
            unresolved_failures.append(failure)
            continue

        repaired = replace(text_obs)
        table_name = _failure_name(failure.raw_text, obstacle_id)
        if table_name:
            repaired.name = table_name
        repaired.airport_icao = failure.airport_icao or repaired.airport_icao
        repaired.source_page = failure.source_page or repaired.source_page
        repaired.raw_text = _join_raw_text(failure.raw_text, text_obs.raw_text)
        merged.append(repaired)

    merged = sorted(merged, key=_obstacle_sort_key)
    merged = _repair_order_anomalies(merged, text_index)
    merged = apply_quality_scores(merged)
    return merged, unresolved_failures


def apply_quality_scores(obstacles: list[Obstacle]) -> list[Obstacle]:
    """Return obstacles with confidence_score based on quality checks.

    Latitude/longitude are intentionally ignored: missing coordinates should
    not lower confidence or trigger UI risk colors.
    """
    order_anomalies = _bearing_order_anomaly_ids(obstacles)
    scored: list[Obstacle] = []
    for obs in obstacles:
        confidence = CONFIDENCE_HIGH_RISK if _is_high_risk(obs, order_anomalies) else CONFIDENCE_OK
        scored.append(replace(obs, confidence_score=confidence))
    return scored


def append_missing_id_failures(
    obstacles: list[Obstacle],
    failures: list[ParseFailure],
) -> list[ParseFailure]:
    """Add review placeholders for likely missing numeric obstacle IDs.

    This catches records that never became parser candidates. It is deliberately
    conservative: only pure numeric IDs are checked, and only when one airport
    already has enough numeric records to look like a sequential AIP table.
    """
    existing_failure_ids = {
        (_normal_airport_id(f.airport_icao), _normal_id(failure_id))
        for f in failures
        for failure_id in [_failure_obstacle_id(f)]
        if failure_id
    }

    additions: list[ParseFailure] = []
    for airport_icao, ids in _numeric_ids_by_airport(obstacles).items():
        unique_ids = sorted(set(ids))
        if len(unique_ids) < MIN_SEQUENTIAL_ID_COUNT:
            continue

        present_numbers = {number for _, number in unique_ids}
        width = max(len(text) for text, _ in ids)
        for number in range(unique_ids[0][1], unique_ids[-1][1] + 1):
            if number in present_numbers:
                continue

            obstacle_id = str(number).zfill(width)
            key = (_normal_airport_id(airport_icao), _normal_id(obstacle_id))
            if key in existing_failure_ids:
                continue

            additions.append(ParseFailure(
                airport_icao=airport_icao,
                source_page=0,
                raw_text=f"疑似缺失编号 {obstacle_id}",
                reason=f"编号序列断号，疑似 PDF 抽取漏识别：{obstacle_id}",
            ))
            existing_failure_ids.add(key)

    return failures + additions


def _normal_airport_id(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return text.upper() or "UNKNOWN"


def _numeric_ids_by_airport(
    obstacles: Iterable[Obstacle],
) -> dict[str, list[tuple[str, int]]]:
    grouped: dict[str, list[tuple[str, int]]] = {}
    for obs in obstacles:
        text = "" if obs.obstacle_id is None else str(obs.obstacle_id).strip()
        if not text or not text.isdigit():
            continue

        airport_icao = _normal_airport_id(obs.airport_icao)
        grouped.setdefault(airport_icao, []).append((text, int(text)))
    return grouped


def _index_obstacles(obstacles: Iterable[Obstacle]) -> dict[str, Obstacle]:
    index: dict[str, Obstacle] = {}
    for obs in obstacles:
        key = _normal_id(obs.obstacle_id)
        if key and key not in index:
            index[key] = obs
    return index


def _normal_id(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    match = _ID_RE.search(text)
    return match.group(1).upper() if match else text.upper()


def _failure_obstacle_id(failure: ParseFailure) -> str:
    match = _THREE_DIGIT_ID_RE.search(failure.reason or "")
    if match:
        return match.group(1)
    match = _THREE_DIGIT_ID_RE.search(failure.raw_text or "")
    if match:
        return match.group(1)
    return _normal_id(failure.raw_text)


def _failure_name(raw_text: str, obstacle_id: str) -> str:
    first_cell = (raw_text or "").split("|", 1)[0]
    for part in first_cell.splitlines():
        clean = part.strip()
        if not clean:
            continue
        if _normal_id(clean) == obstacle_id:
            continue
        if clean.isdigit():
            continue
        return clean
    return ""


def _join_raw_text(table_raw: str, text_raw: str) -> str:
    if table_raw and text_raw and table_raw != text_raw:
        return f"{table_raw} || text fallback: {text_raw}"
    return table_raw or text_raw


def _needs_text_repair(obs: Obstacle) -> bool:
    if _bearing(obs) is None:
        return True
    if obs.distance_m is None:
        return True
    if obs.elevation_m is None:
        return True
    if obs.distance_m < MIN_REASONABLE_DISTANCE_M:
        return True
    brg = _bearing(obs)
    return brg is not None and not 0 <= brg <= 360


def _repair_core_fields(base: Obstacle, fallback: Obstacle) -> Obstacle:
    repaired = replace(base)
    if fallback.mag_bearing_deg is not None:
        repaired.mag_bearing_deg = fallback.mag_bearing_deg
    if fallback.bearing_deg is not None:
        repaired.bearing_deg = fallback.bearing_deg
    if fallback.distance_m is not None:
        repaired.distance_m = fallback.distance_m
    if fallback.elevation_m is not None:
        repaired.elevation_m = fallback.elevation_m
        repaired.unit_height_original = fallback.unit_height_original or "m"
    if fallback.height_m is not None:
        repaired.height_m = fallback.height_m
    if fallback.latitude is not None:
        repaired.latitude = fallback.latitude
    if fallback.longitude is not None:
        repaired.longitude = fallback.longitude
    if fallback.raw_text and fallback.raw_text != repaired.raw_text:
        repaired.raw_text = _join_raw_text(repaired.raw_text, fallback.raw_text)
    return repaired


def _repair_order_anomalies(
    obstacles: list[Obstacle],
    text_index: dict[str, Obstacle],
) -> list[Obstacle]:
    anomaly_ids = _bearing_order_anomaly_ids(obstacles)
    if not anomaly_ids:
        return obstacles

    repaired: list[Obstacle] = []
    for obs in obstacles:
        key = _normal_id(obs.obstacle_id)
        fallback = text_index.get(key)
        if key in anomaly_ids and fallback is not None:
            repaired.append(_repair_core_fields(obs, fallback))
        else:
            repaired.append(obs)
    return repaired


def _is_high_risk(obs: Obstacle, order_anomalies: set[str]) -> bool:
    brg = _bearing(obs)
    if brg is None or not 0 <= brg <= 360:
        return True
    if obs.distance_m is None or obs.distance_m < MIN_REASONABLE_DISTANCE_M:
        return True
    if obs.elevation_m is None:
        return True
    return _normal_id(obs.obstacle_id) in order_anomalies


def _bearing(obs: Obstacle) -> float | None:
    return obs.mag_bearing_deg if obs.mag_bearing_deg is not None else obs.bearing_deg


def _distance_bucket(obs: Obstacle) -> str | None:
    if obs.distance_m is None:
        return None
    return "inner" if obs.distance_m <= INNER_RADIUS_M else "outer"


def _bearing_order_anomaly_ids(obstacles: list[Obstacle]) -> set[str]:
    anomalies: set[str] = set()
    for bucket in ("inner", "outer"):
        group = [
            obs
            for obs in obstacles
            if _distance_bucket(obs) == bucket
            and _bearing(obs) is not None
            and obs.distance_m is not None
            and obs.distance_m >= MIN_REASONABLE_DISTANCE_M
        ]
        if len(group) < 3:
            continue
        for idx in range(1, len(group) - 1):
            prev_brg = _bearing(group[idx - 1])
            cur_brg = _bearing(group[idx])
            next_brg = _bearing(group[idx + 1])
            if prev_brg is None or cur_brg is None or next_brg is None:
                continue
            if prev_brg <= next_brg and not prev_brg <= cur_brg <= next_brg:
                anomalies.add(_normal_id(group[idx].obstacle_id))
    return anomalies


def _obstacle_sort_key(obs: Obstacle) -> tuple[int, int, str]:
    text = str(obs.obstacle_id or "")
    match = re.search(r"\d+", text)
    number = int(match.group(0)) if match else 10**9
    return (obs.source_page or 0, number, text)
