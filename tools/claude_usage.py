#!/usr/bin/env python3
"""
Print Claude Code token usage. A thin CLI over ajazz_dock.claude_usage, which
is the same code the status strip uses.

    ./.venv/bin/python tools/claude_usage.py
    ./.venv/bin/python tools/claude_usage.py --json
    ./.venv/bin/python tools/claude_usage.py --limit 3000000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ajazz_dock import claude_usage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    parser.add_argument("--limit", type=int,
                        default=claude_usage.DEFAULT_LIMIT_OUT,
                        help="5h output-token baseline used for the percentage")
    args = parser.parse_args()

    data = claude_usage.collect(args.limit)
    if args.json:
        print(json.dumps(data))
        return 0

    fmt = claude_usage.fmt
    window = data["window"]
    print("5 小时窗口")
    if not window["open"]:
        print("  当前空闲 —— 下一条消息会开启一个新窗口")
    else:
        print(f"  起点      {datetime.fromtimestamp(window['start']):%m-%d %H:%M}")
        print(f"  重置      {datetime.fromtimestamp(window['reset']):%m-%d %H:%M}"
              f"  (还剩 {window['seconds_left'] / 60:.0f} 分钟)")
        print(f"  已输出    {fmt(window['out'])} / {fmt(window['limit'])}"
              f"  —— 剩余 {window['pct_left']:.0f}%")
        print(f"  消息数    {window['msgs']}")
        print("  注：limit 是自定基准，不是真实额度（本地无额度数据）")

    print(f"\n{'窗口':<8}{'输入':>9}{'输出':>9}{'缓存写':>10}{'缓存读':>11}"
          f"{'总计':>10}{'消息':>7}")
    for name, bucket in data["buckets"].items():
        print(f"{name:<8}{fmt(bucket['in']):>9}{fmt(bucket['out']):>9}"
              f"{fmt(bucket['cache_w']):>10}{fmt(bucket['cache_r']):>11}"
              f"{fmt(bucket['total']):>10}{bucket['msgs']:>7}")

    print("\n按模型（输出 token）:")
    for model, out in sorted(data["models"].items(), key=lambda kv: -kv[1])[:6]:
        print(f"  {model:<42}{fmt(out):>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
