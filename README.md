# openlxl — 英语词汇故事学习 Agent

基于 FSRS（间隔重复）算法的英语词汇学习模式：从学习词库选目标词 → 用受限词汇写英文故事 → 审计 → 记使用频率 → 等用户报「会/不会」→ 更新记忆状态。用户明确确认后才写入新词。

> **记忆调度参照自 Anki**：本项目的间隔重复调度采用 [Anki](https://apps.ankiweb.net/) 同款的开源 FSRS 算法（经由 [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) 实现），选词优先级、遗忘分与复习间隔的计算与 Anki 生态一致。

本仓库是 [DeepSeek Harness (DSH)](https://github.com/deepseek-ai/dsh) 的 **agent preset**，也可脱离 DSH 单独作为 Python CLI 使用。

## 特性

- **FSRS 记忆调度**：内置 [py-fsrs 6.3.1](https://github.com/open-spaced-repetition/py-fsrs)（Anki 同款间隔重复算法），每个词独立维护 `难度 / 稳定性 / 下次到期`。
- **遗忘分排序**：选词时按当前遗忘分（`(1 - 可提取性) × 100`）实时排序——快忘的词自动排到最前，新词默认 30 分，长期遗忘的「不会」词能插队回炉。
- **受限词汇写作**：故事中的普通词必须落在「范围词汇库 + 内置功能词 + 明确专名」内，目标词豁免并强制加粗。
- **严格顺序闸门**：批次状态机（`TARGETS_SELECTED → WAITING_FEEDBACK → WAITING_WORD_CONFIRMATION → IDLE`）保证流程不可跳步：没有用户反馈不更新记忆，没有用户确认不写新词。
- **词形归并**：`sought → seek`、`stood → stand`、`blue|蓝色` 多义词独立计数。
- **指纹去重**：同一篇文本重复标记会被跳过，防止词频虚高。

## 目录结构

```
openlxl/
├── agent.cordis.yml              # DSH agent preset 组合（persona + 工具 + 技能）
├── preset.yml                    # preset 元数据
├── plugins/
│   └── engstory-tools.mjs        # 6 个确定性工具（注册给 DSH Agent）
├── skills/
│   └── engstory-domain/
│       ├── SKILL.md              # 领域规则 + 固定输出模板
│       ├── 检索/SKILL.md         # 子技能：选词（CLI 参考）
│       ├── 写故事/SKILL.md       # 子技能：写故事闭环（CLI 参考）
│       ├── 更定频率/SKILL.md     # 子技能：标频（CLI 参考）
│       ├── 反馈/SKILL.md         # 子技能：报词反馈（CLI 参考）
│       ├── 写入词汇/SKILL.md     # 子技能：写新词（CLI 参考）
│       └── scripts/              # 9 个 Python 脚本（纯标准库）
│           ├── vocab_core.py     #   词库读写 / 词形归并 / FSRS 遗忘分
│           ├── pick.py           #   选词
│           ├── mark.py           #   标频（使用统计）
│           ├── feedback.py       #   反馈（更新 FSRS）
│           ├── add.py            #   写新词
│           ├── vocab_distill.py  #   生成允许词汇包
│           ├── story_audit.py    #   故事审计
│           ├── range_lib.py      #   范围词库 / 功能词白名单
│           └── state.py          #   批次状态机
├── vendor/                       # vendored 依赖（均为 MIT）
│   ├── fsrs/                     #   py-fsrs 6.3.1（含其 LICENSE）
│   └── typing_extensions.py      #   4.16.0
└── examples/
    ├── vocab.sample.json         # 示例学习词库
    └── range.sample.json         # 示例范围词汇库
```

## 快速开始

### 作为 DSH agent preset 使用

前置条件：已安装 [DeepSeek Harness (DSH)](https://github.com/deepseek-ai/dsh) 与 Python ≥ 3.10。

1. 把本仓库克隆到 DSH 的 agent presets 目录（每个 preset 一个目录，目录名 `openlxl` 必须保留）：

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

2. 启动 DSH，新建会话时选择 `openlxl` preset（agent 自动获得 6 个工具 + 领域技能）。

3. 准备两个词库（路径由你自己指定，工具参数或环境变量传入）：

   | 词库 | 默认路径（环境变量可改） | 作用 |
   |---|---|---|
   | FSRS 学习库 | `/workspace/vocab.json`（`ENGSTORY_VOCAB`） | 要学的词：目标词选择 / 使用统计 / 记忆反馈 |
   | 范围词汇库 | `./range_vocab.json`（`ENGSTORY_RANGE`） | 限定故事里普通词的词汇范围 |

4. 对 Agent 说「写故事」，它就会走完整闭环：选词 → 写故事 → 审计 → 标频 → 等你报「会/不会」→ 更新记忆。

### 作为 Python CLI 使用

要求 Python ≥ 3.10（无第三方运行时依赖，FSRS 已 vendored）。

```powershell
cd skills/engstory-domain
$V = "<你的学习词库路径>"; $R = "<你的范围词库路径>"

# 1. 写新词（用户确认后才做）
python scripts/add.py --words "abandon 放弃, coffin 棺材" --vocab $V

# 2. 选 7 个目标词
python scripts/pick.py --vocab $V

# 3. 生成允许词汇包（准备写故事）
python scripts/vocab_distill.py --targets "abandon,coffin" --range $R --vocab $V

# 4. 审计故事
python scripts/story_audit.py --text "<故事正文>" --targets "abandon,coffin" --range $R

# 5. 标频（记使用次数）
python scripts/mark.py --text "<故事正文>" --words "abandon,coffin" --vocab $V

# 6. 反馈（用户报完会/不会后）
python scripts/feedback.py --words "abandon 会, coffin 不会" --vocab $V
```

所有脚本支持 `--json` 输出，便于程序化调用。

## 工作流与状态机

```
写故事闭环（严格按顺序）：
  ① select_targets      从学习库选 7 个目标词           → TARGETS_SELECTED
  ② prepare_story_vocab 生成允许词汇包
  ③ 写 180–400 词纯英文故事（目标词加粗）
  ④ audit_story         审计通过才提交，失败最多重写 2 次
  ⑤ commit_story        保存故事 + 标频 + 打开反馈阶段   → WAITING_FEEDBACK
  ⑥ apply_feedback      用户报「会/不会」后才更新 FSRS   → WAITING_WORD_CONFIRMATION / IDLE
  ⑦ write_learning_words 审计发现的范围外词，用户确认后才写入学习库
```

| 工具 | 脚本 | 动作 | 何时触发 |
|---|---|---|---|
| `engstory_select_targets` | pick.py | 选目标词，开批次 | 每轮开始 |
| `engstory_prepare_story_vocab` | vocab_distill.py | 生成本轮允许词汇包 | 写故事前 |
| `engstory_audit_story` | story_audit.py | 只读审计 | 写故事后 |
| `engstory_commit_story` | story_audit.py + mark.py | 审计通过才保存 + 标频 | 审计通过后 |
| `engstory_apply_feedback` | feedback.py | 更新 FSRS 记忆状态 | 用户报完词后 |
| `engstory_write_learning_words` | add.py | 写入新词 | 用户明确确认后 |

## 数据文件

### 学习词库（JSON）

```json
{
  "meta": { "marked": { "<文本指纹 sha1>": "2026-08-15T20:00:00+08:00" } },
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

字段说明：

| 字段 | 含义 | 谁更新 |
|---|---|---|
| `picks` / `last_pick` | 被检索次数 / 上次检索时间 | pick.py |
| `uses` / `texts` / `last_use` | 使用次数 / 篇数 / 上次使用 | mark.py |
| `不会频次` | 重复导入次数 | add.py |
| `state`/`step`/`stability`/`difficulty`/`due`/`last_review`/`card_id` | FSRS 卡片参数 | feedback.py（py-fsrs 计算） |
| `forget_score` | 遗忘分缓存（选词/反馈时实时刷新） | pick.py / feedback.py |

多义词按 `英文|释义` 拆成独立词条（如 `blue|蓝色`、`blue|忧伤`），各自独立计数、独立记忆。

### 范围词汇库（JSON）

```json
{
  "words": {
    "castle":   { "gloss": "城堡" },
    "walk":     { "gloss": "走", "forms": ["walked", "walking"] }
  }
}
```

### 批次状态文件

默认在学习库同目录 `state.json`（`ENGSTORY_STATE` 可改），故事默认存学习库同目录 `stories/`。

## FSRS 说明

- 记忆状态用 [py-fsrs 6.3.1](https://github.com/open-spaced-repetition/py-fsrs) 计算（MIT），与 Anki FSRS 生态同算法。
- 遗忘分 = `(1 - 可提取性 retrievability) × 100`，0~100+，**越高越接近遗忘、越该练**：
  - 未反馈新卡默认 30；
  - 反馈过「会」的词 0~10，随间隔到期逐渐回升；
  - 反馈过「不会」的词会爬过 30 自动插队回炉。
- 标频（`uses/texts`）只影响同分时的排序，**不直接进入 FSRS 公式**；记忆调度只由反馈和流逝时间驱动。
- 依赖目录可用环境变量 `ENGSTORY_FSRS` 指向外部安装的 fsrs 包（如 `pip install fsrs` 后指向其 site-packages 所在目录），默认使用仓库 `vendor/`。

## 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `ENGSTORY_VOCAB` | `/workspace/vocab.json` | FSRS 学习词库路径 |
| `ENGSTORY_RANGE` | `./range_vocab.json` | 范围词汇库路径 |
| `ENGSTORY_STATE` | 学习库同目录 `state.json` | 批次状态文件 |
| `ENGSTORY_FSRS` | 仓库 `vendor/` | fsrs 依赖目录 |

## 许可

- 本仓库代码：MIT（见 [LICENSE](LICENSE)）。
- vendored 依赖：[py-fsrs](https://github.com/open-spaced-repetition/py-fsrs)（MIT，见 `vendor/fsrs/LICENSE`）、[typing-extensions](https://github.com/python/typing_extensions)（PSF-2.0 / Apache-2.0）。
- 致谢：记忆调度参照 [Anki](https://apps.ankiweb.net/) 的开源 [FSRS 间隔重复算法](https://github.com/open-spaced-repetition/fsrs4anki)。
