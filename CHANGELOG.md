# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.1.3] - 2026-08-22

### 新增

- **分层剧情记忆**：
  - 新增 `chapter-ledger.jsonl`（账本 `ledger.py`）：每章结构化保存事实、人物变化、关系变化、线索增删与后果，用于"已发生什么"。
  - 新增 `plot-outline.json`（总纲 `outline.py`）：卷/故事弧级长期方向（核心主线 / 终点 / 卷 / 弧 / 永久事实 / 禁止项），用于长篇记忆。
  - 新增**冲突检测**：`ledger` 用"主体内容词重叠 + 否定极性相反"启发式，能标记「哥哥确实来过旧警局」vs「哥哥从未进过警局」这类矛盾（提示级，不自动拦截）。
- **可提炼风格**：
  - 新增 `style-profile.json`（`style.py`）：风格配置带维度 / must_do / avoid / 置信度。
  - 新增 `engstory_extract_style`（从参考片段 + 读者感受生成**候选**风格，不落盘）与 `engstory_confirm_style`（用户确认后才写入）。风格不会自动覆盖。
- **按需上下文组装**：
  - 新增 `context.py` + `engstory_build_context`：把风格 + 卷/弧总纲 + 事实账本 + 当前状态 + 目标词组装成一个**有界的写作上下文包**。
- **连载状态增强（storyline.py）**：
  - 新增风格 / 角色 / 关系 / 线索 / 本章目标 / 上章后果等字段。
  - 支持 `--style-profile`、`--characters`、`--open-threads`、`--relationship-state`、`--chapter-goal`、`--consequence`、`--new-threads`、`--resolved-threads` 等参数。
- **工具从 6 个扩展到 9 个**：新增 `engstory_build_context` / `engstory_extract_style` / `engstory_confirm_style`；`engstory_commit_story` 新增 `obstacle`、`choice`、`story_arc`、`scene_location`、`facts_added`、`facts_confirmed`、`character_changes`、`relationship_changes` 等可选字段，可同步写入账本。

### 修复

- **故事连载 Chapter 1 源起丢失**：滚动 `recap` 超过 5 章时永久保留 Chapter 1（初始因果）+ 最近 4 章，长篇不丢源头。
- **冷启动主线写死英文**：无激活连载时直接 `advance`，自动以本章摘要作为主线，不再固定为 `A continuous adventure.`。
- **中文 JSON 乱码**：为 `runPython` 增加 `PYTHONIOENCODING=utf-8`，修复被管道捕获 stdout 时 Python 用 GBK 编码导致中文摘要/线索/角色被 Node 误解码的问题。
- **`commit_story` 可复用兜底**：`summary` / `next_hook` 缺省时自动从正文末尾提取。

### 变更

- **写作规范升级为章节戏剧结构**：`写故事/SKILL.md` 要求每章完成「立即接场 → 本章目标 → 阻力 → 选择 → 后果 → 具体钩子」6 步，并加入负面约束（禁止重复天气 / 随机加人 / 空泛结尾 / 梦境解释等）。
- **领域规则补充**：`engstory-domain/SKILL.md` 明确"词汇审计 ≠ 文学审计"，提交前须生成结构化字段（summary / next_hook / chapter_goal / consequence / new_threads / resolved_threads）。

### 数据文件

- 词库、范围库、故事、状态、连载、风格、总纲、账本都是用户的持久学习数据，位于 preset 之外。
- 默认与词库同目录：`state.json`、`storyline.json`、`style-profile.json`、`plot-outline.json`、`chapter-ledger.jsonl`、`stories/`。

## [0.1.2] - 2026-08-16

### 修复

- **修复 FSRS `due` 参数未发挥作用的问题**：此前选词排序只看遗忘分（retrievability），完全忽略 Anki 的 `due` 到期时间，导致反馈「不会」的词因遗忘分≈0 反而沉底、迟迟不出现。现改为 Anki 同款「到期驱动」排序，`due` 正确生效——「不会」的词下一轮（无论隔多久调用）必现、排在最前。

### 变更

- **选词升级为到期驱动四队列**：学习中/重学中的词（反馈过「不会」的）→ 已逾期的复习词 → 没反馈过的新词 → 未到期的复习词
- **反馈输出不再显示「0.0 天后」**：改为自然语言（即将到期 / 约 X 分钟后 / 约 X 小时后 / 明天 / N 天后）
- **选词行新增「到期」列**：新词 / 已逾期 / 即将到期 / 约 X 分钟后 / 明天 / N 天后，一眼看出每个词该不该练

## [0.1.1] - 2026-08-16

首个公开版本。

### 新增

- **6 个确定性工具**：选目标词 / 准备故事词汇包 / 审计故事 / 提交故事 / 应用反馈 / 写入新词（DSH agent preset）
- **FSRS 间隔重复调度**：记忆调度参照 Anki 的开源 FSRS 算法（vendored py-fsrs 6.3.1），每个词独立维护难度 / 稳定性 / 下次到期
- **遗忘分实时排序选词**：新卡默认 30 分，反馈过「不会」的词随时间爬升自动插队回炉，刚复习的词沉底休息
- **受限词汇故事写作**：目标词强制加粗并豁免范围约束，普通词限定在范围词库 + 内置功能词 + 明确专名内
- **严格审计**：目标词全中 / 普通词范围 / 字数 180–400 / 纯英文，审计通过才提交
- **批次状态机**：`TARGETS_SELECTED → WAITING_FEEDBACK → WAITING_WORD_CONFIRMATION → IDLE`，无用户反馈不更新记忆、无用户确认不写新词
- **词形归并**：`sought → seek`、`stood → stand`；多义词按 `英文|释义` 独立词条、独立计数
- **文本指纹去重**：同一篇文本重复标记自动跳过，防止词频虚高
- **双用法**：DSH agent preset（对话式完整闭环）+ 独立 Python CLI（纯标准库，Python ≥ 3.10）
- **示例数据**：`examples/vocab.sample.json`、`examples/range.sample.json`

### 许可

- 本仓库：MIT
- vendored：py-fsrs（MIT）、typing-extensions（PSF-2.0 / Apache-2.0）
