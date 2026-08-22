#!/usr/bin/env python3
"""style.py — 风格配置（纯标准库）

职责：
  - load:    读取 style-profile.json（缺省返回空）
  - save:    写入确认后的 style-profile.json
  - scaffold: 生成风格提炼的"中间结构骨架"，供模型填充（多片段分析/合并/置信度/未判定项）
  - context: 输出面向模型的精简风格上下文（must_do/avoid/关键维度/置信度）
  - candidate: 从模型候选 JSON 中抽取 must_do/avoid/关键维度并打置信度字段

默认路径：style-profile.json（与词库同目录）。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def default_style_path(vocab_path: Path) -> Path:
    return Path(os.environ.get("ENGSTORY_STYLE", str(vocab_path.parent / "style-profile.json")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_push(value, *keys):
    """从 value 里安全地按路径取出一个值。"""
    cur = value
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def empty_profile() -> dict:
    return {
        "version": 1,
        "source": None,
        "confidence": {},
        "dimensions": {},
        "must_do": [],
        "avoid": [],
        "uncertain": [],
        "updated_at": None,
    }


def scaffold(samples=None, reader_impressions=""):
    """生成风格提炼的中间结构骨架，填充到模型。"""
    samples_list = samples if isinstance(samples, list) else []
    dims = ["pov", "tone", "pace", "sentence_rhythm", "dialogue", "plot_movement", "chapter_endings"]
    return {
        "samples": samples_list,
        "reader_impressions": reader_impressions,
        "dimensions": dims,
        "per_sample_analysis": [
            {"sample_id": s.get("id") if isinstance(s, dict) else s, "undetermined": True}
            for s in samples_list
        ],
        "merge_guidance": "找出至少两个片段中重复出现的特征；单个片段偶发特征不应作为稳定风格。",
        "confidence_scale": {"high": "多个片段一致", "medium": "部分片段支持", "low": "证据不足"},
    }


def extract_profile(candidate: dict) -> dict:
    """从模型候选 JSON 抽取出正式 style-profile，并标记置信度。"""
    profile = empty_profile()
    dims = safe_push(candidate, "dimensions") or {}
    if isinstance(dims, dict):
        profile["dimensions"] = dims
    profile["must_do"] = safe_push(candidate, "must_do") or []
    profile["avoid"] = safe_push(candidate, "avoid") or []
    conf = safe_push(candidate, "confidence") or {}
    if isinstance(conf, dict):
        profile["confidence"] = conf
    profile["uncertain"] = safe_push(candidate, "uncertain") or []
    profile["source"] = safe_push(candidate, "source") or {"type": "llm_extracted"}
    # 保证数组字段
    for field in ("must_do", "avoid", "uncertain"):
        if not isinstance(profile[field], list):
            profile[field] = []
    return profile


def to_context(profile: dict, limit_words=400) -> dict:
    """面向模型的精简风格上下文。"""
    dims = profile.get("dimensions", {})
    bounds = {}
    # 只取对写作最关键的维度
    for key in ("genre", "pov", "tone", "pace", "dialogue", "plot_movement", "chapter_endings", "language"):
        v = dims.get(key)
        if v is not None:
            bounds[key] = v
    conf = profile.get("confidence", {})
    return {
        "dimensions": bounds,
        "must_do": profile.get("must_do", []),
        "avoid": profile.get("avoid", []) if isinstance(profile.get("avoid"), list) else [],
        "confidence": conf,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="风格配置")
    ap.add_argument("--action", required=True, choices=["load", "save", "scaffold", "extract", "context"])
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--style", help="style-profile.json 路径（默认与词库同目录）")
    ap.add_argument("--data", help="JSON：要保存/提取的候选或正式 profile")
    ap.add_argument("--samples", help="JSON 数组：参考片段")
    ap.add_argument("--impressions", help="用户读者感受（自然语言）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    vocab_path = Path(args.vocab)
    sp = Path(args.style) if args.style else default_style_path(vocab_path)

    if args.action == "load":
        result = empty_profile()
        if sp.exists():
            d = json.loads(sp.read_text(encoding="utf-8-sig"))
            if isinstance(d, dict):
                result = {**empty_profile(), **d}
    elif args.action == "save":
        data = json.loads(args.data) if args.data else empty_profile()
        data["updated_at"] = now_iso()
        for field in ("must_do", "avoid", "uncertain"):
            if not isinstance(data.get(field), list):
                data[field] = []
        sp.parent.mkdir(parents=True, exist_ok=True)
        tmp = sp.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, sp)
        result = data
    elif args.action == "scaffold":
        samples = json.loads(args.samples) if args.samples else []
        result = scaffold(samples, args.impressions or "")
    elif args.action == "extract":
        data = json.loads(args.data) if args.data else {}
        result = extract_profile(data)
    elif args.action == "context":
        data = empty_profile()
        if sp.exists():
            d = json.loads(sp.read_text(encoding="utf-8-sig"))
            if isinstance(d, dict):
                data = {**empty_profile(), **d}
        result = to_context(data)
    else:
        sys.exit(f"ERROR: 未知操作 {args.action}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
