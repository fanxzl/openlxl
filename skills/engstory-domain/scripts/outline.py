#!/usr/bin/env python3
"""outline.py — 分层剧情总纲（纯标准库）

保存整卷/故事弧/主线的结构化方向，用于长篇记忆。
职责：
  - get:    读取整份总纲
  - set:    写入/替换整份总纲（先读后改，通常由上层合成再整体落盘）
  - append: 追加一条故事弧记录
  - arc:    取当前故事弧相关内容（按 id 或按章节）

默认路径与 storyline.json 同目录：plot-outline.json。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def default_outline_path(vocab_path: Path) -> Path:
    return Path(os.environ.get("ENGSTORY_OUTLINE", str(vocab_path.parent / "plot-outline.json")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_outline() -> dict:
    return {
        "title": None,
        "core_thread": None,
        "end_state": None,
        "volumes": [],
        "updated_at": None,
    }


def load_outline(path: Path) -> dict:
    if not path.exists():
        return empty_outline()
    try:
        d = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: 总纲文件损坏（{e}）：{path}")
    base = empty_outline()
    if not isinstance(d, dict):
        sys.exit(f"ERROR: 总纲文件格式不正确：{path}")
    for k, v in d.items():
        if k in base:
            base[k] = v
    if not isinstance(base["volumes"], list):
        base["volumes"] = []
    return base


def save_outline(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def find_arc(data: dict, arc_id: str = None, chapter: int = None) -> dict:
    """按故事弧 id 或章节号定位到 {volume, arc}，返回该弧的完整定义。"""
    for vol in data.get("volumes", []):
        for arc in vol.get("arcs", []):
            if arc_id and arc.get("id") == arc_id:
                return {"volume": vol, "arc": arc}
            if chapter is not None:
                start, end = arc.get("chapter_start"), arc.get("chapter_end")
                if (start is None or chapter >= start) and (end is None or chapter <= end):
                    return {"volume": vol, "arc": arc}
    return None


def to_context(data: dict, arc_id: str = None, chapter: int = None, limit=2000) -> dict:
    """面向模型的精简上下文：核心主线 + 终点 + 目标卷/弧关键事件 + 永久事实 + 禁止项。"""
    result = {
        "title": data.get("title"),
        "core_thread": data.get("core_thread"),
        "end_state": data.get("end_state"),
        "target": None,
        "permanent_facts": data.get("permanent_facts", []),
        "forbidden": data.get("forbidden", []),
    }
    loc = find_arc(data, arc_id, chapter)
    if loc:
        arc = loc["arc"]
        result["target"] = {
            "volume_goal": loc["volume"].get("goal"),
            "arc_id": arc.get("id"),
            "arc_goal": arc.get("goal"),
            "key_events": arc.get("key_events", []),
            "chapter_start": arc.get("chapter_start"),
            "chapter_end": arc.get("chapter_end"),
            "resolved": arc.get("resolved", []),
            "unresolved": arc.get("unresolved", []),
        }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="分层剧情总纲")
    ap.add_argument("--action", required=True, choices=["get", "set", "append", "arc"])
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--outline", help="总纲 json 路径（默认与词库同目录）")
    ap.add_argument("--data", help="完整总纲 JSON（set 用）")
    ap.add_argument("--volume", help="JSON：一个卷对象（append 用）")
    ap.add_argument("--arc-id", help="故事弧 id（arc 用）")
    ap.add_argument("--chapter", type=int, help="章节号（arc 用）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    vocab_path = Path(args.vocab)
    op = Path(args.outline) if args.outline else default_outline_path(vocab_path)

    if args.action == "get":
        result = load_outline(op)
    elif args.action == "set":
        if not args.data:
            sys.exit("ERROR: set 必须提供 --data JSON")
        data = json.loads(args.data)
        data["updated_at"] = now_iso()
        if "permanent_facts" not in data:
            data["permanent_facts"] = []
        if "forbidden" not in data:
            data["forbidden"] = []
        save_outline(op, data)
        result = data
    elif args.action == "append":
        data = load_outline(op)
        if not args.volume:
            sys.exit("ERROR: append 必须提供 --volume JSON")
        vol = json.loads(args.volume)
        vols = data.setdefault("volumes", [])
        # 同 id 卷则替换，否则追加
        replaced = False
        for i, existing in enumerate(vols):
            if existing.get("id") == vol.get("id"):
                vols[i] = vol
                replaced = True
                break
        if not replaced:
            vols.append(vol)
        data["updated_at"] = now_iso()
        save_outline(op, data)
        result = data
    elif args.action == "arc":
        data = load_outline(op)
        result = to_context(data, arc_id=args.arc_id, chapter=args.chapter)
    else:
        sys.exit(f"ERROR: 未知操作 {args.action}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
