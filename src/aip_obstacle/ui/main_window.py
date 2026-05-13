"""AIP 障碍物数据识别工具 — GUI 主窗口（PySide6）。"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from aip_obstacle.models import Obstacle, ParseResult
from aip_obstacle.pipeline import parse_file
from aip_obstacle.storage.sqlite_store import SQLiteStore
from aip_obstacle.exporters.excel_exporter import export_xlsx


# ---------------------------------------------------------------------------
# 后台解析线程（避免阻塞界面）
# ---------------------------------------------------------------------------

class _ParseWorker(QThread):
    finished = Signal(object)          # ParseResult
    error = Signal(str)                # 错误信息

    def __init__(self, file_path: str, airport_icao: str | None, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._airport_icao = airport_icao or None

    def run(self):
        try:
            result = parse_file(self._file_path, airport_icao=self._airport_icao)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# 障碍物数据表格模型
# ---------------------------------------------------------------------------

_COLUMNS = [
    ("状态", "_review_status", False),
    ("ICAO", "airport_icao", True),
    ("编号", "obstacle_id", True),
    ("名称", "name", True),
    ("方位(°)", "bearing_deg", True),
    ("磁方位(°)", "mag_bearing_deg", True),
    ("距离(m)", "distance_m", True),
    ("纬度", "latitude", True),
    ("经度", "longitude", True),
    ("海拔(m)", "elevation_m", True),
    ("高度(m)", "height_m", True),
    ("可信度", "confidence_score", False),
    ("是否人工修改", "is_user_modified", False),
    ("页码", "source_page", True),
]

_FLOAT_FIELDS = {
    "bearing_deg",
    "mag_bearing_deg",
    "distance_m",
    "latitude",
    "longitude",
    "elevation_m",
    "height_m",
}

_INT_FIELDS = {"source_page"}

_COLOR_HIGH_RISK = "#FFD6D6"
_COLOR_RISK = "#FFF3BF"
_COLOR_USER_MODIFIED = "#D7ECFF"

_HIGH_RISK_CONFIDENCE_THRESHOLD = 0.5
_RISK_CONFIDENCE_THRESHOLD = 0.9

_STATUS_PARSED = "自动解析"
_STATUS_NEEDS_INPUT = "待补录"
_STATUS_MANUAL = "人工新增"

_OBSTACLE_ID_IN_REASON_RE = re.compile(r"编号\s*([A-Za-z0-9_-]+)")
_FIRST_ID_RE = re.compile(r"\b([A-Za-z]*\d{1,4}[A-Za-z0-9_-]*)\b")
_NUMBER_RE = re.compile(r"\d+")


def _is_user_modified(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "是"}
    return bool(value)


def _obstacle_row_color(row: dict) -> str | None:
    """返回障碍物行的背景色；人工修改优先于自动风险判断。"""
    if _is_user_modified(row.get("is_user_modified")):
        return _COLOR_USER_MODIFIED

    try:
        confidence = float(row.get("confidence_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < _HIGH_RISK_CONFIDENCE_THRESHOLD:
        return _COLOR_HIGH_RISK
    if confidence < _RISK_CONFIDENCE_THRESHOLD:
        return _COLOR_RISK
    return None


def _obstacle_id_number(value: Any) -> int | None:
    text = "" if value is None else str(value)
    match = _NUMBER_RE.search(text)
    return int(match.group(0)) if match else None


def _extract_failure_obstacle_id(reason: str, raw_text: str) -> str:
    match = _OBSTACLE_ID_IN_REASON_RE.search(reason or "")
    if match:
        return match.group(1)
    match = _FIRST_ID_RE.search(raw_text or "")
    return match.group(1) if match else ""


def _review_row_sort_key(row: dict) -> tuple[int, int, int]:
    page = row.get("source_page")
    try:
        page_num = int(page)
    except (TypeError, ValueError):
        page_num = 0
    obstacle_num = _obstacle_id_number(row.get("obstacle_id"))
    return (
        page_num,
        obstacle_num if obstacle_num is not None else 10**9,
        int(row.get("_source_order", 0) or 0),
    )


def _obstacle_to_review_row(obs: Obstacle, source_order: int) -> dict:
    row = obs.__dict__.copy()
    row["id"] = None
    row["_review_status"] = _STATUS_PARSED
    row["_source_order"] = source_order
    return row


def _failure_to_review_row(failure, source_order: int) -> dict:
    obstacle_id = _extract_failure_obstacle_id(failure.reason, failure.raw_text)
    return {
        "id": None,
        "airport_icao": failure.airport_icao,
        "obstacle_id": obstacle_id,
        "name": "",
        "bearing_deg": None,
        "mag_bearing_deg": None,
        "distance_m": None,
        "latitude": None,
        "longitude": None,
        "elevation_m": None,
        "height_m": None,
        "unit_distance_original": None,
        "unit_height_original": None,
        "confidence_score": 0.0,
        "is_user_modified": 0,
        "edited_at": None,
        "source_page": failure.source_page,
        "raw_text": failure.raw_text,
        "_review_status": _STATUS_NEEDS_INPUT,
        "_source_order": source_order,
        "_failure_reason": failure.reason,
    }


def _blank_review_row(
    airport_icao: str = "UNKNOWN",
    source_page: int = 1,
    source_order: int = 0,
) -> dict:
    return {
        "id": None,
        "airport_icao": airport_icao or "UNKNOWN",
        "obstacle_id": "",
        "name": "",
        "bearing_deg": None,
        "mag_bearing_deg": None,
        "distance_m": None,
        "latitude": None,
        "longitude": None,
        "elevation_m": None,
        "height_m": None,
        "unit_distance_original": "m",
        "unit_height_original": "m",
        "confidence_score": 0.0,
        "is_user_modified": 1,
        "edited_at": None,
        "source_page": source_page,
        "raw_text": "",
        "_review_status": _STATUS_MANUAL,
        "_source_order": source_order,
    }


def _result_rows_for_review(result: ParseResult) -> list[dict]:
    rows: list[dict] = []
    source_order = 0
    for obs in result.obstacles:
        rows.append(_obstacle_to_review_row(obs, source_order))
        source_order += 1
    for failure in result.failures:
        rows.append(_failure_to_review_row(failure, source_order))
        source_order += 1
    return sorted(rows, key=_review_row_sort_key)


def _missing_text(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _validate_review_rows(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[tuple[str, str]] = set()

    if not rows:
        return ["没有可确认的障碍物数据"]

    for idx, row in enumerate(rows, start=1):
        label = f"第 {idx} 行"
        airport_icao = str(row.get("airport_icao") or "").strip()
        obstacle_id = str(row.get("obstacle_id") or "").strip()

        if not airport_icao:
            errors.append(f"{label} 缺少 ICAO")
        if not obstacle_id:
            errors.append(f"{label} 缺少编号")
        if _missing_text(row.get("name")):
            errors.append(f"{label} 缺少名称")

        has_bearing = (
            row.get("mag_bearing_deg") is not None
            or row.get("bearing_deg") is not None
        )
        if not has_bearing or row.get("distance_m") is None:
            errors.append(f"{label} 缺少方位/距离")

        if airport_icao and obstacle_id:
            key = (airport_icao.upper(), obstacle_id)
            if key in seen_ids:
                errors.append(f"{label} 编号重复：{obstacle_id}")
            seen_ids.add(key)

    return errors


def _review_rows_to_obstacles(rows: list[dict]) -> list[Obstacle]:
    return [_row_to_obstacle(row) for row in rows]


def _row_to_obstacle(row: dict) -> Obstacle:
    raw_text = row.get("raw_text") or ""
    if not raw_text:
        raw_text = f"人工补录：{row.get('obstacle_id', '')} {row.get('name', '')}".strip()
    return Obstacle(
        airport_icao=str(row.get("airport_icao") or "UNKNOWN").strip() or "UNKNOWN",
        obstacle_id=str(row.get("obstacle_id") or "").strip(),
        name=str(row.get("name") or "").strip(),
        bearing_deg=row.get("bearing_deg"),
        mag_bearing_deg=row.get("mag_bearing_deg"),
        distance_m=row.get("distance_m"),
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        elevation_m=row.get("elevation_m"),
        height_m=row.get("height_m"),
        unit_distance_original=row.get("unit_distance_original") or "m",
        unit_height_original=row.get("unit_height_original") or "m",
        confidence_score=float(row.get("confidence_score") or 0.0),
        is_user_modified=_is_user_modified(row.get("is_user_modified")),
        edited_at=row.get("edited_at"),
        source_page=int(row.get("source_page") or 0),
        raw_text=raw_text,
    )


def _resolve_output_dir(text: str, base_dir: Path | None = None) -> Path:
    raw = (text or "").strip() or "output"
    path = Path(raw).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


class _ObstacleTableModel(QAbstractTableModel):
    editFailed = Signal(str)
    rowsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_data(self, rows: list[dict]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rows_copy(self) -> list[dict]:
        return [row.copy() for row in self._rows]

    def row_dict(self, row_index: int) -> dict | None:
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]
        return None

    def add_blank_row(self, insert_at: int, defaults: dict) -> int:
        insert_at = max(0, min(insert_at, len(self._rows)))
        self.beginInsertRows(QModelIndex(), insert_at, insert_at)
        self._rows.insert(insert_at, defaults)
        self.endInsertRows()
        self.rowsChanged.emit()
        return insert_at

    def remove_row(self, row_index: int) -> bool:
        if not 0 <= row_index < len(self._rows):
            return False
        self.beginRemoveRows(QModelIndex(), row_index, row_index)
        del self._rows[row_index]
        self.endRemoveRows()
        self.rowsChanged.emit()
        return True

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLUMNS)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return _COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        field = _COLUMNS[index.column()][1]

        if role == Qt.BackgroundRole:
            color = _obstacle_row_color(row)
            return QBrush(QColor(color)) if color else None

        if role not in (Qt.DisplayRole, Qt.EditRole):
            return None

        val = row.get(field)
        if field == "is_user_modified":
            return "是" if _is_user_modified(val) else "否"
        if val is None:
            return ""
        if isinstance(val, float):
            return f"{val:.4f}" if abs(val) < 1000 else f"{val:.1f}"
        return str(val)

    def flags(self, index):
        base = super().flags(index)
        if not index.isValid():
            return base
        editable = _COLUMNS[index.column()][2]
        if editable:
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False

        field = _COLUMNS[index.column()][1]
        editable = _COLUMNS[index.column()][2]
        if not editable:
            return False

        row = self._rows[index.row()]
        try:
            new_value = self._coerce_value(field, value)
        except ValueError as exc:
            self.editFailed.emit(str(exc))
            return False

        old_value = row.get(field)
        if self._same_value(old_value, new_value):
            return True

        row[field] = new_value
        row["is_user_modified"] = 1
        self.dataChanged.emit(
            self.index(index.row(), 0),
            self.index(index.row(), self.columnCount() - 1),
            [Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole],
        )
        self.rowsChanged.emit()
        return True

    @staticmethod
    def _same_value(old_value, new_value) -> bool:
        if old_value is None or new_value is None:
            return old_value is None and new_value is None
        if isinstance(old_value, (float, int)) and isinstance(new_value, float):
            return abs(float(old_value) - new_value) < 1e-9
        return str(old_value) == str(new_value)

    @staticmethod
    def _coerce_value(field: str, value):
        text = "" if value is None else str(value).strip()
        if field == "name":
            if not text:
                raise ValueError("障碍物名称不能为空")
            return text

        if field in _FLOAT_FIELDS:
            if not text:
                return None
            try:
                val = float(text)
            except ValueError as exc:
                raise ValueError(f"{field} 需要输入数字") from exc
            if not math.isfinite(val):
                raise ValueError(f"{field} 需要输入有效数字")
            if field in {"bearing_deg", "mag_bearing_deg"} and not 0 <= val <= 360:
                raise ValueError("方位必须在 0 到 360 度之间")
            if field == "latitude" and not -90 <= val <= 90:
                raise ValueError("纬度必须在 -90 到 90 之间")
            if field == "longitude" and not -180 <= val <= 180:
                raise ValueError("经度必须在 -180 到 180 之间")
            return val

        if field in _INT_FIELDS:
            if not text:
                return 0
            try:
                return int(text)
            except ValueError as exc:
                raise ValueError(f"{field} 需要输入整数") from exc

        return text

    @staticmethod
    def _column_index(field_name: str) -> int | None:
        for idx, (_, field, _) in enumerate(_COLUMNS):
            if field == field_name:
                return idx
        return None


# ---------------------------------------------------------------------------
# 解析失败表格模型
# ---------------------------------------------------------------------------

_FAILURE_COLS = [("ICAO", "airport_icao"), ("页码", "source_page"), ("原文", "raw_text"), ("原因", "reason")]


class _FailureTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_data(self, rows: list[dict]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(_FAILURE_COLS)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return _FAILURE_COLS[section][0]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        row = self._rows[index.row()]
        field = _FAILURE_COLS[index.column()][1]
        val = row.get(field, "")
        return str(val) if val is not None else ""


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AIP 障碍物数据识别工具")
        self.resize(1100, 680)

        self._parse_result: ParseResult | None = None
        self._out_dir: Path | None = None
        self._confirmed_obstacles: list[Obstacle] = []
        self._confirmed_file_hash: str | None = None
        self._confirmed_row_count = 0

        self._setup_ui()
        self._update_buttons(has_data=False, confirmed=False)

    # ------------------------------------------------------------------
    # UI 搭建
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- 文件选择区 ---
        file_group = QGroupBox("输入")
        fl = QHBoxLayout(file_group)
        fl.addWidget(QLabel("AIP 文件:"))
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("选择 .pdf 或 .txt 文件...")
        fl.addWidget(self._file_edit, 1)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._on_browse_file)
        fl.addWidget(btn_browse)
        fl.addWidget(QLabel("  指定机场(可选):"))
        self._icao_edit = QLineEdit()
        self._icao_edit.setPlaceholderText("如 ZBAA")
        self._icao_edit.setMaximumWidth(70)
        fl.addWidget(self._icao_edit)
        fl.addWidget(QLabel("  输出目录:"))
        self._out_edit = QLineEdit("output")
        fl.addWidget(self._out_edit, 1)
        btn_out = QPushButton("浏览...")
        btn_out.clicked.connect(self._on_browse_out)
        fl.addWidget(btn_out)
        root.addWidget(file_group)

        # --- 操作按钮区 ---
        btn_row = QHBoxLayout()
        self._btn_parse = QPushButton("解析文件")
        self._btn_parse.clicked.connect(self._on_parse)
        self._btn_parse.setMinimumHeight(36)
        btn_row.addWidget(self._btn_parse)

        btn_row.addSpacing(20)
        self._btn_add_above = QPushButton("上方新增行")
        self._btn_add_above.clicked.connect(lambda: self._on_add_row(after=False))
        btn_row.addWidget(self._btn_add_above)

        self._btn_add_below = QPushButton("下方新增行")
        self._btn_add_below.clicked.connect(lambda: self._on_add_row(after=True))
        btn_row.addWidget(self._btn_add_below)

        self._btn_delete_row = QPushButton("删除选中行")
        self._btn_delete_row.clicked.connect(self._on_delete_row)
        btn_row.addWidget(self._btn_delete_row)

        btn_row.addSpacing(20)
        self._btn_confirm = QPushButton("最终确认")
        self._btn_confirm.clicked.connect(self._on_confirm)
        btn_row.addWidget(self._btn_confirm)

        btn_row.addWidget(QLabel("导出:"))
        self._btn_xlsx = QPushButton("导出 XLSX")
        self._btn_xlsx.clicked.connect(lambda: self._on_export("xlsx"))
        btn_row.addWidget(self._btn_xlsx)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # --- 统计摘要 ---
        self._stats_label = QLabel("就绪，请选择 AIP 文件并点击「解析文件」")
        root.addWidget(self._stats_label)

        self._legend_label = QLabel(
            '<span style="background-color:#FFD6D6;">&nbsp;&nbsp;&nbsp;</span> '
            '红色：高风险，必须人工复核&nbsp;&nbsp;'
            '<span style="background-color:#FFF3BF;">&nbsp;&nbsp;&nbsp;</span> '
            '黄色：存在风险&nbsp;&nbsp;'
            '<span style="background-color:#D7ECFF;">&nbsp;&nbsp;&nbsp;</span> '
            '蓝色：已人工修改'
        )
        root.addWidget(self._legend_label)

        # --- 结果表格区 ---
        self._tabs = QTabWidget()
        self._obstacle_table = QTableView()
        self._obstacle_table.setSortingEnabled(False)
        self._obstacle_table.horizontalHeader().setStretchLastSection(True)
        self._obstacle_table.setAlternatingRowColors(True)
        self._obstacle_model = _ObstacleTableModel()
        self._obstacle_model.editFailed.connect(self.statusBar().showMessage)
        self._obstacle_model.rowsChanged.connect(self._mark_unconfirmed)
        self._obstacle_table.setModel(self._obstacle_model)

        self._failure_table = QTableView()
        self._failure_table.setAlternatingRowColors(True)
        self._failure_table.horizontalHeader().setStretchLastSection(True)
        self._failure_model = _FailureTableModel()
        self._failure_table.setModel(self._failure_model)

        self._tabs.addTab(self._obstacle_table, "障碍物数据")
        self._tabs.addTab(self._failure_table, "解析失败")
        root.addWidget(self._tabs, 1)

        # --- 状态栏 ---
        self.statusBar().showMessage("就绪")

    # ------------------------------------------------------------------
    # 文件选择
    # ------------------------------------------------------------------

    def _on_browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 AIP 文件", "",
            "AIP 文件 (*.pdf *.txt);;PDF (*.pdf);;TXT (*.txt);;所有文件 (*)"
        )
        if path:
            self._file_edit.setText(path)

    def _on_browse_out(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self._out_edit.setText(path)

    def _current_out_dir(self) -> Path:
        out_dir = _resolve_output_dir(self._out_edit.text(), Path.cwd())
        out_dir.mkdir(parents=True, exist_ok=True)
        self._out_dir = out_dir
        return out_dir

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------

    def _on_parse(self):
        file_path = self._file_edit.text().strip()
        if not file_path:
            QMessageBox.warning(self, "提示", "请先选择输入文件")
            return
        if not Path(file_path).exists():
            QMessageBox.warning(self, "提示", f"文件不存在：{file_path}")
            return

        icao = self._icao_edit.text().strip() or None
        self._confirmed_file_hash = None
        self._confirmed_row_count = 0
        self._confirmed_obstacles = []
        self._update_buttons(has_data=False, confirmed=False)
        self._obstacle_model.set_data([])
        self._failure_model.set_data([])
        self._tabs.setTabText(0, "确认表")
        self._tabs.setTabText(1, "解析失败")

        self._btn_parse.setEnabled(False)
        self._btn_parse.setText("解析中...")
        self.statusBar().showMessage("正在解析，请稍候...")

        self._worker = _ParseWorker(file_path, icao)
        self._worker.finished.connect(self._on_parse_done)
        self._worker.error.connect(self._on_parse_error)
        self._worker.start()

    def _on_parse_done(self, result: ParseResult):
        self._parse_result = result
        self._btn_parse.setEnabled(True)
        self._btn_parse.setText("解析文件")
        self._confirmed_file_hash = None
        self._confirmed_row_count = 0

        stats = result.stats
        review_rows = _result_rows_for_review(result)
        self._stats_label.setText(
            f"解析完成 | 候选 {stats.total_candidates} 条 | "
            f"成功 {stats.total_success} 条 | 待补录 {stats.total_failed} 条"
        )

        self.statusBar().showMessage(
            f"解析完成 — {result.source_file} | 请补齐待补录行后点击最终确认"
        )

        self._obstacle_model.set_data(review_rows)
        self._failure_model.set_data([
            {"airport_icao": f.airport_icao, "source_page": f.source_page,
             "raw_text": f.raw_text, "reason": f.reason}
            for f in result.failures
        ])

        self._tabs.setCurrentIndex(0)
        self._tabs.setTabText(0, f"确认表 ({len(review_rows)})")
        self._tabs.setTabText(1, f"解析失败 ({len(result.failures)})")
        self._update_buttons(has_data=True, confirmed=False)

        # 自适应列宽
        self._obstacle_table.resizeColumnsToContents()

    def _on_parse_error(self, msg: str):
        self._btn_parse.setEnabled(True)
        self._btn_parse.setText("解析文件")
        self.statusBar().showMessage("解析出错")
        QMessageBox.critical(self, "解析失败", msg)

    # ------------------------------------------------------------------
    # 当前确认表操作
    # ------------------------------------------------------------------

    def _current_row_index(self) -> int:
        index = self._obstacle_table.currentIndex()
        return index.row() if index.isValid() else -1

    def _new_row_defaults(self, selected_row: int) -> dict:
        selected = self._obstacle_model.row_dict(selected_row)
        if selected is not None:
            airport_icao = selected.get("airport_icao") or "UNKNOWN"
            source_page = int(selected.get("source_page") or 1)
        elif self._parse_result and self._parse_result.obstacles:
            airport_icao = self._parse_result.obstacles[0].airport_icao
            source_page = self._parse_result.obstacles[0].source_page
        else:
            airport_icao = self._icao_edit.text().strip() or "UNKNOWN"
            source_page = 1
        return _blank_review_row(
            airport_icao=airport_icao,
            source_page=source_page,
            source_order=len(self._obstacle_model.rows_copy()),
        )

    def _on_add_row(self, after: bool):
        if self._parse_result is None:
            QMessageBox.warning(self, "提示", "请先解析文件")
            return
        selected = self._current_row_index()
        insert_at = selected + (1 if after and selected >= 0 else 0)
        if selected < 0:
            insert_at = self._obstacle_model.rowCount()
        row_index = self._obstacle_model.add_blank_row(
            insert_at, self._new_row_defaults(selected)
        )
        self._obstacle_table.selectRow(row_index)
        self._tabs.setTabText(0, f"确认表 ({self._obstacle_model.rowCount()})")

    def _on_delete_row(self):
        selected = self._current_row_index()
        if selected < 0:
            QMessageBox.warning(self, "提示", "请先选中要删除的行")
            return
        if self._obstacle_model.remove_row(selected):
            self._tabs.setTabText(0, f"确认表 ({self._obstacle_model.rowCount()})")

    def _mark_unconfirmed(self):
        if self._parse_result is None:
            return
        self._confirmed_file_hash = None
        self._confirmed_row_count = 0
        self._confirmed_obstacles = []
        self._update_buttons(
            has_data=self._parse_result is not None,
            confirmed=False,
        )
        self.statusBar().showMessage("当前表格有未确认修改，请点击最终确认后再导出")

    def _on_confirm(self):
        if self._parse_result is None:
            QMessageBox.warning(self, "提示", "请先解析文件")
            return

        rows = self._obstacle_model.rows_copy()
        errors = _validate_review_rows(rows)
        if errors:
            preview = "\n".join(errors[:12])
            if len(errors) > 12:
                preview += f"\n……另有 {len(errors) - 12} 个问题"
            QMessageBox.warning(
                self,
                "不能最终确认",
                "请先补齐确认表中的问题：\n\n" + preview,
            )
            return

        obstacles = _review_rows_to_obstacles(rows)
        out_dir = self._current_out_dir()
        db_path = out_dir / "aip_obstacle.sqlite"
        try:
            with SQLiteStore(db_path) as store:
                store.replace_confirmed_obstacles(
                    file_path=self._parse_result.source_file,
                    file_hash=self._parse_result.file_hash,
                    obstacles=obstacles,
                )
        except Exception as exc:
            QMessageBox.critical(self, "最终确认失败", str(exc))
            return

        self._confirmed_file_hash = self._parse_result.file_hash
        self._confirmed_row_count = len(obstacles)
        self._confirmed_obstacles = obstacles
        self._update_buttons(has_data=True, confirmed=True)
        self.statusBar().showMessage(
            f"最终确认完成：{len(obstacles)} 条记录已写入 {db_path}，可以导出 XLSX"
        )

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def _on_export(self, fmt: str):
        if self._parse_result is None:
            QMessageBox.warning(self, "提示", "请先解析文件")
            return
        if self._confirmed_file_hash != self._parse_result.file_hash:
            QMessageBox.warning(
                self,
                "不能导出",
                "请先点击“最终确认”。XLSX 只会导出本次确认后的数据。",
            )
            return
        if not self._confirmed_obstacles:
            QMessageBox.warning(self, "提示", "没有本次确认数据，请重新最终确认")
            return

        out_dir = self._current_out_dir()
        db_path = out_dir / "aip_obstacle.sqlite"

        try:
            with SQLiteStore(db_path) as store:
                store.replace_confirmed_obstacles(
                    file_path=self._parse_result.source_file,
                    file_hash=self._parse_result.file_hash,
                    obstacles=self._confirmed_obstacles,
                )

            with SQLiteStore(db_path) as store:
                obstacles = store.fetch_obstacles_by_file_hash(self._confirmed_file_hash)

            if len(obstacles) != self._confirmed_row_count:
                QMessageBox.warning(
                    self,
                    "不能导出",
                    "数据库中的确认数据数量与当前会话不一致，请重新点击最终确认。",
                )
                return

            obs_list = [_row_to_obstacle(row) for row in obstacles]
            xlsx_path = out_dir / "obstacles.xlsx"
            export_xlsx(obs_list, xlsx_path)

            self.statusBar().showMessage(
                f"导出完成：XLSX → {xlsx_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _update_buttons(self, has_data: bool, confirmed: bool):
        row_count = self._obstacle_model.rowCount()
        self._btn_add_above.setEnabled(has_data)
        self._btn_add_below.setEnabled(has_data)
        self._btn_delete_row.setEnabled(has_data and row_count > 0)
        self._btn_confirm.setEnabled(has_data and row_count > 0)
        self._btn_xlsx.setEnabled(has_data and row_count > 0 and confirmed)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
