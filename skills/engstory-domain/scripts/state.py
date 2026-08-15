#!/usr/bin/env python3
"""state.py — 英语故事学习批次状态（纯标准库）

一个学习循环的进度保存在单份 JSON 状态文件中，供工具层做顺序闸门：
  - select_targets 之后进入 TARGETS_SELECTED
  - commit_story 审计通过并保存后进入 WAITING_FEEDBACK
  - apply_feedback 后，若存在待确认发现词则进入 WAITING_WORD_CONFIRMATION，否则回到 IDLE
  - write_learning_words(source=story-discovery) 要求状态为 WAITING_WORD_CONFIRMATION 且词在待确认列表

默认路径取学习库同目录的 state.json，可用 --state 或环境变量 ENGSTORY_STATE 覆盖。
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def default_state(vocab_path: Path) -> Path:
    return Path(os.environ.get("ENGSTORY_STATE", str(vocab_path.parent / "state.json")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_batch() -> dict:
    return {
        "batch_id": None,
        "state": "IDLE",
        "targets": [],
        "story_path": None,
        "audit": None,
        "discovered_words": [],
        "created_at": None,
        "updated_at": None,
    }


def load_state(path: Path) -> dict:
    if not path.exists():
        return empty_batch()
    try:
        d = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: 状态文件损坏（{e}）：{path}")
    base = empty_batch()
    if not isinstance(d, dict):
        sys.exit(f"ERROR: 状态文件格式不正确：{path}")
    for k, v in d.items():
        if k in base:
            base[k] = v
    return base


def save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def new_batch_id() -> str:
    return datetime.now(timezone.utc).strftime("b%Y%m%dT%H%M%S%f")
