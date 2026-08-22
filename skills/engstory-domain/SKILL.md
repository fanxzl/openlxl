---
name: engstory-domain
description: >-
  英语词汇故事学习领域：从 FSRS 学习库选目标词，用范围词汇库限制普通词，
  按用户风格与章节戏剧结构连载纯英文故事，审计入账后等待用户反馈更新记忆；用户明确确认后才写入新词。
platforms: [windows]
metadata:
  version: "1.3.0"
---

# 英语词汇故事 Agent 领域规则

本模式只有两个长期词库与一份连载状态：

1. **范围词汇库**：限制故事中的普通词汇范围，不表示用户已经掌握。
2. **FSRS 学习库**：保存真正要学习的词，负责目标词选择、使用统计和记忆反馈。
3. **连载状态（storyline.json）**：跨轮次持久化故事主线设定（premise）、用户风格（style_profile）、角色（characters）、未解决线索（open_threads）、章节号（current_chapter）、本章目标（chapter_goal）、上章后果（last_consequence）、滚动前情（recap）与上章结尾钩子（last_ending）。
4. **风格配置（style-profile.json，可选）**：从参考片段 + 用户读感提炼的写作方式（dimensions/must_do/avoid/confidence），独立于剧情。
5. **剧情总纲（plot-outline.json，可选）**：卷/故事弧级长期方向（core_thread/end_state/volumes/arcs/permanent_facts），用于长篇记忆。
6. **章节事实账本（chapter-ledger.jsonl，可选）**：每章结构化事实、人物/关系变化、线索增删、后果，用于"已发生什么"。

## 内部工具

所有确定性操作都通过以下固定工具完成，不要直接调用脚本或手改 JSON：

- `engstory_select_targets`：从 FSRS 学习库选目标词，开启一个学习批次，**同时返回完整连载状态（storyline：风格/角色/线索/后果/章节号）**。
- `engstory_prepare_story_vocab`：从范围词汇库生成本轮允许词汇包。
- `engstory_audit_story`：只读审计故事（目标词命中 + 普通词范围）。
- `engstory_commit_story`：审计通过后保存故事、记录使用、**推进连载状态或开启新剧本连载（含风格/角色/线索/目标/后果）、并写入章节账本（若提供 facts/character_changes 等）**、进入反馈阶段。
- `engstory_apply_feedback`：应用用户明确报告的“会/不会/勉强/很熟”。
- `engstory_write_learning_words`：写入用户明确确认的新词。
- `engstory_build_context`：组装**写作上下文包**（style + plot + facts + immediate + targets），供模型动笔前读取。
- `engstory_extract_style`：根据参考片段 + 读者感受生成**候选**风格分析骨架（不直接落盘）。
- `engstory_confirm_style`：确认后把风格配置写入 `style-profile.json`（安全闸门：用户确认才写）。

所有工具都必须显式传入 FSRS 学习库绝对路径；`--range` 传入范围词汇库绝对路径。批次状态默认保存在学习库同目录的 `state.json`；连载状态保存在同目录的 `storyline.json`；风格/总纲/账本默认与词库同目录（`style-profile.json` / `plot-outline.json` / `chapter-ledger.jsonl`）。

## 完整工作流（严格按顺序）

### 1. 选目标词与获取前情

调用 `engstory_select_targets`（默认 7 个）。
工具返回包含 `words` 与 `storyline`（若已有连载，含 `active`、`current_chapter`、`premise`、`style_profile`、`characters`、`open_threads`、`chapter_goal`、`last_consequence`、`last_ending`、`recap`）。

### 2. 剧本识别与分流

- **分支 A（用户给出了新剧本/新设定/新背景）**：
  - 判定标准：用户输入中提供了故事设定、设定卡、小说大纲、或明确要求“换个故事/开新篇”。
  - 动作：将用户给的设定作为主线（premise），结合风格（可选用户给的 style_profile）开启 **Chapter 1**。
  - 提交参数：`engstory_commit_story` 必须传 `premise`，并传本章的 `summary`、`next_hook`、`chapter_goal`、`consequence`，可选 `style_profile`、`characters`、`open_threads`。
