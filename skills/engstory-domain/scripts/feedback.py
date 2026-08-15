#!/usr/bin/env python3
"""feedback.py — 词汇掌握反馈：你报词单评级（会/不会），更新词的 FSRS 记忆状态。

用法（任选其一）：
  python feedback.py --words "abandon 会, coffin 不会"
  python feedback.py --words "abandon 不会, dive 会" --json

评级（两档最常用，四档都支持）：
  会 / 会了 / 记住了 / 认识        → Good（记得牢，下次间隔拉长）
  不会 / 忘了 / 不认识             → Again（忘了，难度↑，很快再见）
  勉强 / 模糊                      → Hard（可选：勉强想起）
  很熟 / 熟练                      → Easy（可选：非常熟）

说明：
  - 每个词条独立维护记忆状态（难度/稳定性/下次到期），由 py-fsrs 计算（MIT 开源）。
  - 词库里的词条会自动带上 fsrs 状态；没有的按"新卡"起步（立即到期）。
  - 只更新记忆状态，不碰 picks/uses 那些统计字段。
"""

import argparse
import json
import os
import sys
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
    DEFAULT_VOCAB, load, memory_score, now_iso, save, split_key,
)
from fsrs import Card, Rating, Scheduler  # noqa: E402

RATING_MAP = {
    "会": Rating.Good, "会了": Rating.Good, "记住了": Rating.Good,
    "认识": Rating.Good, "认识它": Rating.Good, "good": Rating.Good,
    "不会": Rating.Again, "忘了": Rating.Again, "不认识": Rating.Again,
    "again": Rating.Again,
    "勉强": Rating.Hard, "模糊": Rating.Hard, "hard": Rating.Hard,
    "很熟": Rating.Easy, "熟练": Rating.Easy, "easy": Rating.Easy,
}


def parse_feedback(text: str) -> list:
    """解析 "abandon 会, coffin 不会" → [(词, Rating), ...]"""
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) < 2:
            continue
        raw = tokens[-1].strip("，。、；;,. ")
        rating = RATING_MAP.get(raw.lower())
        if rating is None:
            continue
        word = " ".join(tokens[:-1]).strip().lower()
        if word:
            out.append((word, rating))
    return out


def feedback_ref(key: str, words: dict) -> str:
    """返回稳定外部标识；同英文有多个释义时统一为 base|释义。"""
    base, _ = split_key(key)
    candidates = [k for k in words if split_key(k)[0] == base]
    if len(candidates) > 1:
        return f"{base}|{words[key].get('gloss', '')}"
    return base


def resolve_feedback_key(token: str, words: dict):
    """把外部标识解析成唯一内部 key；返回 (key, error_type)。"""
    token = token.strip().lower()
    if "|" in token:
        base, gloss = token.split("|", 1)
        candidates = [
            k for k, e in words.items()
            if split_key(k)[0] == base and e.get("gloss", "").lower() == gloss
        ]
    else:
        candidates = [k for k in words if split_key(k)[0] == token]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, "ambiguous"
    return None, "missing"


def main() -> int:
    ap = argparse.ArgumentParser(description="反馈：按用户报的会/不会，更新词条记忆状态")
    ap.add_argument("--words", required=True, help="词单+评级：abandon 会, coffin 不会")
    ap.add_argument("--vocab", default=str(DEFAULT_VOCAB), help="词库 json 路径")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    items = parse_feedback(args.words)
    if not items:
        sys.exit('ERROR: 没解析出 词+评级。格式：--words "abandon 会, coffin 不会"')

    vp = Path(args.vocab)
    data = load(vp)
    words = data["words"]

    sched = Scheduler()
    now = datetime.now(timezone.utc)
    updated, missing, ambiguous = [], [], []

    for word, rating in items:
        key, err = resolve_feedback_key(word, words)
        if err == "missing":
            missing.append(word)
            continue
        if err == "ambiguous":
            ambiguous.append(word)
            continue
        keys = [key]
        for k in keys:
            e = words[k]
            f = e.get("fsrs") or {kk: e.get(kk) for kk in (
                "card_id", "state", "step", "stability",
                "difficulty", "due", "last_review",
            )}
            # 只有关键字段完整时才反序列化；缺失/损坏的旧词条自动按新卡重建。
            try:
                if f.get("card_id") is None or f.get("state") is None or not f.get("due"):
                    raise ValueError("FSRS 参数不完整")
                card = Card.from_dict(f)
            except (KeyError, TypeError, ValueError):
                card = Card()
            new_card, _log = sched.review_card(card, rating, review_datetime=now)
            # 记忆参数平铺记录在词条上，反馈时一并更新
            for kk, vv in new_card.to_dict().items():
                e[kk] = vv
            e.pop("fsrs", None)               # 清理旧嵌套格式
            e["forget_score"] = memory_score(e, now)   # 遗忘分常驻，一并刷新
            days = max(0.0, (new_card.due - now).total_seconds() / 86400)
            updated.append({
                "key": feedback_ref(k, words),
                "rating": rating.name,
                "due_in_days": round(days, 1),
                "difficulty": round(new_card.difficulty, 3),
                "stability": round(new_card.stability, 3),
            })

    save(vp, data)

    if args.json:
        print(json.dumps({
            "updated": updated,
            "missing": missing,
            "ambiguous": ambiguous,
        }, ensure_ascii=False, indent=1))
        return 0

    if updated:
        print(f"已更新 {len(updated)} 个词条的记忆状态：")
        for u in updated:
            print(f"  {u['key']}  [{u['rating']}]  下次约 {u['due_in_days']} 天后  难度 {u['difficulty']}")
    if ambiguous:
        print("多义词标识不明确，请使用 英文|释义：" + "、".join(ambiguous))
    if missing:
        print(f"词库没有，跳过：{'、'.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
