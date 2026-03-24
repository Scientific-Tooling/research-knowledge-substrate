# RKS 产品路线图

本文档基于已完成的核心基础设施（见 `product-priorities.md` 和 `research-output-roadmap.md`），规划 RKS 的下一阶段发展方向。

**制定日期**：2026-03-22

---

## 指导原则

- **可信度优先于功能数量**：RKS 的差异化在于可审计、可溯源的研究图谱，而非最多的特性。
- **先让现有承诺可证明，再扩展边界**：提取质量可测量之前，不扩展提取类型。
- **保持窄责任边界**：RKS 专注于被明确告知的论文，不做自主网络爬取或文献发现。
- **Agent 是一等公民**：任何新功能都应同时对 CLI 用户和 Agent 工作流可用。

---

## 第一阶段：夯实核心（1-2 个月）

### P0：提取质量的可测量性

**背景**：当前最大盲区是不知道 Claims/Concepts 提取质量有多好，无法检测模型或 prompt 变更对质量的影响。

**任务**：

- [ ] 为 5-10 篇领域内熟悉的论文手工标注 Claims Golden Set
- [x] 实现 precision/recall 计算工具（`rks evaluate claims <paper_id> --golden <path> [--min-f1 N]`）
- [x] 将提取质量评估接入 CI，每次提交自动回归（`tests/test_claim_quality_regression.py`，CI 自动发现）
- [x] 文档化评估方法论，确保 Golden Set 可维护（`docs/evaluation-methodology.md`）

**退出标准**：

- 能用数值指标（precision/recall/F1）描述当前提取质量基线
- CI 在提取质量下降超过阈值时报警
- Golden Set 覆盖 abstract、methods、results 三个主要 section

---

### P0：端到端自动化集成测试

**背景**：`rks-autotest` 技能文件已存在，但缺乏覆盖完整 pipeline 的自动化测试。

**任务**：

- [ ] 制作轻量级测试语料（1-2 篇公开论文的 PDF 固定版本，当前用 fixture JSON）
- [x] 编写覆盖 `ingest → extract → query → output` 完整路径的集成测试（`tests/test_e2e_pipeline.py`）
- [x] 接入 CI，每次提交必须通过（`package-check.yml` 已覆盖）
- [ ] 覆盖 `llm-api` 双轨路径（当前仅 `agent` 路径，llm-api 需 API key）

**退出标准**：

- 单次 CI 运行可验证完整 pipeline 的正确性
- 测试失败时输出足够定位问题的诊断信息
- 测试运行时间在合理范围内（目标 < 5 分钟）

---

## 第二阶段：降低使用门槛（2-4 个月）

### P1：最小可行 Web UI

**背景**：纯 CLI 对非开发者研究人员是硬门槛。RKS 已有 HTTP 服务作为后端基础。

**范围**（严格限定，不过度工程化）：

- [ ] 论文列表页（支持按 tag 筛选、按年份排序）
- [ ] 论文详情页（Claims、Concepts、Methods、Datasets 的结构化展示）
- [ ] Claim 关系审阅页（Promote / Retract 操作，对应 `review` 命令）
- [ ] Concept 图谱可视化（只读，基于现有 graph 数据）

**约束**：

- 后端 100% 使用 RKS 现有 HTTP API，不引入新存储层
- **写入操作只开放 Review**，保持数据写入路径的可控性
- 不做用户认证（本地工具定位）

**退出标准**：

- 非开发者研究人员可以通过浏览器完成 Claim 审阅工作
- UI 不引入任何 CLI 和 HTTP 层没有的新业务逻辑

---

### P1：Zotero / BibTeX 批量导入

**背景**：研究人员已有文献库，应打通既有工作流而非要求从头重建。

**任务**：

- [ ] 支持从 BibTeX 文件生成 `rks batch ingest` manifest
- [ ] 支持从 Zotero RDF 导出文件生成 manifest
- [ ] 处理 DOI 缺失的情况（退化为 title + author 元数据记录，无法自动获取 PDF）
- [ ] 文档化推荐的 Zotero → RKS 迁移流程

**退出标准**：

- 一条命令将 Zotero 导出转换为可直接用于 `rks batch ingest` 的 manifest
- 转换过程中的缺失字段以警告而非错误形式报告

---

## 第三阶段：Agent 协作深化（3-6 个月）

### P2：技能（Skill）端到端行为验证

**背景**：10 个技能文件是"设计意图"，需要证明它们真的能指导外部 Agent 完成完整任务。

**任务**：

- [ ] 为每个核心技能录制可复现的 Agent 运行日志作为行为基线
- [ ] 实现技能文件变更的回归检测：技能更新后自动验证 Agent 工作流不破坏
- [ ] 识别并修复技能指令中的歧义（基于实际 Agent 运行中的失败案例）

**退出标准**：

- 至少 5 个核心技能有对应的可复现集成测试
- 技能文件的任何修改都触发对应验证

---

### P2：冲突集群（Conflict Cluster）主动通知

**背景**：`evolution_repository` 已能检测冲突，但用户需要主动查询，不够及时。

**任务**：

- [ ] 每次新论文入库后自动运行冲突检测
- [ ] 在 `rks status paper <id>` 输出中展示该论文引入的新冲突
- [ ] 在 `rks ingest` 完成时报告冲突摘要（如有）
- [ ] 支持 `rks output conflict-digest` 命令输出全局冲突快照

**退出标准**：

- 新论文入库后无需额外操作即可知晓其引入的争议
- 冲突通知可链接回具体 Claim ID，便于追查

---

### P2：多用户协作路径规划

**背景**：SQLite 是单机方案，团队协作需要明确扩展路径。此阶段不实现，只完成设计。

**任务**：

- [ ] 文档化 PostgreSQL 适配层的接口要求（Repository 层需要哪些变更）
- [ ] 设计基于 Snapshot 的"团队共享快照"协作协议（已有导出/导入基础）
- [ ] 评估 Snapshot 合并（merge）的可行性与冲突解决策略

**退出标准**：

- 有一份设计文档描述从单机到多用户的演进路径
- 路径不要求重写存储层，可渐进迁移

---

## 永不做的事

| 方向 | 原因 |
|------|------|
| 自主网络爬取 | 破坏窄责任边界；质量不可控；与 RKS 定位冲突 |
| 无溯源的自由生成 | 违反证据绑定原则；退化为普通 AI 工具 |
| 绕过 Review 门控的批量写入 | 破坏审定与推断的区分，这是 RKS 核心信任基础 |
| 大而全的前端 Dashboard | 分散重心；超出本地研究工具定位 |

---

## 里程碑总览

```
2026 Q2（1-2月）
├── ✦ 提取质量基线建立（Golden Set + CI 回归）
└── ✦ 端到端集成测试接入 CI

2026 Q3（2-4月）
├── ✦ 最小 Web UI 上线（论文浏览 + Claim 审阅）
└── ✦ Zotero / BibTeX 批量导入

2026 Q4（3-6月）
├── ✦ 技能端到端行为验证体系
├── ✦ 冲突集群主动通知
└── ✦ 多用户协作设计文档
```

---

## 与现有文档的关系

| 文档 | 状态 | 关系 |
|------|------|------|
| `product-priorities.md` | 已完成 | 本 roadmap 的起点，P0-P3 均已交付 |
| `research-output-roadmap.md` | 已完成 | Research Output 层已具备，本 roadmap 在其上构建 |
| `focus-optimization-plan.md` | 参考 | 约束原则与本 roadmap 一致 |
| 本文档 | 进行中 | 描述下一阶段方向 |
