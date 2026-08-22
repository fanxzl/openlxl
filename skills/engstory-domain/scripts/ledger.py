#!/usr/bin/env python3
"""ledger.py — 章节事实账本（纯标准库）

每章一条 JSONL 记录，保存结构化事实、人物变化、关系变化、线索增删与后果。
职责：
  - append: 追加一章账本记录
  - get:    读取某章 / 全部账本
  - facts:  汇总当前所有"永久事实"（confirmed 状态）
  - conflict: 检测新提交事实与既有永久事实是否冲突（相同主体不同内容）

默认路径与 storyline.json 同目录：chapter-ledger.jsonl。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def default_ledger_path(vocab_path: Path) -> Path:
    return Path(os.environ.get("ENGSTORY_LEDGER", str(vocab_path.parent / "chapter-ledger.jsonl")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_lines(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _norm_list(value):
    return value if isinstance(value, list) else []


def _facts(records: list, statuses=("confirmed", "candidate")) -> list:
    """汇总指定状态的事实，按首次出现的顺序去重。"""
    seen, result = set(), []
    for rec in records:
        for fact in _norm_list(rec.get("facts_added", [])) + _norm_list(rec.get("facts_confirmed", [])):
            if isinstance(fact, dict):
                text = str(fact.get("text", ""))
                status = str(fact.get("status", "candidate"))
            else:
                text = str(fact)
                status = "candidate"
            if text and status in statuses and text not in seen:
                seen.add(text)
                result.append(text)
    return result


def _normalize_fact(raw, chapter: int, default_status="candidate") -> dict:
    if isinstance(raw, dict):
        text = str(raw.get("text", "")).strip()
        status = str(raw.get("status", default_status)).strip() or "candidate"
    else:
        text = str(raw).strip()
        status = default_status
    return {"text": text, "status": status, "chapter": chapter}


def build_record(chapter, summary="", chapter_goal="", obstacle="", choice="", consequence="",
                 facts_added=(), facts_confirmed=(), character_changes=(), relationship_changes=(),
                 new_threads=(), resolved_threads=(), next_hook="", story_arc="", scene_location="",
                 story_file="", target_words=()):
    record = {
        "chapter": chapter,
        "story_arc": story_arc,
        "scene_location": scene_location,
        "summary": summary,
        "chapter_goal": chapter_goal,
        "obstacle": obstacle,
        "choice": choice,
        "consequence": consequence,
        "facts_added": [_normalize_fact(f, chapter, "candidate") for f in _norm_list(facts_added)],
        "facts_confirmed": [_normalize_fact(f, chapter, "confirmed") for f in _norm_list(facts_confirmed)],
        "character_changes": _norm_list(character_changes),
        "relationship_changes": _norm_list(relationship_changes),
        "new_threads": _norm_list(new_threads),
        "resolved_threads": _norm_list(resolved_threads),
        "next_hook": next_hook,
        "target_words": _norm_list(target_words),
        "story_file": story_file,
        "created_at": now_iso(),
    }
    return record


# 常见否定标志；用于粗略判断"极性"差异
_NEGATORS = {"未", "没", "不", "无", "非", "别", "not", "never", "no", "none", "nothing"}

# 高频功能字/助词：不参与"主体"判定，避免通用字造成跨主题误报
_STOP_CHARS = set("的了吗呢着过在是有和也也都就才到从会能要进来来去往向把被让对")

# 拉丁词/数字单独成词；CJK 抓单字符但剔除停用字与否定字（避免把否定当主体）
_WORD_RE = re.compile(r"[a-z]+|\d+")


def _content_tokens(text: str) -> set:
    """提取"主体"内容词：英文词 + 数字 + CJK 实字符（剔除停用字/否定字）。"""
    text = text.lower()
    toks = set(_WORD_RE.findall(text))
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            if ch in _STOP_CHARS or ch in _NEGATORS:
                continue
            toks.add(ch)
    return toks


def _polarity(text: str) -> int:
    """count 否定标志（单字或英文否定词），用于极性比较。"""
    low = text.lower()
    n = sum(1 for m in _NEGATORS if m in text or m in low)
    return n


def detect_conflict(records: list, new_facts: list) -> list:
    """检测新提交事实与既有 confirmed 事实的潜在冲突（提示级，不自动拦截）。

    判定规则（确定性启发式）：
      1. 文本完全相同 → 视为确认，不冲突；
      2. 两者"主体"内容词无交集 → 不同主题，不判冲突；
      3. 主体内容词有交集，且"否定极性"相反（一个含否定词、一个不含），且措辞不同 → 标记潜在冲突。

    该启发式只做"提示"，真正裁定交由上层 + 模型/用户，避免脆弱的语义 NLU。
    """
    confirmed = _facts(records, statuses=("confirmed",))
    conflicts = []
    for raw in _norm_list(new_facts):
        text = raw.get("text", raw) if isinstance(raw, dict) else raw
        text = str(text).strip()
        if not text:
            continue
        if text in confirmed:
            continue
        new_toks = _content_tokens(text)
        new_pol = _polarity(text)
        for base in confirmed:
            if text == base:
                continue
            base_toks = _content_tokens(base)
            shared = new_toks & base_toks
            if not shared:
                continue
            if (new_pol > 0) != (_polarity(base) > 0):
                conflicts.append({"old": base, "new": text, "shared": sorted(shared)})
                break
    return conflicts


def main() -> int:
    ap = argparse.ArgumentParser(description="章节事实账本")
    ap.add_argument("--action", required=True, choices=["append", "get", "facts", "conflict"])
    ap.add_argument("--vocab", required=True, help="词库 json 路径，用于推导默认账本路径")
    ap.add_argument("--ledger", help="账本 jsonl 路径（默认与词库同目录）")
    # append 专用
    ap.add_argument("--chapter", type=int, help="章节号")
    ap.add_argument("--summary", help="本章摘要")
    ap.add_argument("--chapter-goal", help="本章目标")
    ap.add_argument("--obstacle", help="本章阻力")
    ap.add_argument("--choice", help="主角选择")
    ap.add_argument("--consequence", help="选择后果")
    ap.add_argument("--facts-added", help="JSON 数组：新增事实")
    ap.add_argument("--facts-confirmed", help="JSON 数组：确认事实")
    ap.add_argument("--character-changes", help="JSON 数组：人物变化")
    ap.add_argument("--relationship-changes", help="JSON 数组：关系变化")
    ap.add_argument("--new-threads", help="JSON 数组：新增线索")
    ap.add_argument("--resolved-threads", help="JSON 数组：解决线索 id")
    ap.add_argument("--next-hook", help="下一章钩子")
    ap.add_argument("--story-arc", help="所属故事弧")
    ap.add_argument("--scene-location", help="场景地点")
    ap.add_argument("--story-file", help="正文文件路径")
    ap.add_argument("--target-words", help="JSON 数组：目标词")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    vocab_path = Path(args.vocab)
    lp = Path(args.ledger) if args.ledger else default_ledger_path(vocab_path)
    records = _read_lines(lp)

    if args.action == "append":
        if not args.chapter:
            sys.exit("ERROR: append 必须提供 --chapter")
        record = build_record(
            chapter=args.chapter,
            summary=args.summary or "",
            chapter_goal=args.chapter_goal or "",
            obstacle=args.obstacle or "",
            choice=args.choice or "",
            consequence=args.consequence or "",
            facts_added=json.loads(args.facts_added) if args.facts_added else [],
            facts_confirmed=json.loads(args.facts_confirmed) if args.facts_confirmed else [],
            character_changes=json.loads(args.character_changes) if args.character_changes else [],
            relationship_changes=json.loads(args.relationship_changes) if args.relationship_changes else [],
            new_threads=json.loads(args.new_threads) if args.new_threads else [],
            resolved_threads=json.loads(args.resolved_threads) if args.resolved_threads else [],
            next_hook=args.next_hook or "",
            story_arc=args.story_arc or "",
            scene_location=args.scene_location or "",
            story_file=args.story_file or "",
            target_words=json.loads(args.target_words) if args.target_words else [],
        )
        _append(lp, record)
        if args.json:
            print(json.dumps({"added": True, "chapter": args.chapter, "record": record}, ensure_ascii=False, indent=2))
        else:
            print(f"已记录第 {args.chapter} 章。")
        return 0

    if args.action == "get":
        result = records
    elif args.action == "facts":
        result = _facts(records)
    elif args.action == "conflict":
        result = detect_conflict(records, json.loads(args.facts_added) if args.facts_added else [])
    else:
        sys.exit(f"ERROR: 未知操作 {args.action}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if isinstance(result, list):
            for r in result:
                print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
