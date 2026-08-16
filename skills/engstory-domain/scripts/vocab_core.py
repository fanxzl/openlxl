#!/usr/bin/env python3
"""vocab_core.py — 词库共享核心（纯标准库）

被 pick.py（选词）和 mark.py（标频）共同引用。
只做三件事：词库读写（原子）、词形归并、文本计数。
"""

import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

DEFAULT_VOCAB = Path(os.environ.get(
    "ENGSTORY_VOCAB", r"/workspace/vocab.json"))

# ---------------------------------------------------------------------------
# 不规则动词（base: 过去式, 过去分词）
# ---------------------------------------------------------------------------
IRREG = {
    "arise": ("arose", "arisen"), "awake": ("awoke", "awoken"),
    "be": ("was", "been"), "bear": ("bore", "borne"), "beat": ("beat", "beaten"),
    "become": ("became", "become"), "begin": ("began", "begun"),
    "bend": ("bent", "bent"), "bet": ("bet", "bet"), "bind": ("bound", "bound"),
    "bite": ("bit", "bitten"), "bleed": ("bled", "bled"), "blow": ("blew", "blown"),
    "break": ("broke", "broken"), "bring": ("brought", "brought"),
    "broadcast": ("broadcast", "broadcast"), "build": ("built", "built"),
    "burn": ("burnt", "burnt"), "burst": ("burst", "burst"), "buy": ("bought", "bought"),
    "catch": ("caught", "caught"), "choose": ("chose", "chosen"),
    "cling": ("clung", "clung"), "come": ("came", "come"), "cost": ("cost", "cost"),
    "creep": ("crept", "crept"), "cut": ("cut", "cut"), "deal": ("dealt", "dealt"),
    "dig": ("dug", "dug"), "do": ("did", "done"), "draw": ("drew", "drawn"),
    "dream": ("dreamt", "dreamt"), "drink": ("drank", "drunk"),
    "drive": ("drove", "driven"), "dwell": ("dwelt", "dwelt"),
    "eat": ("ate", "eaten"), "fall": ("fell", "fallen"), "feed": ("fed", "fed"),
    "feel": ("felt", "felt"), "fight": ("fought", "fought"),
    "find": ("found", "found"), "fit": ("fit", "fit"), "flee": ("fled", "fled"),
    "fling": ("flung", "flung"), "fly": ("flew", "flown"),
    "forbid": ("forbade", "forbidden"), "forget": ("forgot", "forgotten"),
    "forgive": ("forgave", "forgiven"), "freeze": ("froze", "frozen"),
    "get": ("got", "gotten"), "give": ("gave", "given"), "go": ("went", "gone"),
    "grind": ("ground", "ground"), "grow": ("grew", "grown"),
    "hang": ("hung", "hung"), "have": ("had", "had"), "hear": ("heard", "heard"),
    "hide": ("hid", "hidden"), "hit": ("hit", "hit"), "hold": ("held", "held"),
    "hurt": ("hurt", "hurt"), "keep": ("kept", "kept"), "kneel": ("knelt", "knelt"),
    "know": ("knew", "known"), "lay": ("laid", "laid"), "lead": ("led", "led"),
    "lean": ("leant", "leant"), "leap": ("leapt", "leapt"), "learn": ("learnt", "learnt"),
    "leave": ("left", "left"), "lend": ("lent", "lent"), "let": ("let", "let"),
    "lie": ("lay", "lain"), "light": ("lit", "lit"), "lose": ("lost", "lost"),
    "make": ("made", "made"), "mean": ("meant", "meant"), "meet": ("met", "met"),
    "overcome": ("overcame", "overcome"), "pay": ("paid", "paid"),
    "put": ("put", "put"), "quit": ("quit", "quit"), "read": ("read", "read"),
    "rid": ("rid", "rid"), "ride": ("rode", "ridden"), "ring": ("rang", "rung"),
    "rise": ("rose", "risen"), "run": ("ran", "run"), "say": ("said", "said"),
    "see": ("saw", "seen"), "seek": ("sought", "sought"), "sell": ("sold", "sold"),
    "send": ("sent", "sent"), "set": ("set", "set"), "shake": ("shook", "shaken"),
    "shine": ("shone", "shone"), "shoot": ("shot", "shot"),
    "show": ("showed", "shown"), "shut": ("shut", "shut"),
    "sing": ("sang", "sung"), "sink": ("sank", "sunk"), "sit": ("sat", "sat"),
    "sleep": ("slept", "slept"), "slide": ("slid", "slid"),
    "smell": ("smelt", "smelt"), "speak": ("spoke", "spoken"),
    "speed": ("sped", "sped"), "spell": ("spelt", "spelt"),
    "spend": ("spent", "spent"), "spill": ("spilt", "spilt"),
    "spin": ("spun", "spun"), "spit": ("spat", "spat"), "split": ("split", "split"),
    "spoil": ("spoilt", "spoilt"), "spread": ("spread", "spread"),
    "spring": ("sprang", "sprung"), "stand": ("stood", "stood"),
    "steal": ("stole", "stolen"), "stick": ("stuck", "stuck"),
    "sting": ("stung", "stung"), "strike": ("struck", "struck"),
    "string": ("strung", "strung"), "swear": ("swore", "sworn"),
    "sweep": ("swept", "swept"), "swim": ("swam", "swum"),
    "swing": ("swung", "swung"), "take": ("took", "taken"),
    "teach": ("taught", "taught"), "tear": ("tore", "torn"),
    "tell": ("told", "told"), "think": ("thought", "thought"),
    "throw": ("threw", "thrown"), "undergo": ("underwent", "undergone"),
    "understand": ("understood", "understood"), "undertake": ("undertook", "undertaken"),
    "upset": ("upset", "upset"), "wake": ("woke", "woken"),
    "wear": ("wore", "worn"), "weep": ("wept", "wept"), "win": ("won", "won"),
    "wind": ("wound", "wound"), "withdraw": ("withdrew", "withdrawn"),
    "withstand": ("withstood", "withstood"), "wring": ("wrung", "wrung"),
    "write": ("wrote", "written"),
}

