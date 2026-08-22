#!/usr/bin/env python3
"""context.py — 写作上下文组装层（纯标准库）

合并以下来源，组装成模型每次写作可直接使用的有限长度上下文包：
  - style-profile.json  风格（怎么写）
  - plot-outline.json   卷/故事弧级长期方向（往哪走，按当前弧过滤）
  - chapter-ledger.jsonl 不可改变事实 / 人物 / 关系（已发生什么，按当前章过滤）
  - storyline.json      当前状态（接哪，近期摘要/结尾/线索/目标）
  - 目标任务           本轮目标词（必须自然出现）

用法：
  python context.py --vocab <词库> [--targets "crypt,coffin"] [--json]
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from storyline import default_storyline_path, load_storyline  # noqa: E402
from outline import default_outline_path, load_outline, to_context as outline_context  # noqa: E402
from style import default_style_path, empty_profile, to_context as style_context  # noqa: E402
from ledger import default_ledger_path, _facts, _read_lines  # noqa: E402


def _ctx_title(value, limit=1200):
    if value is None:
        return None
    return str(value).strip()[:limit] or None


def _ctx_list(value, limit=12):
    if not isinstance(value, list):
        return []
    return value[:limit]


def build_context(vocab, targets=None, storyline_path=None, outline_path=None,
                  ledger_path=None, style_path=None, chapter=None, arc_id=None) -> dict:
    sl_path = Path(storyline_path) if storyline_path else default_storyline_path(Path(vocab))
    outline_p = Path(outline_path) if outline_path else default_outline_path(Path(vocab))
    ledger_p = Path(ledger_path) if ledger_path else default_ledger_path(Path(vocab))
    style_p = Path(style_path) if style_path else default_style_path(Path(vocab))

    sl = load_storyline(sl_path)
    # 兼容旧版 storyline 缺路径字段
    outline_p = Path(sl.get("plot_outline_path")) if sl.get("plot_outline_path") else outline_p
    ledger_p = Path(sl.get("ledger_path")) if sl.get("ledger_path") else ledger_p
    style_p = Path(sl.get("style_profile_path")) if sl.get("style_profile_path") else style_p

    cur_chapter = chapter or sl.get("current_chapter") or 0
    rec = _read_lines(ledger_p)

    # 风格
    sty = empty_profile()
    if style_p.exists():
        d = json.loads(style_p.read_text(encoding="utf-8-sig"))
        if isinstance(d, dict):
            sty = {**empty_profile(), **d}
    style_ctx = style_context(sty)

    # 总纲
    outline_data = load_outline(outline_p)
    plot_ctx = outline_context(outline_data, arc_id=arc_id, chapter=cur_chapter)

    # 事实与人物（limit 裁剪）
    facts = _facts(rec)
    characters = sl.get("characters") or []
    relationships = sl.get("relationship_state") or []

    # 当前状态
    immediate = {
        "current_chapter": cur_chapter,
        "chapter_goal": sl.get("chapter_goal"),
        "last_summary": sl.get("last_summary"),
        "last_consequence": sl.get("last_consequence"),
        "last_ending": sl.get("last_ending"),
        "recent_recap": _ctx_list(sl.get("recap"), 5),
        "open_threads": _ctx_list(sl.get("open_threads"), 12),
    }

    return {
        "style": style_ctx,
        "plot": plot_ctx,
        "facts": _ctx_list(facts, 12),
        "characters": _ctx_list(characters, 12),
        "relationships": _ctx_list(relationships, 12),
        "immediate": immediate,
        "targets": _ctx_list(targets or []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="写作上下文组装")
    ap.add_argument("--vocab", required=True, help="词库 json 路径")
    ap.add_argument("--targets", help="逗号分隔目标词 key")
    ap.add_argument("--storyline", help="连载状态 json 路径")
    ap.add_argument("--outline", help="总纲 json 路径")
    ap.add_argument("--ledger", help="账本 jsonl 路径")
    ap.add_argument("--style", help="style-profile.json 路径")
    ap.add_argument("--chapter", type=int, help="当前章节号（默认取状态值）")
    ap.add_argument("--arc-id", help="故事弧 id")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    targets = [t.strip() for t in (args.targets or "").split(",") if t.strip()]
    result = build_context(
        args.vocab,
        targets=targets,
        storyline_path=args.storyline,
        outline_path=args.outline,
        ledger_path=args.ledger,
        style_path=args.style,
        chapter=args.chapter,
        arc_id=args.arc_id,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
