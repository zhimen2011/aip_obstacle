# AIP 障碍物数据识别与结构化模块

从中国民航 AIP（航行资料汇编）中自动提取机场障碍物数据，结构化存入 SQLite，并支持导出 CSV / JSON / GeoJSON。

本模块是更大航空运行系统的上游数据组件，不是面向旅客或飞行员的终端产品。

---

## 安装

**环境要求：** Python 3.10+

```bash
pip install -r requirements.txt
```

---

## 使用方法

### 1. 解析 AIP 文件

```bash
python -m aip_obstacle.cli parse <输入文件> --out <输出目录>
```

示例：

```bash
# 解析 TXT 文件
python -m aip_obstacle.cli parse examples/sample_aip.txt --out output/

# 解析文本型 PDF
python -m aip_obstacle.cli parse data/ZBAA_AD2.pdf --out output/
```

解析完成后，`output/` 目录下会生成 `aip_obstacle.sqlite` 数据库。

### 2. 导出数据

```bash
python -m aip_obstacle.cli export <输出目录> --format csv|json|geojson|all
```

示例：

```bash
# 导出全部格式
python -m aip_obstacle.cli export output/ --format all

# 只导出 GeoJSON
python -m aip_obstacle.cli export output/ --format geojson
```

### 3. 输出文件说明

```
output/
├── aip_obstacle.sqlite      # 主数据库（可用 DB Browser for SQLite 查看）
├── obstacles.csv            # 全量障碍物，缺字段留空
├── obstacles.json           # 全量障碍物，缺字段为 null
├── obstacles.geojson        # 仅含经纬度的障碍物（可在 QGIS / geojson.io 查看）
├── parse_failures.csv       # 识别失败的行（保留原文，供人工复核）
└── logs/
    └── run_YYYYMMDD_HHMMSS.log
```

---

## 快速验证（从零到跑通）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 用内置样例文件测试
python -m aip_obstacle.cli parse examples/sample_aip.txt --out output/

# 3. 导出
python -m aip_obstacle.cli export output/ --format all

# 4. 运行测试
python -m pytest tests/ -v
```

---

## 项目结构

```
src/aip_obstacle/
├── __init__.py          # 公共 API 入口
├── cli.py               # 命令行入口（parse / export）
├── models.py            # 数据结构（TextBlock / Obstacle / ParseResult 等）
├── pipeline.py          # 处理管线（串联 parsers / services / storage）
├── parsers/
│   ├── txt_parser.py    # TXT 文件 → List[TextBlock]
│   ├── pdf_parser.py    # 文本型 PDF → List[TextBlock]
│   └── ocr_parser.py    # 占位，本期不实现
├── services/
│   ├── detector.py      # 识别疑似障碍物行
│   └── field_parser.py  # 解析编号/名称/方位/距离/经纬度/高度
├── storage/
│   └── sqlite_store.py  # SQLite 读写封装
├── exporters/
│   ├── csv_exporter.py
│   ├── json_exporter.py
│   └── geojson_exporter.py
└── utils/
    ├── geo.py           # 坐标转换、单位换算
    ├── hashing.py       # 文件 sha256（去重用）
    └── logging.py       # 日志初始化
```

---

## 核心模块说明

| 模块 | 职责 |
|------|------|
| `parsers/` | 只负责从文件中提取原始文本 + 页码，不做业务判断 |
| `services/` | 识别候选行、解析字段、单位标准化 |
| `storage/` | SQLite schema 初始化和读写，去重逻辑在数据库层（UNIQUE 约束） |
| `exporters/` | 把数据库记录写成文件，不做字段计算 |
| `pipeline.py` | 把以上各层串联，对外暴露 `parse_file()` / `parse_text()` |

---

## 支持的输入格式

| 格式 | 状态 |
|------|------|
| 文本型 PDF（能复制文字） | ✅ 支持 |
| TXT 纯文本 | ✅ 支持 |
| 扫描版 PDF / 图片 | ❌ 本期不支持（OCR 接口预留） |
| Word / Excel | ❌ 本期不支持 |

---

## 常见问题

**Q：PDF 解析出来是空的？**
A：该 PDF 可能是扫描件（无文本层），本期不支持 OCR。请先用 Adobe Acrobat 或其他工具将其转为文本型 PDF，或手动导出为 TXT。

**Q：障碍物的机场归属显示 UNKNOWN？**
A：解析器从页眉或章节标题识别 ICAO 四字码（Z 开头，如 ZBAA）。如果 AIP 文本中没有这类标识，可以在命令行用 `--airport` 参数手动指定（后续版本支持）。

**Q：同一份文件导入两次会重复吗？**
A：不会。系统用文件 sha256 哈希去重，同一文件第二次导入会直接跳过。

**Q：parse_failures.csv 里的记录是什么？**
A：识别为「疑似障碍物行」但关键字段（编号、名称、定位信息）无法解析的行。保留原文供人工复核，不会丢失。

---

## 运行测试

```bash
python -m pytest tests/ -v
```

当前测试覆盖：
- 坐标转换（度分秒 ↔ 十进制）
- 单位换算（ft/m/km/NM）
- 机场 ICAO 识别 + 候选行识别
- 字段解析（编号/名称/方位/距离/经纬度/高度）
- SQLite 入库去重
- 端到端冒烟测试（parse → 写库 → 导出三种格式）

---

## 后续扩展方向

- OCR 支持（扫描版 PDF）
- 根据「方位 + 距离 + ARP 坐标」反推障碍物经纬度
- 磁方位自动换算为真方位
- 图形界面（PySide6）
- 与更大航空运行系统的对接接口
- 历史版本比对（AIP 周期性更新）
