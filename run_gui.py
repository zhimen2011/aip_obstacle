import sys
from pathlib import Path

# 把 src 目录加入 Python 搜索路径
src = Path(__file__).parent / "src"
sys.path.insert(0, str(src))

from aip_obstacle.ui.main_window import run_gui
run_gui()
