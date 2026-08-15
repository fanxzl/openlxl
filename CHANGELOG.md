# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