- **分支 B（用户常规触发：写故事/继续/下一篇/选词）**：
  - 判定标准：用户未给新设定。
  - 动作：直接承接 `storyline.last_ending` 的镜头、`chapter_goal` 与 `last_consequence`，写 **Chapter N+1**。
  - 提交参数：`engstory_commit_story` 无需传 premise，转传 `summary`、`next_hook`、`chapter_goal`、`consequence`、`new_threads`、`resolved_threads`。

### 3. 准备故事词汇包

调用 `engstory_prepare_story_vocab`，得到允许普通词与词形。

### 4. 纯英文连载写作

模型按"章节戏剧结构"写 300–500 词纯英文故事：
- 目标词必须全部出现且加粗（如 **abandon**）；
- 普通词落在允许集合内；
- 紧扣上一章后果与结尾动作，情节层层推进，篇末留下自然镜头动作；
- 遵守负面约束（不重复介绍天气、不随机加人物、不空泛结尾等）。

### 5. 审计

调用 `engstory_audit_story` 检查目标词与普通词范围。失败则重写（最多 2 次），不提交失败稿。

### 6. 提交与连载推进

审计通过后调用 `engstory_commit_story`（带上 `summary`、`next_hook`，以及 `chapter_goal`、`consequence`、`new_threads`/`resolved_threads`；新剧本加 `premise`/`style_profile`/`characters`/`open_threads`）：保存故事文件、记录词频、更新 `storyline.json`、进入 `WAITING_FEEDBACK`。

### 7. 反馈

把本轮目标词和释义列给用户，等待报告“会/不会/勉强/很熟”。没有用户反馈前不得调用 `engstory_apply_feedback`。

### 8. 发现词确认

审计发现的范围外词进入待确认列表。只有用户明确说“把 X 加入学习库”后，才调用 `engstory_write_learning_words`。

## 故事质量规则

**词汇审计 ≠ 文学审计。** 工具层只确定性地校验可计算事实；文学质量由模型自检 + 用户反馈兜底。

- 工具确定检查：目标词全部出现、字数、纯英文、普通词范围、重复提交、`summary`/`next_hook`/`chapter_goal`/`consequence` 是否存在、`storyline` 字段是否成功更新。
- 模型自检（写作前必须确认）：本章目标、阻力、主角选择、后果、是否推进线索、结尾是否有具体钩子、是否因目标词引入无关内容。

提交前必须生成以下结构化字段，禁止留空：

```text
summary          本章发生了什么
next_hook        下一章从什么具体镜头接续
chapter_goal     主角本章要完成什么
consequence      主角的选择造成了什么结果
new_threads      本章新增了哪些未解决问题（JSON 数组）
resolved_threads 本章解决了哪些旧问题（JSON 数组，为 id 列表）
```

## 输出格式（固定模板，模板外不加任何文字）

### 呈现故事

审计、提交均静默，只在失败时说话：

```
## 第 {N} 章 · {章节英文标题}（{词数} 词）

{正文}

已入账：目标词 {命中}/{总数}。
```

### 报词（故事之后立即给出，无额外寒暄）

```
| # | 词条 | 释义 |
|---|---|---|
| 1 | crypt | 地下室 |
...

逐个报：会 / 不会（可选：勉强 / 很熟）。
```

### 反馈结果（一行，禁止逐词列难度）

```
已记录：会 {a} / 不会 {b} / 勉强 {c} / 很熟 {d}。不会的词{时间}复习。
```

---

## 数据文件

- 词库、范围库、故事、状态与连载信息都是用户的持久学习数据，位于 preset 之外。
- 默认连载文件在学习库同目录 `storyline.json`；默认故事目录为 `stories/`。
