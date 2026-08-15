#!/usr/bin/env python3
"""vocab_distill.py — 生成本轮故事词汇包（纯只读）

读取范围词汇库并生成模型写故事时可用的允许词汇范围：
  - 目标词（必须使用，豁免范围约束）
  - 允许普通词元（范围库 + 内置功能词 + 明确专名）
  - 允许词形（词元自动展开 + 范围库手工 forms）

用法：
  python vocab_distill.py --targets "coffin,abrupt" --range <range.json> --proper-names "Alice,Bob"
  python vocab_distill.py --targets "castle,blue|蓝色" --range <range.json> --json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from range_lib import DEFAULT_RANGE, allowed_sets, load_range  # noqa: E402
from state import default_state, load_state  # noqa: E402
from vocab_core import load, split_key  # noqa: E402


def resolve_targets(raw_items: list, vocab_path: Path | None):
    """把 --targets 条目解析成精确内部 key；多义裸英文标为歧义。"""
    resolved, ambiguous, missing = [], [], []
    words = load(vocab_path)["words"] if vocab_path else {}
    for raw in raw_items:
        token = raw.strip().lower()
        if not token:
            continue
        if "|" in token:
            base, gloss = token.split("|", 1)
            candidates = [
                k for k, e in words.items()
                if split_key(k)[0] == base and e.get("gloss", "").lower() == gloss
            ]
        else:
            candidates = [k for k in words if split_key(k)[0] == token]
        if len(candidates) == 1:
            resolved.append(candidates[0])
        elif len(candidates) > 1:
            ambiguous.append(token)
        else:
            # 不在学习库中但用户显式给出，仍作为目标词（带释义）
            resolved.append(token)
    return resolved, ambiguous


def main() -> int:
    ap = argparse.ArgumentParser(description="蒸馏：生成故事允许词汇包")
    ap.add_argument("--targets", help="逗号分隔的目标词条 key（可含英文|释义）")
    ap.add_argument("--range", default=str(DEFAULT_RANGE), help="范围词汇库 json 路径")
    ap.add_argument("--vocab", help="FSRS 学习库 json 路径（用于解析精确 key）")
    ap.add_argument("--proper-names", help="逗号分隔的允许专有名词")
    ap.add_argument("--state", help="批次状态文件路径（默认在学习库旁）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    vocab_path = Path(args.vocab) if args.vocab else None
    raw_targets = [t.strip() for t in (args.targets or "").split(",") if t.strip()]
    resolved, ambiguous = resolve_targets(raw_targets, vocab_path)
    proper_names = [p.strip() for p in (args.proper_names or "").split(",") if p.strip()]
    range_words = load_range(Path(args.range))

    sets = allowed_sets(range_words, resolved, proper_names)
    targets = []
    for key in resolved:
        base, gloss = split_key(key)
        targets.append({"key": key, "word": base, "gloss": gloss})

    result = {
        "targets": targets,
        "allowed_lemmas": sorted(sets["lemmas"]),
        "allowed_forms": sorted(sets["forms"]),
        "function_words_count": len(sets["function_words"]),
        "proper_names": sorted(sets["proper_names"]),
        "range_word_count": len(range_words),
        "target_count": len(targets),
        "ambiguous": ambiguous,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    print(f"目标词 {len(targets)} 个：{'、'.join(t['key'] for t in targets) or '无'}")
    print(f"范围词元 {len(range_words)} 个，允许普通词元 {len(sets['lemmas'])} 个，"
          f"允许词形 {len(sets['forms'])} 个，功能词 {len(sets['function_words'])} 个")
    if proper_names:
        print(f"允许专名：{'、'.join(proper_names)}")
    if ambiguous:
        print("多义词标识不明确：" + "、".join(ambiguous))
    return 0


if __name__ == "__main__":
    sys.exit(main())