INFLECTED2BASE = {}
for _b, (_p, _pp) in IRREG.items():
    INFLECTED2BASE[_p] = _b
    INFLECTED2BASE[_pp] = _b
INFLECTED2BASE.update({
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be",
    "been": "be", "being": "be", "has": "have", "does": "do", "goes": "go",
})

CONTRACTIONS = {
    "i'm": "i am", "you're": "you are", "he's": "he is", "she's": "she is",
    "it's": "it is", "we're": "we are", "they're": "they are",
    "i've": "i have", "you've": "you have", "we've": "we have", "they've": "they have",
    "i'll": "i will", "you'll": "you will", "he'll": "he will", "she'll": "she will",
    "we'll": "we will", "they'll": "they will",
    "i'd": "i would", "you'd": "you would", "he'd": "he would", "she'd": "she would",
    "we'd": "we would", "they'd": "they would",
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "can't": "can not", "cannot": "can not", "won't": "will not",
    "isn't": "is not", "aren't": "are not", "wasn't": "was not", "weren't": "were not",
    "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
    "couldn't": "could not", "shouldn't": "should not", "wouldn't": "would not",
    "mustn't": "must not", "needn't": "need not", "ain't": "is not",
    "let's": "let us", "that's": "that is", "there's": "there is", "here's": "here is",
    "what's": "what is", "who's": "who is", "where's": "where is", "how's": "how is",
    "gonna": "going to", "wanna": "want to", "gotta": "got to",
}


# ---------------------------------------------------------------------------
# 词形：正向外推 / 逆向候选
# ---------------------------------------------------------------------------
def _is_cvc(w: str) -> bool:
    return (len(w) <= 5
            and re.match(r"^[^aeiou]*[aeiou][^aeiouwxy]$", w) is not None
            and w[-1] not in "wxy")


