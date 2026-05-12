"""Excel 导出器：按 AIP 机场细则样式（左右双栏）写出障碍物表。"""

from __future__ import annotations

from pathlib import Path
from typing import List

from aip_obstacle.models import Obstacle

_SECTION_SPLIT_M = 15_000  # 15km 分界线
_SEPARATOR_COLS = 2       # 左右栏之间的空列数
_LEFT_COLS = 6            # 左侧列数 (序号+名称+方位+距离+海拔+场压)
_RIGHT_COLS = 6           # 右侧列数
_TOTAL_COLS = _LEFT_COLS + _SEPARATOR_COLS + _RIGHT_COLS


def export_xlsx(obstacles: List[Obstacle], out_path: str | Path) -> None:
    """把障碍物列表写成双栏 Excel（左: ≤15km, 右: >15km）。

    输出格式参考中国 AIP AD 2.10 障碍物表 ZSHC.xlsx 样式。
    依赖 openpyxl，未安装时抛出 ImportError。
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ImportError("请先安装 openpyxl：pip install openpyxl")

    # --- 分栏 ---
    left = sorted(
        [o for o in obstacles if o.distance_m is not None and o.distance_m <= _SECTION_SPLIT_M],
        key=lambda o: o.distance_m or 0,
    )
    right = sorted(
        [o for o in obstacles if o.distance_m is not None and o.distance_m > _SECTION_SPLIT_M],
        key=lambda o: o.distance_m or 0,
    )

    nrows = max(len(left), len(right)) + 2  # +2 行表头
    RIGHT_START = _LEFT_COLS + _SEPARATOR_COLS + 1  # 右侧起始列号

    wb = Workbook()
    ws = wb.active
    ws.title = "机场细则障碍物"

    # --- 样式 ---
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    header_font = Font(bold=True, size=10)
    title_font = Font(bold=True, size=11)
    wrap_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def _border_row(r: int):
        for c in range(1, _TOTAL_COLS + 1):
            ws.cell(row=r, column=c).border = thin_border

    # --- 第 1 行：章节标题 ---
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=_LEFT_COLS)
    c = ws.cell(row=1, column=1, value="半径15 千米内主要障碍物")
    c.font = title_font
    c.alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells(start_row=1, start_column=RIGHT_START,
                   end_row=1, end_column=RIGHT_START + _RIGHT_COLS - 1)
    c = ws.cell(row=1, column=RIGHT_START, value="半径15 千米-50 千米内主要障碍物")
    c.font = title_font
    c.alignment = Alignment(horizontal="center", vertical="center")

    # --- 第 2 行：列标题 ---
    headers = ["障碍物名称", "磁方位（度）", "相对跑道基准点距离（m）", "海拔高度（m）", "场压高度（m）"]
    # 左侧: 序号在第 1 列(表头为空), 名称从第 2 列开始
    for ci, h in enumerate(headers):
        cell = ws.cell(row=2, column=2 + ci, value=h)
        cell.font = header_font
        cell.alignment = wrap_align
    # 右侧同理
    for ci, h in enumerate(headers):
        cell = ws.cell(row=2, column=RIGHT_START + 1 + ci, value=h)
        cell.font = header_font
        cell.alignment = wrap_align

    # --- 数据行 ---
    for idx in range(max(len(left), len(right))):
        row = idx + 3

        # 左侧
        if idx < len(left):
            obs = left[idx]
            ws.cell(row=row, column=1, value=idx + 1)
            ws.cell(row=row, column=2, value=f"{obs.name}\n{obs.obstacle_id}")
            if obs.mag_bearing_deg is not None:
                ws.cell(row=row, column=3, value=int(obs.mag_bearing_deg))
            if obs.distance_m is not None:
                ws.cell(row=row, column=4, value=int(obs.distance_m))
            if obs.elevation_m is not None:
                c = ws.cell(row=row, column=5, value=round(obs.elevation_m, 1))
                c.number_format = "0.0"
            # col 6 = 场压高度，留空

        # 右侧
        if idx < len(right):
            obs = right[idx]
            seq_col = RIGHT_START            # 序号
            name_col = RIGHT_START + 1        # 名称
            brg_col = RIGHT_START + 2         # 方位
            dist_col = RIGHT_START + 3        # 距离
            elev_col = RIGHT_START + 4        # 海拔
            # pres_col = RIGHT_START + 5      # 场压(空)

            ws.cell(row=row, column=seq_col, value=idx + 1)
            ws.cell(row=row, column=name_col, value=f"{obs.name}\n{obs.obstacle_id}")
            if obs.mag_bearing_deg is not None:
                ws.cell(row=row, column=brg_col, value=int(obs.mag_bearing_deg))
            if obs.distance_m is not None:
                ws.cell(row=row, column=dist_col, value=int(obs.distance_m))
            if obs.elevation_m is not None:
                c = ws.cell(row=row, column=elev_col, value=round(obs.elevation_m, 1))
                c.number_format = "0.0"

    # --- 边框 ---
    for r in range(1, nrows + 1):
        _border_row(r)

    # --- 列宽 ---
    width_map = {1: 6, 2: 28, 3: 12, 4: 14, 5: 12, 6: 10}
    for ci, w in width_map.items():
        ws.column_dimensions[get_column_letter(ci)].width = w
    for sp in range(1, _SEPARATOR_COLS + 1):
        ws.column_dimensions[get_column_letter(_LEFT_COLS + sp)].width = 3
    for ci, w in width_map.items():
        ws.column_dimensions[get_column_letter(RIGHT_START - 1 + ci)].width = w

    # --- 行高 ---
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 36
    for r in range(3, nrows + 1):
        ws.row_dimensions[r].height = 28

    # --- 写入 ---
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(p))
