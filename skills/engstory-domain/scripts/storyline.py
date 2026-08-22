#!/usr/bin/env python3
"""storyline.py — 故事连载状态管理（纯标准库）

管理跨轮次故事连载的主线、风格、角色、未解决线索、章节任务、滚动前情提要和结尾钩子：
  - get: 读取当前连载状态
  - start: 开启新故事线（Chapter 1，写入风格/角色/初始线索/章节目标）
  - advance: 推进章节（Chapter N+1，追加滚动摘要，更新线索与后果）
  - reset: 归档/重置当前故事线

兼容：旧版 storyline.json 缺少新增字段时自动补默认值，不破坏现有连载。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def default_storyline_path(vocab_path: Path) -> Path:
    return Path(os.environ.get("ENGSTORY_STORYLINE", str(vocab_path.parent / "storyline.json")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_storyline() -> dict:
    return {
        "active": False,
        "series_id": None,
        "title": None,
        "premise": None,
        "style_profile": {},
        "characters": [],
        "open_threads": [],
        "relationship_state": [],
        "current_chapter": 0,
        "chapter_goal": None,
        "last_summary": None,
        "last_consequence": None,
        "recap": [],
        "last_ending": None,
        "last_story_file": None,
        "updated_at": None,
    }


def parse_json_value(raw, fallback):
    """把命令行 JSON 字符串解析为对象；空值返回 fallback。"""
    if raw is None or not str(raw).strip():
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: JSON 参数格式错误：{e}")


def bounded_text(value, limit=500):
    """限制文本长度并去空白；空值返回 None。"""
    if value is None:
        return None
    return str(value).strip()[:limit] or None


def normalize_list(value, limit=20):
    if not isinstance(value, list):
        return []
    return value[:limit]


def normalize_relationship(value, limit=20):
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        a = bounded_text(item.get("a"), 80) or "?"
        b = bounded_text(item.get("b"), 80) or "?"
        rel = bounded_text(item.get("state"), 160) or "unknown"
        out.append({"a": a, "b": b, "state": rel})
    return out


def update_threads(current, new_threads=None, resolved_threads=None):
    """先删除已解决线索，再新增未解决线索，按 id 去重，最多 20 条。"""
    threads = normalize_list(current)
    resolved = {str(x) for x in normalize_list(resolved_threads)}
    if resolved:
        threads = [
            t for t in threads
            if isinstance(t, dict) and str(t.get("id", t.get("question", ""))) not in resolved
        ]
    existing = {
        str(t.get("id", t.get("question", "")))
        for t in threads if isinstance(t, dict)
    }
    for item in normalize_list(new_threads):
        if not isinstance(item, dict):
            continue
        item = dict(item)
        item["question"] = bounded_text(item.get("question"), 300) or "未命名线索"
        item["id"] = bounded_text(item.get("id"), 100) or item["question"]
        item["importance"] = bounded_text(item.get("importance"), 40) or "medium"
        item["status"] = "open"
        key = item["id"]
        if key not in existing:
            threads.append(item)
            existing.add(key)
    return threads[-20:]


def load_storyline(path: Path) -> dict:
    if not path.exists():
        return empty_storyline()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: 连载状态文件损坏（{e}）：{path}")
    base = empty_storyline()
    if not isinstance(data, dict):
        sys.exit(f"ERROR: 连载状态文件格式不正确：{path}")
    for k, v in data.items():
        if k in base:
            base[k] = v
    # 兼容旧文件：补齐结构化字段类型
    if not isinstance(base["style_profile"], dict):
        base["style_profile"] = {}
    if not isinstance(base["characters"], list):
        base["characters"] = []
    if not isinstance(base["open_threads"], list):
        base["open_threads"] = []
    if not isinstance(base["relationship_state"], list):
        base["relationship_state"] = []
    if not isinstance(base["recap"], list):
        base["recap"] = []
    return base


def save_storyline(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def start_series(
    path: Path,
    premise: str,
    title: str = None,
    story_file: str = None,
    ending: str = None,
    summary: str = None,
    style_profile=None,
    characters=None,
    open_threads=None,
    relationship_state=None,
    chapter_goal: str = None,
    consequence: str = None,
) -> dict:
    ts = now_iso()
    sid = datetime.now(timezone.utc).strftime("s%Y%m%dT%H%M%S%f")
    recap = []
    if summary and summary.strip():
        recap.append({"chapter": 1, "summary": bounded_text(summary, 400)})
    data = {
        "active": True,
        "series_id": sid,
        "title": bounded_text(title, 150) or "Untitled Series",
        "premise": bounded_text(premise, 500),
        "style_profile": style_profile if isinstance(style_profile, dict) else {},
        "characters": normalize_list(characters, 20),
        "open_threads": normalize_list(open_threads, 20),
        "relationship_state": normalize_relationship(relationship_state, 20),
        "current_chapter": 1,
        "chapter_goal": bounded_text(chapter_goal, 400),
        "last_summary": bounded_text(summary, 400),
        "last_consequence": bounded_text(consequence, 400),
        "recap": recap,
        "last_ending": bounded_text(ending, 500),
        "last_story_file": bounded_text(story_file, 500),
        "updated_at": ts,
    }
    save_storyline(path, data)
    return data


def advance_series(
    path: Path,
    summary: str,
    ending: str = None,
    story_file: str = None,
    title: str = None,
    max_recap: int = 5,
    chapter_goal: str = None,
    consequence: str = None,
    new_threads=None,
    resolved_threads=None,
    relationship_state=None,
) -> dict:
    data = load_storyline(path)
    if not data.get("active"):
        auto_premise = bounded_text(summary, 500) or "连载故事主线"
        auto_title = bounded_text(title, 150) or "未命名连载故事"
        return start_series(
            path,
            premise=auto_premise,
            title=auto_title,
            story_file=story_file,
            ending=ending,
            summary=summary,
            open_threads=new_threads,
            chapter_goal=chapter_goal,
            consequence=consequence,
            relationship_state=relationship_state,
        )

    ts = now_iso()
    next_ch = (data.get("current_chapter") or 0) + 1
    recap = data.get("recap") or []
    if summary and summary.strip():
        recap.append({"chapter": next_ch, "summary": bounded_text(summary, 400)})

    # 滚动摘要保持策略：保留 Chapter 1（源起）+ 最近 (max_recap - 1) 章
    if len(recap) > max_recap:
        first_item = recap[0]
        recent_items = recap[-(max_recap - 1):]
        if first_item not in recent_items and first_item.get("chapter") == 1:
            recap = [first_item] + recent_items
        else:
            recap = recap[-max_recap:]

    data["current_chapter"] = next_ch
    data["recap"] = recap
    data["open_threads"] = update_threads(data.get("open_threads"), new_threads, resolved_threads)
    if relationship_state and isinstance(relationship_state, list):
        data["relationship_state"] = normalize_relationship(relationship_state, 20)
    if ending and ending.strip():
        data["last_ending"] = bounded_text(ending, 500)
    if story_file and story_file.strip():
        data["last_story_file"] = bounded_text(story_file, 500)
    if title and title.strip():
        data["title"] = bounded_text(title, 150)
    if summary and summary.strip():
        data["last_summary"] = bounded_text(summary, 400)
    if chapter_goal and chapter_goal.strip():
        data["chapter_goal"] = bounded_text(chapter_goal, 400)
    if consequence and consequence.strip():
        data["last_consequence"] = bounded_text(consequence, 400)
    data["updated_at"] = ts

    save_storyline(path, data)
    return data


def reset_series(path: Path) -> dict:
    data = empty_storyline()
    save_storyline(path, data)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="连载状态管理：主线、风格、角色、线索、章节任务与前情")
    ap.add_argument("--action", required=True, choices=["get", "start", "advance", "reset"], help="操作类型")
    ap.add_argument("--vocab", required=True, help="词库 json 路径")
    ap.add_argument("--storyline", help="连载状态 json 路径（默认与词库同目录）")
    ap.add_argument("--premise", help="新剧本/世界观核心设定（start 时使用）")
    ap.add_argument("--title", help="故事或系列标题")
    ap.add_argument("--summary", help="本章一句话事件摘要（advance/start 时记录入 recap）")
    ap.add_argument("--ending", help="本章结尾镜头/留给下一章的动作钩子")
    ap.add_argument("--story-file", help="本章保存的 md 文件路径")
    ap.add_argument("--style-profile", help="JSON：风格配置对象")
    ap.add_argument("--characters", help="JSON：角色数组")
    ap.add_argument("--open-threads", help="JSON：初始未解决线索数组")
    ap.add_argument("--relationship-state", help="JSON：人物关系数组")
    ap.add_argument("--chapter-goal", help="本章主角要完成的具体目标")
    ap.add_argument("--consequence", help="本章选择造成的后果")
    ap.add_argument("--new-threads", help="JSON：本章新增线索数组")
    ap.add_argument("--resolved-threads", help="JSON：本章解决的线索 id 数组")
    ap.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = ap.parse_args()

    vocab_path = Path(args.vocab)
    sl_path = Path(args.storyline) if args.storyline else default_storyline_path(vocab_path)

    style_profile = parse_json_value(args.style_profile, {})
    characters = parse_json_value(args.characters, [])
    open_threads = parse_json_value(args.open_threads, [])
    relationship_state = parse_json_value(args.relationship_state, [])
    new_threads = parse_json_value(args.new_threads, [])
    resolved_threads = parse_json_value(args.resolved_threads, [])

    if args.action == "get":
        result = load_storyline(sl_path)
    elif args.action == "start":
        if not args.premise:
            sys.exit("ERROR: start 操作必须提供 --premise（新剧本/设定背景）")
        result = start_series(
            sl_path, premise=args.premise, title=args.title, story_file=args.story_file,
            ending=args.ending, summary=args.summary, style_profile=style_profile,
            characters=characters, open_threads=open_threads,
            relationship_state=relationship_state, chapter_goal=args.chapter_goal,
            consequence=args.consequence,
        )
    elif args.action == "advance":
        result = advance_series(
            sl_path, summary=args.summary or "", ending=args.ending, story_file=args.story_file,
            title=args.title, chapter_goal=args.chapter_goal, consequence=args.consequence,
            new_threads=new_threads, resolved_threads=resolved_threads,
            relationship_state=relationship_state,
        )
    elif args.action == "reset":
        result = reset_series(sl_path)
    else:
        sys.exit(f"ERROR: 未知操作 {args.action}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("active"):
            print(f"连载状态：第 {result.get('current_chapter')} 章 · 《{result.get('title')}》")
            print(f"主线设定：{result.get('premise')}")
            if result.get("chapter_goal"):
                print(f"本章目标：{result.get('chapter_goal')}")
            if result.get("last_consequence"):
                print(f"上章后果：{result.get('last_consequence')}")
            if result.get("last_ending"):
                print(f"上章结尾：{result.get('last_ending')}")
            rec = result.get("recap") or []
            if rec:
                print("前情提要：")
                for r in rec:
                    print(f"  - 第 {r['chapter']} 章：{r['summary']}")
        else:
            print("当前无进行中的故事连载（IDLE）。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
