#!/usr/bin/env python3
"""pick.py — 只做一件事：从词库里选出 N 个词，返回给 LLM。

排序依据（Anki 同款四队列，到期驱动，越靠前越该练）：
  1. 学习中/重学中的词（state=1/3 且反馈过）——按到期时间升序，最先复习
  2. 已逾期的复习词（state=2 且 due<=now）——按到期时间升序，最逾期优先
  3. 没反馈过的新词——默认遗忘分 30，按使用/检索统计兜底
  4. 未到期的复习词（state=2 且 due>now）——按到期时间升序补位

「不会」的词反馈后进入学习/重学队列、到期时间很近，下一轮（无论隔多久
调用）必然排到最前——这是与 Anki「很快再见」一致的核心行为。

输出每个词附带：释义、遗忘分、到期文案、检索次数、上次检索时间。
写回词库：被选中的词 picks+1、last_pick=现在。

用法：
  python pick.py                # 选 7 个（默认）
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
    str(Path(__file__).resolve().parents[3] / "fsrs_pkg"),      # 旧布局 fsrs_pkg/
):
    if _fsrs_cand and Path(_fsrs_cand).is_dir():
        sys.path.insert(0, _fsrs_cand)
        break
from vocab_core import (  # noqa: E402
    DEFAULT_VOCAB, ago, fmt_interval, load, memory_score, now_iso,
    parse_due, save, split_key,
)
from fsrs import State  # noqa: E402

# 四队列编码：数值越小越靠前
Q_LEARNING = 1   # 学习中/重学中（已反馈）
Q_OVERDUE = 2    # 已逾期的复习词
Q_NEW = 3        # 没反馈过的新词
Q_FUTURE = 4     # 未到期的复习词


def queue_of(entry: dict, now) -> int:
    """按词条当前状态归入四队列之一。"""
    last_review = entry.get("last_review")
    state = entry.get("state")
    if last_review and state in (State.Learning.value, State.Relearning.value):
        return Q_LEARNING
    if last_review and state == State.Review.value:
        due = parse_due(entry, now)
        if due is not None and due <= now:
            return Q_OVERDUE
        return Q_FUTURE
    # 没反馈过（last_review 空）→ 新词；状态残缺也按新词处理
    return Q_NEW


def pick(data: dict, n: int, now=None) -> list:
    """按四队列到期驱动取前 n 个词。返回 [(word, entry, score), ...]
    同时把每个词条的最新遗忘分写回 e['forget_score']（常驻参数）。"""
    if now is None:
        now = datetime.now(timezone.utc)
    pool = []
    for w, e in data["words"].items():
        score = memory_score(e, now)          # 实时算遗忘分
        e["forget_score"] = score             # 常驻写回词条
        q = queue_of(e, now)
        due = parse_due(e, now)
        due_ts = due.timestamp() if due is not None else float("inf")
        pool.append((w, e, score, q, due_ts))
    pool.sort(key=lambda we: (
        we[3],                                # 队列：学习中 → 逾期 → 新词 → 未来到期
        we[4],                                # 同队列按到期时间升序
        -we[2],                               # 同到期：遗忘分高的优先（新词全 30 平）
        we[1].get("uses", 0),                 # 同分：用得少的优先
        we[1].get("last_pick") or "",         # 同分：久未检索的优先
        we[1].get("picks", 0),                # 同分：检索少的优先
        we[0],                                # 字母序兜底
    ))
    return [(w, e, s) for w, e, s, _q, _d in pool[:n]]


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
        due = parse_due(e)
        if e.get("last_review"):
            due_in = fmt_interval(due - datetime.now(timezone.utc)) if due else "待反馈"
        else:
            due_in = "新词"
        rows.append({
            "key": ref,                          # 后续 mark/feedback 必须原样传递
            "word": base,
            "gloss": gloss,
            "score": score,                       # FSRS 遗忘分
            "queue": queue_of(e, datetime.now(timezone.utc)),
            "due_in": due_in,                     # 自然语言到期文案
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

    # 人读输出：词 + 释义 + 词条/遗忘分/到期 + 检索次数 + 上次检索时间
    # 中文字符终端占两格，按显示宽度对齐
    def disp_w(s: str) -> int:
        return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)

    def pad(s: str, target: int) -> str:
        return s + " " * max(0, target - disp_w(s))

    w_word = max(disp_w(r["word"]) for r in rows)
    w_gloss = max(disp_w(r["gloss"]) for r in rows)
    print(f"本次选词 {len(rows)} 个（按到期/遗忘排序，越靠前越该练）：")
    for r in rows:
        print(f"  {pad(r['word'], w_word)}  {pad(r['gloss'], w_gloss)}"
              f"    [词条 {r['key']}]"
              f" [遗忘分 {r['score']}]"
              f" [到期 {r['due_in']}]"
              f" [检索 {r['picks']} 次，上次 {r['last_pick_ago']}"
              f"；已用 {r['uses']} 次 / {r['texts']} 篇]")
    return 0


if __name__ == "__main__":
    sys.exit(main())