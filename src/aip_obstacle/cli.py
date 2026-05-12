"""命令行入口。

用法：
    python -m aip_obstacle.cli parse <文件> --out <输出目录>
    python -m aip_obstacle.cli export <输出目录> --format csv|json|geojson|all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aip_obstacle.utils.logging import get_logger


def _cmd_parse(args: argparse.Namespace) -> int:
    logger = get_logger(args.out)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "aip_obstacle.sqlite"

    from aip_obstacle.pipeline import parse_file
    from aip_obstacle.storage.sqlite_store import SQLiteStore

    try:
        result = parse_file(args.file)
    except FileNotFoundError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"解析失败：{e}", file=sys.stderr)
        return 1

    with SQLiteStore(db_path) as store:
        if store.file_already_imported(result.file_hash):
            logger.warning("文件已导入过（hash 相同），跳过写库：%s", args.file)
        else:
            sf_id = store.insert_source_file(
                file_path=args.file,
                file_hash=result.file_hash,
                total_candidates=result.stats.total_candidates,
                total_success=result.stats.total_success,
                total_failed=result.stats.total_failed,
            )
            store.save_parse_result(result, source_file_id=sf_id)
            logger.info(
                "写库完成：%d 条障碍物，%d 条失败记录",
                result.stats.total_success,
                result.stats.total_failed,
            )

    print(
        f"解析完成：候选 {result.stats.total_candidates} | "
        f"成功 {result.stats.total_success} | "
        f"失败 {result.stats.total_failed}"
    )
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    db_path = out_dir / "aip_obstacle.sqlite"

    if not db_path.exists():
        print(f"错误：数据库不存在，请先运行 parse 命令：{db_path}", file=sys.stderr)
        return 1

    from aip_obstacle.storage.sqlite_store import SQLiteStore
    from aip_obstacle.exporters.csv_exporter import export_csv, export_failures_csv
    from aip_obstacle.exporters.json_exporter import export_json
    from aip_obstacle.exporters.geojson_exporter import export_geojson

    fmt = args.format.lower()

    with SQLiteStore(db_path) as store:
        obstacles = store.fetch_all_obstacles()
        failures = store.fetch_all_failures()

    if fmt in ("csv", "all"):
        export_csv(obstacles, out_dir / "obstacles.csv")
        export_failures_csv(failures, out_dir / "parse_failures.csv")
        print(f"已导出 CSV：{out_dir / 'obstacles.csv'}")

    if fmt in ("json", "all"):
        export_json(obstacles, out_dir / "obstacles.json")
        print(f"已导出 JSON：{out_dir / 'obstacles.json'}")

    if fmt in ("geojson", "all"):
        skipped = export_geojson(obstacles, out_dir / "obstacles.geojson")
        print(f"已导出 GeoJSON：{out_dir / 'obstacles.geojson'}（跳过 {skipped} 条无坐标记录）")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aip_obstacle",
        description="AIP 障碍物数据识别与结构化工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # parse 子命令
    p_parse = sub.add_parser("parse", help="解析 AIP 文件并写入数据库")
    p_parse.add_argument("file", help="输入文件路径（.pdf 或 .txt）")
    p_parse.add_argument("--out", default="output", help="输出目录（默认 output/）")

    # gui 子命令
    sub.add_parser("gui", help="启动图形界面")

    # export 子命令
    p_export = sub.add_parser("export", help="从数据库导出文件")
    p_export.add_argument("out_dir", help="输出目录（含 aip_obstacle.sqlite）")
    p_export.add_argument(
        "--format",
        choices=["csv", "json", "geojson", "all"],
        default="all",
        help="导出格式（默认 all）",
    )

    args = parser.parse_args()
    if args.command == "parse":
        sys.exit(_cmd_parse(args))
    elif args.command == "gui":
        from aip_obstacle.ui.main_window import run_gui
        sys.exit(run_gui())
    elif args.command == "export":
        sys.exit(_cmd_export(args))


if __name__ == "__main__":
    main()
