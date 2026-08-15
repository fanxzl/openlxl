#!/usr/bin/env python3
"""range_lib.py — 范围词汇库与允许词集合（纯标准库）

被 vocab_distill.py（准备故事词汇包）和 story_audit.py（故事审计）共同引用。
职责：
  1. 读取范围词汇库 range_vocab.json（词元 → {gloss, forms?}）。
  2. 内置基础功能词白名单，避免语法词被误判为超纲。
  3. 给定目标词、范围词、功能词、专名，生成允许词元集合与允许词形集合。
  4. 判断一个表面词是否落在允许集合内（词形归并）。
"""

import json
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from vocab_core import backward_candidates, forward_forms, split_key  # noqa: E402

DEFAULT_RANGE = Path(os.environ.get("ENGSTORY_RANGE", "range_vocab.json"))

# 内置功能词白名单：即使范围库遗漏，这些语法词也不判超纲。
FUNCTION_WORDS = {
    # 冠词
    "a", "an", "the",
    # 代词
    "i", "you", "he", "she", "it", "we", "they",
    "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "mine", "yours", "hers", "ours", "theirs",
    "this", "that", "these", "those",
    "who", "whom", "whose", "which", "what",
    "some", "any", "no", "every", "each", "all", "both", "either", "neither",
    "one", "ones", "other", "others", "another",
    "someone", "something", "somebody", "anyone", "anything", "anybody",
    "nobody", "nothing", "everyone", "everything", "everybody",
    "myself", "yourself", "himself", "herself", "itself", "ourselves", "themselves",
    # be / have / do
    "be", "am", "is", "are", "was", "were", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "done", "doing",
    # 情态
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    # 介词
    "of", "in", "on", "at", "to", "from", "by", "with", "without", "about",
    "for", "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "under", "over", "up", "down", "out", "off", "near",
    "behind", "beside", "inside", "outside", "around", "across", "along", "among",
    # 连词
    "and", "or", "but", "so", "if", "because", "though", "although", "while",
    "when", "where", "why", "how", "than", "as", "then", "until", "unless",
    # 副词常用
    "not", "no", "yes", "very", "too", "also", "just", "only", "even",
    "still", "already", "yet", "again", "now", "here", "there", "always",
    "never", "sometimes", "often", "usually", "really", "quite", "almost",
    "together", "away", "back", "again", "today", "tomorrow", "yesterday",
    # 疑问/感叹与缩略展开产物
    "oh", "ah", "well", "ok", "okay", "hey", "hi", "hello", "goodbye",
    "please", "thanks", "thank",
    # 常见数词
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "hundred", "thousand", "first", "second",
    "third",
    # 感叹词与口语句
    "look", "listen", "wait", "come", "go", "get", "let", "make", "say", "tell",
}


def load_range(path: Path) -> dict:
    """读取范围词汇库，返回 {lemma: entry}。不存在的文件按空范围库处理。"""
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: 范围词库损坏（{e}）：{path}")
    words = d.get("words", d) if isinstance(d, dict) else {}
    if not isinstance(words, dict):
        sys.exit(f"ERROR: 范围词库格式不正确：{path}")
    return words


def allowed_sets(range_words: dict, target_keys=(), proper_names=(), extra_forms=()) -> dict:
    """生成允许词元集合与允许词形集合。

    参数：
      range_words   范围词库 {lemma: {gloss, forms?, ...}}
      target_keys   本轮目标词条 key（单义 base 或多义 base|释义）
      proper_names  允许的专有名词（大小写不敏感，统一小写存储）
      extra_forms   手工补充的额外允许词形
    返回：
      {lemmas: set, forms: set, function_words: set, proper_names: set}
    """
    lemmas = set(FUNCTION_WORDS)
    forms = set()
    for lemma, entry in range_words.items():
        lemma = lemma.lower().strip()
        if not lemma or "|" in lemma:
            # 范围库只接受单义词元；带释义的 key 视为损坏并跳过
            continue
        lemmas.add(lemma)
        extra = []
        if isinstance(entry, dict):
            extra = entry.get("forms", []) or []
        forms.update(forward_forms(lemma, tuple(extra)))

    # 目标词豁免：目标词 base 一律允许（含其常规词形）
    target_bases = {split_key(k)[0].lower() for k in target_keys}
    for base in target_bases:
        lemmas.add(base)
        forms.update(forward_forms(base))

    for pn in proper_names:
        pn = pn.lower().strip()
        if pn:
            lemmas.add(pn)

    for f in extra_forms:
        f = f.lower().strip()
        if f:
            forms.add(f)

    return {
        "lemmas": lemmas,
        "forms": forms,
        "function_words": set(FUNCTION_WORDS),
        "proper_names": {p.lower().strip() for p in proper_names if p and p.strip()},
    }


def lemma_of(tok: str, lemmas: set, forms: set) -> str | None:
    """把表面词归并到允许词元；不在允许集合返回 None。"""
    tok = tok.lower()
    if tok in lemmas or tok in forms:
        return tok
    for cand in backward_candidates(tok):
        if cand in lemmas:
            return cand
    return None


def is_allowed_token(tok: str, lemmas: set, forms: set) -> bool:
    """判断表面词（已去标点、非数字）是否落在允许集合。"""
    if not tok:
        return False
    if re.fullmatch(r"\d+(?:[.,]\d+)*", tok):
        return True
    if len(tok) == 1 and tok in "ai":
        return True
    return lemma_of(tok, lemmas, forms) is not None
