"""PyInstaller 入口：把 argparse 的 SystemExit/正常返回统一为进程退出码。

规则引擎失败时 cli.main 内部 raise SystemExit(2)，console 入口会原样传播，
这里显式调用以保证 exe 语义与 `python -m` 完全一致。
"""
import multiprocessing
import sys

from mcd_postmortem.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
    sys.exit(0)