def forward_forms(word: str, extra=()) -> set:
    if " " in word:
        return {word} | set(extra)
    f = {word} | set(extra)
    if word in IRREG:
        f.update(IRREG[word])
    if re.search(r"(s|x|z|ch|sh|o)$", word):
        f.add(word + "es")
    if re.search(r"[^aeiou]y$", word):
        f.update({word[:-1] + "ies", word[:-1] + "ied",
                  word[:-1] + "ier", word[:-1] + "iest"})
    f.add(word + "s")
    if word.endswith("fe"):
        f.add(word[:-2] + "ves")
    elif word.endswith("f") and not word.endswith("ff"):
        f.add(word[:-1] + "ves")
    if word.endswith("e"):
        f.update({word + "d", word + "r", word + "st"})
    if _is_cvc(word):
        d = word + word[-1]
        f.update({d + "ed", d + "ing", d + "er", d + "est"})
    f.add(word + "ed")
    if word.endswith("ie"):
        f.add(word[:-2] + "ying")
    elif word.endswith("e") and not word.endswith("ee"):
        f.add(word[:-1] + "ing")
    f.update({word + "ing", word + "er", word + "est"})
    return f


def _undouble(w: str) -> str:
    return w[:-1] if len(w) >= 2 and w[-1] == w[-2] and w[-1] not in "aeiou" else w


def backward_candidates(tok: str) -> set:
    c = {tok}
    if tok in INFLECTED2BASE:
        c.add(INFLECTED2BASE[tok])
    if tok.endswith("ies") and len(tok) > 3:
        c.update({tok[:-3] + "y", tok[:-3] + "e", tok[:-3]})
    if tok.endswith("es") and len(tok) > 3:
        c.update({tok[:-2], tok[:-1]})
    if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 2:
        c.add(tok[:-1])
    if tok.endswith("ves") and len(tok) > 3:
        c.update({tok[:-3] + "f", tok[:-3] + "fe"})
    if tok.endswith("ied") and len(tok) > 3:
        c.add(tok[:-3] + "y")
    if tok.endswith("ed") and len(tok) > 2:
        b = tok[:-2]
        c.update({b, tok[:-1], _undouble(b)})
    if tok.endswith("ying") and len(tok) > 4:
        c.add(tok[:-4] + "ie")
    if tok.endswith("ing") and len(tok) > 4:
        b = tok[:-3]
        c.update({b, b + "e", _undouble(b)})
    for suf, ml in (("iest", 5), ("ier", 4), ("est", 4), ("er", 3)):
        if tok.endswith(suf) and len(tok) > ml:
            b = tok[:-len(suf)]
            c.update({b, b + "e", b + "y", _undouble(b)})
    return c


# ---------------------------------------------------------------------------
# 词库读写（原子）
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 多义词拆分支持
# ---------------------------------------------------------------------------
_SENSE_SPLIT_RE = re.compile(r"[\s,，、;；/]+")


def split_senses(gloss: str) -> list:
    """把一个释义串切成多个意思：按 空格/逗号/顿号/分号/斜杠 切。"""
    return [p.strip() for p in _SENSE_SPLIT_RE.split(gloss) if p.strip()]


_STOP_CHARS = set("的了地在和与及或等啊呀呢吗")


def _core_chars(s: str) -> set:
    """提取释义里的核心汉字（去掉助词）。"""
    return {c for c in s if "\u4e00" <= c <= "\u9fff" and c not in _STOP_CHARS}


def gloss_similar(a: str, b: str, threshold: float = 0.5) -> bool:
    """两个释义是否相近：核心汉字交集占较小一方的比例 >= threshold。"""
    if not a or not b:
        return a == b
    ca, cb = _core_chars(a), _core_chars(b)
    if not ca or not cb:
        return False
    return len(ca & cb) / min(len(ca), len(cb)) >= threshold


