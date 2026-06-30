"""日志初始化。统一输出到 stdout 和文件。"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "aip_obstacle"


def get_logger(out_dir: Optional[str | Path] = None) -> logging.Logger:
    """获取模块 logger。如果传入 out_dir，则同时写入 <out_dir>/logs/run_YYYYMMDD_HHMMSS.log。

    多次调用不会重复添加 handler。
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    if out_dir is not None:
        log_dir = Path(out_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(
            log_dir / f"run_{stamp}.log", encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger
