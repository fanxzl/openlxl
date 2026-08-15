#!/usr/bin/env python3
"""add.py — 只做一件事：把新单词放进词库，初始化计数。

新词初始化：picks=0、last_pick=null、uses=0、texts=0、last_use=null。
已存在的词跳过，绝不重置其数据。

用法（任选其一）：
  python add.py --words "abandon 放弃, give up 放弃(短语)"
  python add.py --words "abandon, abrupt, give up"          # 纯词，无释义
  python add.py --file wordlist.txt                          # 词表文件（每行一条）
  echo "abandon 放弃, abrupt" | python add.py                # 管道
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocab_core import (  # noqa: E402
    DEFAULT_VOCAB, gloss_similar, load, new_entry, save, split_key, split_senses,
)


def parse_entry(entry: str):
    """解析一条为 (词, 释义)。词可为短语（give up）。解析不出返回 None。"""
    entry = entry.strip()
    if not entry:
        return None
    # 显式分隔符：tab / 逗号 / " - " / —— / 2+ 空格
    m = re.split(r"\t|,|，| - |——|\s{2,}", entry, maxsplit=1)
    if len(m) > 1:
        w, gloss = m[0].strip().lower(), m[1].strip()
    else:
        # ASCII 词部 + 非 ASCII 释义（"abandon 放弃" 这种单空格分隔）
        mg = re.match(r"^([a-zA-Z][a-zA-Z '\-]*?)\s+([^\x00-\x7F].*)$", entry)
        if mg:
            w, gloss = mg.group(1).strip().lower(), mg.group(2).strip()
        else:
            w, gloss = entry.lower(), ""
    if not re.fullmatch(r"[a-z][a-z '\-]*", w):
        return None
    return w, gloss


def find_entry(words: dict, word: str, sense: str):
    """在词库里找 (word) 或 (word|释义) 的条目。
    返回 (key, 是否相近)。无匹配返回 (None, False)。"""
    # 1) 同单词（无后缀）且意思相近 → 合并
    if word in words:
        g = words[word].get("gloss", "")
        if gloss_similar(g, sense):
            return word, True
    # 2) 同单词的其他意思条目，用相似度判断
    prefix = word + "|"
    for k in words:
        if k.startswith(prefix):
            g = words[k].get("gloss", "")
            if gloss_similar(g, sense):
                return k, True
    return None, False


def main() -> int:
    ap = argparse.ArgumentParser(description="导入新词：放进词库并初始化计数")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--words", help="逗号分隔的词单，每条可带释义：abandon 放弃, give up")
    src.add_argument("--file", help="词表文件（每行一条，支持 # 注释）")
    ap.add_argument("--vocab", default=str(DEFAULT_VOCAB), help="词库 json 路径")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    # 收集条目
    if args.words:
        entries = [s for s in args.words.split(",") if s.strip()]
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            sys.exit(f"ERROR: 文件不存在：{p}")
        entries = [
            ln.strip()
            for ln in p.read_text(encoding="utf-8-sig").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
    elif not sys.stdin.isatty():
        entries = [s for s in sys.stdin.read().split(",") if s.strip()]
    else:
        sys.exit("ERROR: 没有输入。用 --words / --file，或通过管道传入。")

    if not entries:
        sys.exit("ERROR: 没有可导入的词。")

    vp = Path(args.vocab)
    data = load(vp)          # 文件不存在时自动建空词库
    words = data["words"]

    added, bumped, bad = [], [], 0
    for e in entries:
        parsed = parse_entry(e)
        if parsed is None:
            bad += 1
            continue
        w, gloss = parsed
        senses = split_senses(gloss) if gloss else [""]
        for sense in senses:
            key, similar = find_entry(words, w, sense)
            if key is not None:
                # 已存在（同词或意思相近）→ 不导入，"不会频次" +1
                words[key]["不会频次"] = words[key].get("不会频次", 1) + 1
                bumped.append(split_key(key)[0] + (f"({split_key(key)[1]})" if split_key(key)[1] else ""))
                continue
            # 新建词条：多义词拆分带释义后缀；单义词保持纯单词 key
            if w in words:
                new_key = f"{w}|{sense}"
            else:
                new_key = w
            words[new_key] = new_entry(sense)
            added.append(new_key)
    save(vp, data)

    if args.json:
        print(json.dumps({"added": added, "bumped": bumped, "bad": bad,
                          "total": len(words)}, ensure_ascii=False, indent=1))
        return 0

    if added:
        print(f"已放入 {len(added)} 个新词（频次初始为 0，不会频次=1）：{'、'.join(added)}")
    if bumped:
        print(f"已存在，不会频次 +1：{'、'.join(bumped)}")
    if bad:
        print(f"格式不识别，忽略 {bad} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
