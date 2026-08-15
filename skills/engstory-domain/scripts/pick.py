#!/usr/bin/env python3
"""pick.py — 只做一件事：从词库里选出 N 个词，返回给 LLM。

排序依据（记忆导向，越靠前越该练）：
  1. 实际使用次数少的优先（uses 升序）——用得少的词最缺曝光
  2. 距上次检索越久的优先（last_pick 升序，从未检索排最前）
  3. 被检索次数少的优先（picks 升序）
复习词天然融合在这个排序里：练过但久未再现的词会自动上浮。

输出每个词附带：释义、检索次数、上次检索时间。
写回词库：被选中的词 picks+1、last_pick=现在。

用法：
  python pick.py                # 选 8 个（默认）
  python pick.py -n 8           # 选 8 个
  python pick.py -n 3           # 选 3 个
  python pick.py --json         # JSON 输出
  python pick.py --peek         # 只看不记（不写 picks/last_pick）
"""

import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
for _fsrs_cand in (
    os.environ.get("ENGSTORY_FSRS"),                            # 显式指定 fsrs 依赖目录
    str(Path(__file__).resolve().parents[3] / "vendor"),        # 仓库内置 vendor/
):
    if _fsrs_cand and Path(_fsrs_cand).is_dir():
        sys.path.insert(0, _fsrs_cand)
        break
from vocab_core import (  # noqa: E402
    DEFAULT_VOCAB, ago, load, memory_score, now_iso, save, split_key,
)


def pick(data: dict, n: int, now=None) -> list:
    """按 FSRS 遗忘分取前 n 个词。返回 [(word, entry, score), ...]
    同时把每个词条的最新遗忘分写回 e['forget_score']（常驻参数）。"""
    if now is None:
        now = datetime.now(timezone.utc)
    pool = []
    for w, e in data["words"].items():
        score = memory_score(e, now)          # 实时算遗忘分
        e["forget_score"] = score             # 常驻写回词条
        pool.append((w, e, score))
    pool.sort(key=lambda we: (
        -we[2],                               # 遗忘分高的优先
        we[1].get("uses", 0),                 # 同分：用得少的优先
        we[1].get("last_pick") or "",         # 同分：久未检索的优先
        we[1].get("picks", 0),                # 同分：检索少的优先
        we[0],                                # 字母序兜底
    ))
    return pool[:n]


def main() -> int:
    ap = argparse.ArgumentParser(description="选词：从词库取 N 个最该练的词")
    ap.add_argument("-n", "--count", type=int, default=7, help="取几个词（默认 7）")
    ap.add_argument("--vocab", default=str(DEFAULT_VOCAB), help="词库 json 路径")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--peek", action="store_true", help="只看不记（不更新检索次数与时间）")
    args = ap.parse_args()

    vp = Path(args.vocab)
    data = load(vp)
    if not data["words"]:
        sys.exit(f"ERROR: 词库为空或不存在：{vp}\n请先准备词库（导入词表是另一个技能的事）。")

    chosen = pick(data, args.count)
    ts = now_iso()

    rows = []
    all_words = data["words"]
    for w, e, score in chosen:
        # 多义词对外必须携带「英文|具体释义」作为稳定标识；单义词仍使用英文。
        base, key_gloss = split_key(w)
        gloss = e.get("gloss") or key_gloss
        same_base = [k for k in all_words if split_key(k)[0] == base]
        ref = f"{base}|{gloss}" if len(same_base) > 1 else base
        rows.append({
            "key": ref,                          # 后续 mark/feedback 必须原样传递
            "word": base,
            "gloss": gloss,
            "score": score,                       # FSRS 遗忘分
            "picks": e.get("picks", 0),           # 更新前的检索次数
            "last_pick": e.get("last_pick"),
            "last_pick_ago": ago(e.get("last_pick")),
            "uses": e.get("uses", 0),
            "texts": e.get("texts", 0),
        })

    if not args.peek:
        for w, e, _score in chosen:
            e["picks"] = e.get("picks", 0) + 1
            e["last_pick"] = ts
        save(vp, data)

    if args.json:
        print(json.dumps({"picked_at": ts, "words": rows}, ensure_ascii=False, indent=1))
        return 0

    # 人读输出：词 + 释义 + 检索次数 + 上次检索时间
    # 中文字符终端占两格，按显示宽度对齐
    def disp_w(s: str) -> int:
        return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)

    def pad(s: str, target: int) -> str:
        return s + " " * max(0, target - disp_w(s))

    w_word = max(disp_w(r["word"]) for r in rows)
    w_gloss = max(disp_w(r["gloss"]) for r in rows)
    print(f"本次选词 {len(rows)} 个（按遗忘分排序，越高越该练）：")
    for r in rows:
        print(f"  {pad(r['word'], w_word)}  {pad(r['gloss'], w_gloss)}"
              f"    [词条 {r['key']}]"
              f" [遗忘分 {r['score']}]"
              f" [检索 {r['picks']} 次，上次 {r['last_pick_ago']}"
              f"；已用 {r['uses']} 次 / {r['texts']} 篇]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