def split_key(key: str) -> tuple:
    """把词条 key 拆成 (单词, 释义)。单义词 key 无分隔符。"""
    if "|" in key:
        w, _, g = key.partition("|")
        return w, g
    return key, ""


def memory_score(entry: dict, now=None) -> float:
    """FSRS 遗忘分：0~100+，越高越该练（越接近遗忘）。

    新卡（无反馈记录）给默认分 30：低于长期遗忘的「不会」词（那些会爬过 30 自动回炉）、
    高于刚复习的「会」词（0~10）——新词稳定优先，但真正忘了的词能插队。
    有反馈的卡：R = py-fsrs 遗忘曲线算出的可提取性(0~1)，
    遗忘分 = (1 - R) * 100 —— 纯遗忘时间驱动，与原版 Anki 的
    「记忆保持率」1:1 对照（难度不直接参与；难词经更小的稳定性间接更快到期）。
    记忆参数平铺在词条上：state/step/stability/difficulty/due/last_review/card_id。
    """
    if now is None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
    if "fsrs" in entry:
        f = entry["fsrs"]                      # 兼容旧嵌套格式
    else:
        f = {k: entry.get(k) for k in (
            "card_id", "state", "step", "stability",
            "difficulty", "due", "last_review",
        )}
    if not f or not f.get("last_review"):
        return 30.0
    try:
        from fsrs import Card, Scheduler
        card = Card.from_dict(f)
        sched = Scheduler()
        r = sched.get_card_retrievability(card, now)
        return round((1.0 - r) * 100.0, 1)
    except Exception:
        return 30.0


def parse_due(entry: dict, now=None):
    """从词条平铺字段读 due（ISO 字符串）→ aware datetime；缺失/损坏返回 None。

    naive 时间一律按 UTC 处理（与存储侧 now_iso 保持一致），避免 ago/相减崩溃。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    raw = entry.get("due") if isinstance(entry, dict) else None
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def fmt_interval(td) -> str:
    """把 timedelta 转成自然语言（禁止露出 0.0 天这类 FSRS 内部数字）。

    规则：<1 分钟 → 即将到期；<60 分钟 → 约 X 分钟后；<24 小时 → 约 X 小时后；
    <48 小时 → 明天；否则 N 天后。负数一律视为已逾期。
    """
    if td is None:
        return "很快"
    total_min = td.total_seconds() / 60.0
    if total_min <= 0:
        return "已逾期"
    if total_min < 1:
        return "即将到期"
    if total_min < 60:
        return f"约 {int(total_min)} 分钟后"
    total_h = total_min / 60.0
    if total_h < 24:
        return f"约 {int(total_h)} 小时后"
    total_d = total_h / 24.0
    if total_d < 2:
        return "明天"
    return f"{round(total_d)} 天后"


def new_entry(gloss: str = "") -> dict:
    """一个词的完整字段，包含统计字段与 FSRS 新卡参数。"""
    # 与 py-fsrs Card() 的新卡结构保持一致；card_id 用微秒级时间生成，
    # 避免批量导入时多个词条在同一毫秒创建而发生碰撞。
    now = datetime.now(timezone.utc)
    return {
        "gloss": gloss,
        "picks": 0,          # 被检索（选中）过多少次
        "last_pick": None,   # 上次被检索的时间
        "uses": 0,           # 在多少篇文本里被用到过（每篇只记一次，不按出现次数累加）
        "texts": 0,          # 在多少篇不同文本里出现过
        "last_use": None,    # 上次实际被用到的时间
        "forms": [],         # 额外变形（手工补充）
        "不会频次": 1,       # 导入时累计：词被重复导入一次 +1（仅 add.py 生效）
        "card_id": int(now.timestamp() * 1_000_000),
        "state": 1,          # FSRS State.Learning
        "step": 0,
        "stability": None,
        "difficulty": None,
        "due": now.isoformat(),
        "last_review": None,
        "forget_score": 30.0,
    }


def load(vocab_path: Path) -> dict:
    if not vocab_path.exists():
        return {"meta": {"marked": {}}, "words": {}}
    try:
        d = json.loads(vocab_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: 词库文件损坏（{e}）：{vocab_path}")
    d.setdefault("meta", {})
    d["meta"].setdefault("marked", {})   # 已标记文本的 sha1 → 时间（防重复计数）
    d.setdefault("words", {})
    for w, e in d["words"].items():
        for k, v in new_entry().items():
            e.setdefault(k, v)
    return d


def text_fingerprint(text: str) -> str:
    """文本指纹：按归一化后的词序列算 sha1，忽略排版/标记差异。"""
    _, toks = tokenize(text)
    return hashlib.sha1(" ".join(toks).encode("utf-8")).hexdigest()


def save(vocab_path: Path, data: dict) -> None:
    vocab_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = vocab_path.with_suffix(vocab_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, vocab_path)


# ---------------------------------------------------------------------------
# 文本 → 词计数
# ---------------------------------------------------------------------------
def tokenize(raw: str):
    """返回 (归一化小写文本, tokens)。剥离 markdown 强调标记。"""
    t = re.sub(r"[*_~`]", "", raw).replace("\u2019", "'").replace("\u2018", "'")
    low = t.lower()
    for c, e in sorted(CONTRACTIONS.items(), key=lambda kv: -len(kv[0])):
        low = re.sub(rf"\b{re.escape(c)}\b", e, low)
    toks = re.findall(r"[a-z]+(?:[-'][a-z]+)?", low)
    out = []
    for tk in toks:
        out.append(tk)
        if "-" in tk:
            out.extend(tk.split("-"))
    return low, out


def count_words(text: str, words: dict) -> Counter:
    """统计每个英文表面词在 text 中出现的次数（含变形与短语）。

    返回值按英文 base word 计数，而不是按多义词内部 key 计数。
    例如 sharp、sharp|尖锐的、sharp|急转的统一先得到 sharp 的出现次数；
    具体应记入哪个独立释义，由 mark.py 根据本轮传入的精确 key 分配。
    """
    low, toks = tokenize(text)
    counts: Counter = Counter()

    # 将多义词条按英文 base 合并，仅用于识别词形；所有独立词条的数据仍分开保存。
    bases = {}
    for key, entry in words.items():
        base, _ = split_key(key)
        info = bases.setdefault(base, {"forms": set()})
        info["forms"].update(entry.get("forms", []))

    singles = {w: e for w, e in bases.items() if " " not in w}
    phrases = {w: e for w, e in bases.items() if " " in w}

    index = {}
    for w, e in singles.items():
        for f in forward_forms(w, e.get("forms", [])):
            index.setdefault(f, w)

    for tok, n in Counter(toks).items():
        w = index.get(tok)
        if w is None:
            for cand in backward_candidates(tok):
                if cand in singles:
                    w = cand
                    break
        if w:
            counts[w] += n

    for p, e in phrases.items():
        slots = []
        for w in p.split():
            alts = sorted(forward_forms(w, e.get("forms", [])), key=len, reverse=True)
            slots.append("(?:" + "|".join(re.escape(a) for a in alts) + ")")
        n = len(re.findall(r"\b" + r"\s+".join(slots) + r"\b", low))
        if n:
            counts[p] += n
    return counts


# ---------------------------------------------------------------------------
# 时间展示
# ---------------------------------------------------------------------------
def ago(ts: str | None) -> str:
    """ISO 时间 → 「3天前」这类人读间隔。"""
    if not ts:
        return "从未"
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return "未知"
    sec = (datetime.now() - dt).total_seconds()
    if sec < 60:
        return "刚刚"
    if sec < 3600:
        return f"{int(sec // 60)}分钟前"
    if sec < 86400:
        return f"{int(sec // 3600)}小时前"
    d = int(sec // 86400)
    return f"{d}天前" if d < 30 else f"{d // 30}个月前"
