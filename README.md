# openlxl — English Vocabulary Story Learning Agent

[English](README.md) · [简体中文](README.zh-CN.md)

An English vocabulary learning mode based on FSRS spaced repetition: pick target words from your learning vocabulary → write an English story with range-restricted words → audit → record usage → wait for your "know / don't know" feedback → update memory state. New words are only written into the vocabulary after you explicitly confirm them.

> **Memory scheduling references Anki**: the spaced-repetition scheduling in this project uses the same open-source [FSRS](https://github.com/open-spaced-repetition/fsrs4anki) algorithm that [Anki](https://apps.ankiweb.net/) uses, implemented via [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs). Selection priority, forget scores and review intervals are computed consistently with the Anki ecosystem.

This repository is an **agent preset** for [DeepSeek Harness (DSH)](https://github.com/deepseek-ai/dsh), and can also be used standalone as a Python CLI.

> See [CHANGELOG.md](CHANGELOG.md) · License [MIT](LICENSE)

## Features

- **FSRS memory scheduling**: built-in [py-fsrs 6.3.1](https://github.com/open-spaced-repetition/py-fsrs) (the spaced-repetition algorithm used by Anki); every word keeps its own `difficulty / stability / due date`.
- **Forget-score ranking**: at pick time the current forget score (`(1 - retrievability) × 100`) is computed live — words about to be forgotten float to the top, new cards default to 30, and long-forgotten "don't know" words automatically cut back in line.
- **Range-restricted story writing**: ordinary words in a story must fall within the range vocabulary + built-in function words + explicitly allowed proper nouns; target words are exempt and must be bolded.
- **Strict audit**: all targets present / ordinary words in range / 180–400 words / English only; a story is committed only after the audit passes.
- **Strict batch state machine**: `TARGETS_SELECTED → WAITING_FEEDBACK → WAITING_WORD_CONFIRMATION → IDLE` — no memory update without user feedback, no new words without user confirmation.
- **Morphological lemmatization**: `sought → seek`, `stood → stand`; polysemous words are tracked as independent entries (`blue|蓝色`, `blue|忧伤`).
- **Fingerprint dedup**: re-marking the same text is skipped automatically to prevent inflated usage counts.
- **Dual usage**: DSH agent preset (conversational full loop) + standalone Python CLI (pure stdlib, Python ≥ 3.10).

## Directory Structure

```
openlxl/
├── agent.cordis.yml              # DSH agent preset composition (persona + tools + skills)
├── preset.yml                    # preset metadata
├── CHANGELOG.md                  # version changelog
├── LICENSE                       # MIT license
├── plugins/
│   └── engstory-tools.mjs        # 6 deterministic tools (registered to the DSH agent)
├── skills/
│   └── engstory-domain/
│       ├── SKILL.md              # domain rules + fixed reply templates
│       ├── 检索/SKILL.md         # sub-skill: pick targets (CLI reference)
│       ├── 写故事/SKILL.md       # sub-skill: story loop (CLI reference)
│       ├── 更定频率/SKILL.md     # sub-skill: mark usage (CLI reference)
│       ├── 反馈/SKILL.md         # sub-skill: feedback (CLI reference)
│       ├── 写入词汇/SKILL.md     # sub-skill: write new words (CLI reference)
│       └── scripts/              # 9 Python scripts (pure stdlib)
│           ├── vocab_core.py     #   vocab IO / lemmatization / FSRS forget score
│           ├── pick.py           #   pick targets
│           ├── mark.py           #   mark usage statistics
│           ├── feedback.py       #   apply feedback (updates FSRS)
│           ├── add.py            #   write new words
│           ├── vocab_distill.py  #   build the allowed vocabulary package
│           ├── story_audit.py    #   story audit
│           ├── range_lib.py      #   range vocabulary / function-word whitelist
│           └── state.py          #   batch state machine
├── vendor/                       # vendored dependencies (MIT)
│   ├── fsrs/                     #   py-fsrs 6.3.1 (with its LICENSE)
│   └── typing_extensions.py      #   4.16.0
└── examples/
    ├── vocab.sample.json         # sample learning vocabulary
    └── range.sample.json         # sample range vocabulary
```

## Quick Start

### As a DSH agent preset

Prerequisites: [DeepSeek Harness (DSH)](https://github.com/deepseek-ai/dsh) and Python ≥ 3.10.

1. Clone this repository into DSH's agent presets directory (one directory per preset; the `openlxl` directory name must be kept):

   ```powershell
   # Windows
   git clone https://github.com/fanxzl/openlxl.git
   Copy-Item -Recurse .\openlxl "$env:USERPROFILE\.dsh\.agent-presets\openlxl"
   ```

   ```bash
   # Linux / macOS
   git clone https://github.com/fanxzl/openlxl.git
   cp -r openlxl ~/.dsh/.agent-presets/openlxl
   ```

2. Start DSH and create a new session with the `openlxl` preset (the agent automatically gets the 6 tools + domain skills).

3. Prepare two vocabularies (paths are up to you; pass them to the tools or via environment variables):

   | Vocabulary | Default path (env var override) | Purpose |
   |---|---|---|
   | FSRS learning vocabulary | `/workspace/vocab.json` (`ENGSTORY_VOCAB`) | words to learn: target selection / usage stats / memory feedback |
   | Range vocabulary | `./range_vocab.json` (`ENGSTORY_RANGE`) | restricts the ordinary words allowed in stories |

4. Tell the agent "写故事" (write a story) and it runs the full loop: pick → write → audit → mark → wait for your "know/don't know" → update memory.

### As a Python CLI

Requirements: Python ≥ 3.10 (no third-party runtime dependencies; FSRS is vendored).

```bash
cd skills/engstory-domain
V="<your learning vocab path>"; R="<your range vocab path>"

# 1. Write new words (only after user confirmation)
python scripts/add.py --words "abandon 放弃, coffin 棺材" --vocab "$V"

# 2. Pick 7 target words
python scripts/pick.py --vocab "$V"

# 3. Build the allowed vocabulary package (before writing a story)
python scripts/vocab_distill.py --targets "abandon,coffin" --range "$R" --vocab "$V"

# 4. Audit a story
python scripts/story_audit.py --text "<story text>" --targets "abandon,coffin" --range "$R"

# 5. Mark usage
python scripts/mark.py --text "<story text>" --words "abandon,coffin" --vocab "$V"

# 6. Apply feedback (after the user reports know/don't know)
python scripts/feedback.py --words "abandon 会, coffin 不会" --vocab "$V"
```

All scripts support `--json` output for programmatic use.

## Workflow & State Machine

```
Story loop (strict order):
  ① select_targets      pick 7 target words from the learning vocabulary   → TARGETS_SELECTED
  ② prepare_story_vocab build the allowed vocabulary package
  ③ write a 180–400 word English-only story (target words bolded)
  ④ audit_story         commit only if the audit passes; rewrite at most twice
  ⑤ commit_story        save story + mark usage + open feedback phase      → WAITING_FEEDBACK
  ⑥ apply_feedback      update FSRS only after the user reports            → WAITING_WORD_CONFIRMATION / IDLE
  ⑦ write_learning_words add out-of-range discovered words only after the user confirms
```

| Tool | Script | Action | When |
|---|---|---|---|
| `engstory_select_targets` | pick.py | pick targets, open a batch | start of each round |
| `engstory_prepare_story_vocab` | vocab_distill.py | build the allowed vocabulary package | before writing |
| `engstory_audit_story` | story_audit.py | read-only audit | after writing |
| `engstory_commit_story` | story_audit.py + mark.py | save only if audit passes + mark usage | after audit passes |
| `engstory_apply_feedback` | feedback.py | update FSRS memory state | after user reports |
| `engstory_write_learning_words` | add.py | write new words | after explicit confirmation |

## Data Files

### Learning vocabulary (JSON)

```json
{
  "meta": { "marked": { "<text fingerprint sha1>": "2026-08-15T20:00:00+08:00" } },
  "words": {
    "crypt": {
      "gloss": "地下室",
      "picks": 3, "last_pick": "2026-07-10T09:00:00+08:00",
      "uses": 1, "texts": 1, "last_use": "2026-07-15T20:00:00+08:00",
      "forms": [], "不会频次": 2,
      "card_id": 10001,
      "state": 3, "step": 0,
      "stability": 0.8, "difficulty": 6.3,
      "due": "2026-07-20T09:00:00+00:00",
      "last_review": "2026-07-15T09:00:00+00:00",
      "forget_score": 62.5
    }
  }
}
```

Field reference:

| Field | Meaning | Updated by |
|---|---|---|
| `picks` / `last_pick` | times picked / last pick time | pick.py |
| `uses` / `texts` / `last_use` | usage count / number of texts / last use | mark.py |
| `不会频次` | repeated-import count | add.py |
| `state`/`step`/`stability`/`difficulty`/`due`/`last_review`/`card_id` | FSRS card parameters | feedback.py (computed by py-fsrs) |
| `forget_score` | cached forget score (refreshed at pick/feedback time) | pick.py / feedback.py |

Polysemous words are split into independent entries by `word|gloss` (e.g. `blue|蓝色`, `blue|忧伤`), each with its own counters and memory state.

### Range vocabulary (JSON)

```json
{
  "words": {
    "castle":   { "gloss": "城堡" },
    "walk":     { "gloss": "走", "forms": ["walked", "walking"] }
  }
}
```

### Batch state file

Defaults to `state.json` beside the learning vocabulary (`ENGSTORY_STATE` overridable); stories default to `stories/` beside the vocabulary.

## FSRS Notes

- Memory state is computed by [py-fsrs 6.3.1](https://github.com/open-spaced-repetition/py-fsrs) (MIT), the same algorithm family as Anki's FSRS.
- Forget score = `(1 - retrievability) × 100`, 0–100+, **higher means closer to forgetting and more due for practice**:
  - unreviewed new cards default to 30;
  - cards reviewed as "know" score 0–10 and gradually rise as their interval lapses;
  - cards reviewed as "don't know" climb past 30 and automatically cut back in line.
- Marking usage (`uses/texts`) only affects tie-breaking in ranking; it does **not** enter the FSRS formula directly — scheduling is driven only by feedback and elapsed time.
- The dependency directory can be pointed at an externally installed fsrs package via `ENGSTORY_FSRS` (e.g. after `pip install fsrs`, point it at its site-packages directory); the default is the bundled `vendor/`.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `ENGSTORY_VOCAB` | `/workspace/vocab.json` | FSRS learning vocabulary path |
| `ENGSTORY_RANGE` | `./range_vocab.json` | range vocabulary path |
| `ENGSTORY_STATE` | `state.json` beside the vocabulary | batch state file |
| `ENGSTORY_FSRS` | bundled `vendor/` | fsrs dependency directory |

## License

- This repository: MIT (see [LICENSE](LICENSE)).
- Vendored dependencies: [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) (MIT, see `vendor/fsrs/LICENSE`), [typing-extensions](https://github.com/python/typing_extensions) (PSF-2.0 / Apache-2.0).
- Credits: memory scheduling references [Anki](https://apps.ankiweb.net/)'s open-source [FSRS spaced-repetition algorithm](https://github.com/open-spaced-repetition/fsrs4anki).
