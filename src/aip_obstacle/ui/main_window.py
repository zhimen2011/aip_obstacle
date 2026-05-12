"""AIP 障碍物数据识别工具 — GUI 主窗口（PySide6）。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, Signal
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
from aip_obstacle.exporters.csv_exporter import export_csv, export_failures_csv
from aip_obstacle.exporters.json_exporter import export_json
from aip_obstacle.exporters.geojson_exporter import export_geojson
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
    ("ICAO", "airport_icao"),
    ("编号", "obstacle_id"),
    ("名称", "name"),
    ("方位(°)", "bearing_deg"),
    ("磁方位(°)", "mag_bearing_deg"),
    ("距离(m)", "distance_m"),
    ("纬度", "latitude"),
    ("经度", "longitude"),
    ("海拔(m)", "elevation_m"),
    ("高度(m)", "height_m"),
    ("可信度", "confidence_score"),
    ("页码", "source_page"),
]


class _ObstacleTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[Obstacle] = []

    def set_data(self, rows: list[Obstacle]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLUMNS)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return _COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        row = self._rows[index.row()]
        field = _COLUMNS[index.column()][1]
        val = getattr(row, field, None)
        if val is None:
            return ""
        if isinstance(val, float):
            return f"{val:.4f}" if abs(val) < 1000 else f"{val:.1f}"
        return str(val)


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

        self._setup_ui()
        self._update_buttons(has_data=False)

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
        btn_row.addWidget(QLabel("导出:"))
        self._btn_csv = QPushButton("CSV")
        self._btn_csv.clicked.connect(lambda: self._on_export("csv"))
        btn_row.addWidget(self._btn_csv)
        self._btn_json = QPushButton("JSON")
        self._btn_json.clicked.connect(lambda: self._on_export("json"))
        btn_row.addWidget(self._btn_json)
        self._btn_geojson = QPushButton("GeoJSON")
        self._btn_geojson.clicked.connect(lambda: self._on_export("geojson"))
        btn_row.addWidget(self._btn_geojson)
        self._btn_xlsx = QPushButton("XLSX")
        self._btn_xlsx.clicked.connect(lambda: self._on_export("xlsx"))
        btn_row.addWidget(self._btn_xlsx)
        self._btn_all = QPushButton("导出全部")
        self._btn_all.clicked.connect(lambda: self._on_export("all"))
        btn_row.addWidget(self._btn_all)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # --- 统计摘要 ---
        self._stats_label = QLabel("就绪，请选择 AIP 文件并点击「解析文件」")
        root.addWidget(self._stats_label)

        # --- 结果表格区 ---
        self._tabs = QTabWidget()
        self._obstacle_table = QTableView()
        self._obstacle_table.setSortingEnabled(True)
        self._obstacle_table.horizontalHeader().setStretchLastSection(True)
        self._obstacle_table.setAlternatingRowColors(True)
        self._obstacle_model = _ObstacleTableModel()
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

        self._out_dir = Path(self._out_edit.text().strip() or "output")
        self._out_dir.mkdir(parents=True, exist_ok=True)

        icao = self._icao_edit.text().strip() or None

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
        self._update_buttons(has_data=True)

        stats = result.stats
        self._stats_label.setText(
            f"解析完成 | 候选 {stats.total_candidates} 条 | "
            f"成功 {stats.total_success} 条 | 失败 {stats.total_failed} 条 | "
            f"无经纬度 {stats.total_no_coord} 条"
        )

        self._obstacle_model.set_data(result.obstacles)
        self._failure_model.set_data([
            {"airport_icao": f.airport_icao, "source_page": f.source_page,
             "raw_text": f.raw_text, "reason": f.reason}
            for f in result.failures
        ])

        self._tabs.setCurrentIndex(0)
        self._tabs.setTabText(0, f"障碍物数据 ({len(result.obstacles)})")
        self._tabs.setTabText(1, f"解析失败 ({len(result.failures)})")

        # 自适应列宽
        self._obstacle_table.resizeColumnsToContents()

        self.statusBar().showMessage(
            f"解析完成 — {result.source_file} | 成功 {stats.total_success} / 失败 {stats.total_failed}"
        )

        # 自动写库
        self._write_db(result)

    def _on_parse_error(self, msg: str):
        self._btn_parse.setEnabled(True)
        self._btn_parse.setText("解析文件")
        self.statusBar().showMessage("解析出错")
        QMessageBox.critical(self, "解析失败", msg)

    # ------------------------------------------------------------------
    # 写库
    # ------------------------------------------------------------------

    def _write_db(self, result: ParseResult):
        db_path = self._out_dir / "aip_obstacle.sqlite"
        try:
            with SQLiteStore(db_path) as store:
                if store.file_already_imported(result.file_hash):
                    self.statusBar().showMessage(
                        self.statusBar().currentMessage() + " | 文件已导入过，跳过写库"
                    )
                    return
                sf_id = store.insert_source_file(
                    file_path=result.source_file,
                    file_hash=result.file_hash,
                    total_candidates=result.stats.total_candidates,
                    total_success=result.stats.total_success,
                    total_failed=result.stats.total_failed,
                )
                store.save_parse_result(result, source_file_id=sf_id)
            self.statusBar().showMessage(
                self.statusBar().currentMessage() + " | 已写入数据库"
            )
        except Exception as exc:
            self.statusBar().showMessage(
                self.statusBar().currentMessage() + f" | 写库失败: {exc}"
            )

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def _on_export(self, fmt: str):
        if self._parse_result is None:
            QMessageBox.warning(self, "提示", "请先解析文件")
            return
        if self._out_dir is None:
            return

        db_path = self._out_dir / "aip_obstacle.sqlite"
        if not db_path.exists():
            QMessageBox.warning(self, "提示", f"数据库不存在：{db_path}")
            return

        try:
            with SQLiteStore(db_path) as store:
                obstacles = store.fetch_all_obstacles()
                failures = store.fetch_all_failures()

            msgs = []
            if fmt in ("csv", "all"):
                export_csv(obstacles, self._out_dir / "obstacles.csv")
                export_failures_csv(failures, self._out_dir / "parse_failures.csv")
                msgs.append("CSV")
            if fmt in ("json", "all"):
                export_json(obstacles, self._out_dir / "obstacles.json")
                msgs.append("JSON")
            if fmt in ("geojson", "all"):
                skipped = export_geojson(obstacles, self._out_dir / "obstacles.geojson")
                msgs.append(f"GeoJSON(跳过{skipped}条)")
            if fmt in ("xlsx", "all"):
                # obstacles 是 dict 列表，需转成 Obstacle 对象
                from aip_obstacle.models import Obstacle as ObsModel
                obs_list = [
                    ObsModel(
                        airport_icao=row.get("airport_icao", ""),
                        obstacle_id=row.get("obstacle_id", ""),
                        name=row.get("name", ""),
                        mag_bearing_deg=row.get("mag_bearing_deg"),
                        distance_m=row.get("distance_m"),
                        elevation_m=row.get("elevation_m"),
                    )
                    for row in obstacles
                ]
                export_xlsx(obs_list, self._out_dir / "obstacles.xlsx")
                msgs.append("XLSX")

            self.statusBar().showMessage(f"导出完成：{' | '.join(msgs)} → {self._out_dir}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _update_buttons(self, has_data: bool):
        for btn in (self._btn_csv, self._btn_json, self._btn_geojson, self._btn_xlsx, self._btn_all):
            btn.setEnabled(has_data)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
