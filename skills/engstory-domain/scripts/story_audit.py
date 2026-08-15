#!/usr/bin/env python3
"""story_audit.py — 故事严格审计（纯只读）

检查一篇故事是否满足本轮词汇约束：
  - 目标词是否全部出现（多义词按独立词条计数，同一 base 出现次数 >= 拆分数才算全中）
  - 普通词是否落在允许集合（范围词元 + 内置功能词 + 明确专名 + 目标词豁免）
  - 词形归并（walked → walk）后再判定，避免正常变形被误判超纲
  - 纯英文与字数范围

用法：
  python story_audit.py --file story.md --targets "coffin,abrupt" --range <range.json>
  python story_audit.py --text "..." --targets "castle,blue|蓝色" --range <range.json> --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from range_lib import DEFAULT_RANGE, allowed_sets, is_allowed_token, load_range  # noqa: E402
from vocab_core import backward_candidates, split_key, tokenize  # noqa: E402


def audit_text(text: str, target_keys: list, range_path: Path, proper_names=(), min_words=180, max_words=400) -> dict:
    raw, toks = tokenize(text)
    word_count = len(toks)

    # 目标词命中：按 base 分组，同一 base 出现次数 >= 该 base 的独立词条数才算全中
    groups = {}
    for key in target_keys:
        base, _ = split_key(key)
        groups.setdefault(base, []).append(key)

    target_hits, target_missing = {}, []
    for base, keys in groups.items():
        real = _base_occurrences(raw, toks, base)
        for idx, key in enumerate(keys):
            if idx < real:
                target_hits[key] = 1
            else:
                target_missing.append(key)

    range_words = load_range(range_path)
    sets = allowed_sets(range_words, target_keys, proper_names)
    target_bases = {split_key(k)[0] for k in target_keys}

    out_of_range, seen = [], set()
    for tok in toks:
        if tok in target_bases:
            continue
        if is_allowed_token(tok, sets["lemmas"], sets["forms"]):
            continue
        if tok not in seen:
            seen.add(tok)
            out_of_range.append(tok)

    reasons = []
    if target_missing:
        reasons.append(f"目标词未全部出现：{'、'.join(target_missing)}")
    if out_of_range:
        reasons.append(f"普通词超出允许范围：{'、'.join(out_of_range[:20])}"
                       + (" 等" if len(out_of_range) > 20 else ""))
    if not (min_words <= word_count <= max_words):
        reasons.append(f"字数 {word_count} 不在 {min_words}–{max_words} 范围内")
    if re.search(r"[\u4e00-\u9fff]", text):
        reasons.append("故事包含中文/非英文字符")

    return {
        "pass": not reasons,
        "word_count": word_count,
        "target_hits": target_hits,
        "target_missing": target_missing,
        "out_of_range": out_of_range,
        "reasons": reasons,
    }


def _base_occurrences(low: str, toks: list, base: str) -> int:
    """返回某个 base（词元）在文本中的出现次数，含词形归并。"""
    n = 0
    for tok in toks:
        if tok == base:
            n += 1
            continue
        if base in backward_candidates(tok):
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="审计：检查故事目标词与普通词范围")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="直接传入故事文本")
    src.add_argument("--file", help="故事文件路径")
    ap.add_argument("--targets", required=True, help="逗号分隔的目标词条 key")
    ap.add_argument("--range", default=str(DEFAULT_RANGE), help="范围词汇库 json 路径")
    ap.add_argument("--proper-names", help="逗号分隔的允许专有名词")
    ap.add_argument("--min-words", type=int, default=180)
    ap.add_argument("--max-words", type=int, default=400)
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.text:
        text = args.text
    else:
        p = Path(args.file)
        if not p.exists():
            sys.exit(f"ERROR: 文件不存在：{p}")
        text = p.read_text(encoding="utf-8-sig", errors="replace")

    target_keys = [t.strip().lower() for t in args.targets.split(",") if t.strip()]
    proper_names = [p.strip() for p in (args.proper_names or "").split(",") if p.strip()]

    result = audit_text(text, target_keys, Path(args.range), proper_names,
                        args.min_words, args.max_words)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    if result["pass"]:
        print(f"审计通过：{result['word_count']} 词，目标词全中"
              + (f"（{len(result['target_hits'])} 个）" if result["target_hits"] else ""))
    else:
        print(f"审计失败：{'；'.join(result['reasons'])}")
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
