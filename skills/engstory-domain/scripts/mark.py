#!/usr/bin/env python3
"""mark.py — 只做一件事：读一段文本，把用到的词在词库里记一笔。

更新：命中词 uses += 1（同一次调用每词只记一次）、texts += 1、last_use = 现在。
不碰 picks / last_pick（那是 pick.py 的字段）。

三种输入方式（任选其一）：
  python mark.py --text "The **abandon**ed house ..."   # 直接传文本
  python mark.py --file story.md                        # 传文件
  echo "..." | python mark.py                           # 管道 stdin

可选：--words abandon,abrupt  只报告这几个词的命中情况（用于对照本次给的词）
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocab_core import (  # noqa: E402
    DEFAULT_VOCAB, count_words, load, now_iso, save, split_key, text_fingerprint,
)


def entry_ref(key: str, words: dict) -> str:
    """返回稳定的外部词条标识；多义词统一为 base|释义。"""
    base, _ = split_key(key)
    same_base = [k for k in words if split_key(k)[0] == base]
    if len(same_base) > 1:
        return f"{base}|{words[key].get('gloss', '')}"
    return base


def resolve_requested(raw_items: list, words: dict):
    """把 --words 条目解析成精确内部 key；多义裸英文标为歧义。"""
    resolved, missing, ambiguous = [], [], []
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
            key = candidates[0]
            if key not in resolved:
                resolved.append(key)
        elif len(candidates) > 1:
            ambiguous.append(token)
        else:
            missing.append(token)
    return resolved, missing, ambiguous


def record_hit(words: dict, key: str, ts: str) -> None:
    """同一次调用中，精确词条只记一次。"""
    e = words[key]
    e["uses"] = e.get("uses", 0) + 1
    e["texts"] = e.get("texts", 0) + 1
    e["last_use"] = ts


def main() -> int:
    ap = argparse.ArgumentParser(description="标频：扫描文本，更新词库使用次数")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--text", help="直接传入文本")
    src.add_argument("--file", help="文本文件路径")
    ap.add_argument("--words", help="逗号分隔：只对照这些词报告命中/漏用")
    ap.add_argument("--vocab", default=str(DEFAULT_VOCAB), help="词库 json 路径")
    ap.add_argument("--force", action="store_true", help="即使这段文本标记过也再记一次")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.text:
        text = args.text
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            sys.exit(f"ERROR: 文件不存在：{p}")
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        sys.exit("ERROR: 没有输入。用 --text / --file，或通过管道传入文本。")

    if not text.strip():
        sys.exit("ERROR: 输入文本为空。")

    vp = Path(args.vocab)
    data = load(vp)
    if not data["words"]:
        sys.exit(f"ERROR: 词库为空或不存在：{vp}")

    raw_asked = [w.strip() for w in args.words.split(",")] if args.words else []
    asked, unknown_refs, ambiguous_refs = resolve_requested(raw_asked, data["words"])
    if ambiguous_refs:
        sys.exit(
            "ERROR: 多义词必须使用精确词条标识（英文|释义）："
            + "、".join(ambiguous_refs)
        )

    # 同一段文本重复标记会让词频虚高（LLM 重试、手动补跑都可能触发）→ 指纹去重
    fp = text_fingerprint(text)
    seen = data.setdefault("meta", {}).setdefault("marked", {})
    if fp in seen and not args.force:
        prev = seen[fp]
        msg = f"这段文本已在 {prev} 标记过，本次跳过（--force 可强制再记一次）。"
        if args.json:
            print(json.dumps({"skipped": True, "marked_at": prev, "hits": {},
                              "missed": [], "total_words_updated": 0},
                             ensure_ascii=False, indent=1))
        else:
            print(msg)
        return 0

    counts = count_words(text, data["words"])   # base word → 实际出现次数
    ts = now_iso()

    hits, missed = {}, []
    if asked:
        # 每个英文表面词的出现次数，是最多可确认的独立释义数量。
        # 例如本轮有 sharp|尖锐的、sharp|急转的，则 sharp 至少出现 2 次才两条都命中。
        groups = {}
        for key in asked:
            base, _ = split_key(key)
            groups.setdefault(base, []).append(key)
        for base, keys in groups.items():
            available = counts.get(base, 0)
            for idx, key in enumerate(keys):
                if idx < available:
                    record_hit(data["words"], key, ts)
                    # 多义词按独立词条确认一次；不把同一英文的总出现数重复挂给每个释义。
                    hits[key] = 1 if len(keys) > 1 else available
                else:
                    missed.append(key)
    else:
        # 未提供目标 key 时，只自动记录单义词；多义词无法从纯英文文本判断具体意思。
        for base, n in counts.items():
            candidates = [k for k in data["words"] if split_key(k)[0] == base]
            if n > 0 and len(candidates) == 1:
                key = candidates[0]
                record_hit(data["words"], key, ts)
                hits[key] = n

    extra = []
    asked_bases = {split_key(k)[0] for k in asked}
    if asked:
        for base, n in counts.items():
            if base in asked_bases or n <= 0:
                continue
            candidates = [k for k in data["words"] if split_key(k)[0] == base]
            if len(candidates) == 1:
                key = candidates[0]
                record_hit(data["words"], key, ts)
                hits[key] = n
                extra.append(key)

    seen[fp] = ts
    # 目标词与额外单义词都完成后再保存，确保一次原子写入。
    save(vp, data)

    target_hit_count = sum(1 for k in asked if k in hits)
    display_hits = {entry_ref(k, data["words"]): n for k, n in hits.items()}
    display_missed = [entry_ref(k, data["words"]) for k in missed] + unknown_refs

    if args.json:
        print(json.dumps({
            "marked_at": ts,
            "hits": dict(sorted(display_hits.items())),
            "missed": display_missed,
            "total_words_updated": len(hits),
        }, ensure_ascii=False, indent=1))
        return 0

    if asked:
        print(f"命中 {target_hit_count}/{len(asked) + len(unknown_refs)}："
              + ("、".join(f"{entry_ref(k, data['words'])}×{hits[k]}" for k in asked if k in hits)
                 if hits else "无"))
        if display_missed:
            print(f"未用到 {len(display_missed)} 个：{'、'.join(display_missed)}")
        if extra:
            print(f"另外用到词库里的："
                  + "、".join(f"{entry_ref(k, data['words'])}×{hits[k]}" for k in extra))
    else:
        if hits:
            print(f"已记录 {len(hits)} 个词："
                  + "、".join(f"{entry_ref(k, data['words'])}×{n}" for k, n in sorted(hits.items())))
        else:
            print("文本中没有可唯一定位的词库词条。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
