# RKS 路线图

本文档合并了产品路线（原 `roadmap-zh.md`）与 Agent-Native 界面层演进（原 `agent-native-evolution-zh.md`），统一规划 RKS 下一阶段发展方向。

**更新日期**：2026-03-29

---

## 指导原则

- **可信度优先于功能数量**：RKS 的差异化在于可审计、可溯源的研究图谱，而非最多的特性。
- **先让现有承诺可证明，再扩展边界**：提取质量可测量之前，不扩展提取类型。
- **保持窄责任边界**：RKS 专注于被明确告知的论文，不做自主网络爬取或文献发现。
- **Agent 是一等公民**：任何新功能都应同时对 CLI 用户和 Agent 工作流可用，输出格式对 Agent 直接可消费。

---

## 第零阶段：产品验证与用户接触（立即开始，2 周内）

> **背景**：2026-03-29 产品评估发现，RKS 在工程质量上表现优秀，但尚无外部用户验证。
> 项目存在"以构建代替发布"的倾向——持续增加功能和文档，而核心问题（有人需要这个吗？）未被回答。
> 完整评估见 `docs/product-assessment-2026-03.md`。

### P-1：停止新增功能，聚焦核心价值

**原则**：当前代码库功能已远超验证所需。瓶颈不是能力——是能力有效性的证据。

**任务**：

- [ ] 冻结新功能开发，直到第零阶段退出标准达成
- [ ] 识别并记录当前最常用的 5 条 CLI 命令（基于自身使用频率）
- [ ] 识别 10 个 agent skill 中实际使用频率最高的 3-4 个，计划合并其余

---

### P-1：构建可体验的 Demo Workspace

**背景**：新用户面对 `pip install` 之后无处可去。需要一个开箱即用的体验路径。

**任务**：

- [ ] 选取 5-10 篇同一主题的真实论文（例如癌症流行病学，利用已有 GLOBOCAN 基础）
- [ ] 完成完整的 ingest → extract → build graph 流程
- [ ] 导出为可分发的 workspace archive（`rks export workspace demo.tar.gz`）
- [ ] 编写 3 分钟快速入门指南（`docs/quickstart.md`），从 `pip install` 到 `rks import workspace` 到第一次有意义的查询
- [ ] 快速入门以"展示结果"开头，而非"解释哲学"

**退出标准**：

- 新用户可在 3 分钟内看到真实论文的知识图谱查询结果
- 快速入门中无需阅读架构文档即可体验核心价值

---

### P-1：获取 3 名真实用户

**背景**：产品假设未经外部验证。需要真人使用反馈来校准后续优先级。

**任务**：

- [ ] 找到 3 名非开发者研究人员（读论文为日常工作的人）
- [ ] 提供 Demo Workspace + 快速入门，观察其使用过程（不主动解释）
- [ ] 记录：哪些步骤卡住了？哪些功能被忽略？第一个"有用"的时刻在哪？
- [ ] 根据反馈调整第一至二阶段优先级排序

**退出标准**：

- 至少 3 人完成了从安装到首次查询的完整流程
- 收集到的反馈已记录并体现在后续阶段的任务排序中

---

### P-1：大幅扩展提取质量基线（合并进第一阶段 P0）

**背景**：RKS 的全部价值取决于提取质量。当前仅 2 篇 golden paper（1 篇真实论文），远不够支撑产品可信度。此条目提升原 P0 的 golden set 目标。

**任务**：

- [ ] 将 golden set 目标从 5-10 篇提升到 **20 篇**，覆盖至少 3 个不同学科领域
- [ ] 优先标注提取失败案例（低 F1 论文），而非只挑成功案例
- [ ] 记录每篇论文的提取质量和主要失败模式（缺失 claim、错误 predicate、幻觉等）
- [ ] 建立按领域分组的质量基线（例如：生物医学 avg F1、CS avg F1）

**退出标准**：

- 20 篇 golden paper 覆盖 3+ 领域
- 质量基线可用于回答"RKS 在 X 领域的提取有多好？"

---

### P-1：继续收敛 Operations 层复杂度

**背景**：`operations/service.py` 已拆成薄 facade，并委托给 `_project.py`、`_paper.py`、`_review.py`、`_output.py`、`_evolution.py` 等子服务。原 3000+ 行 god object 风险已缓解，但 `_paper.py`、`_evolution.py`、`reasoning/output.py` 仍各自接近或超过 1000 行，后续修改仍容易出现局部复杂度堆积。

**任务**：

- [x] 将 `ResearchOperations` 拆为薄 facade + focused sub-services，并保持 CLI/HTTP 对外 API 不变
- [ ] 继续拆分 `_paper.py` 中的 merge、status、quality-report 逻辑
- [ ] 继续拆分 `_evolution.py` 中的 timeline、conflict、review-priority/open-question 逻辑
- [ ] 将 `reasoning/output.py` 的 output builders 与 ranking/composition helpers 分离
- [ ] 拆分后每个核心模块尽量不超过 800 行

**退出标准**：

- Operations facade 继续保持薄层委托
- `_paper.py`、`_evolution.py`、`reasoning/output.py` 不再是 1000+ 行集中模块
- 所有现有测试通过

---

### P-1：明确用户定位

**背景**：项目同时面向人类研究人员（但 CLI 是门槛）和 AI Agent（但 skill 是产品而非 CLI）。两头不靠的风险。

**任务**：

- [ ] 写一段不超过 50 字的产品定位（不使用"substrate"、"dual-track"、"artifact-first"等内部术语）
- [ ] 确定主要用户画像：人类研究人员 OR AI Agent OR 两者（但需明确优先级）
- [ ] 如果主要面向人类研究人员：Web UI 优先级应提前
- [ ] 如果主要面向 AI Agent：skill 质量和 JSON 输出优先级应提前

**退出标准**：

- 一句话可以向陌生人解释"RKS 是什么，为什么要用它"

---

## 当前 Agent-Native 能力评估

| 维度 | 当前水平 | 目标水平 | 主要缺口 |
|------|---------|---------|---------|
| 导入时 Agent 能力 | ★★★☆☆ | ★★★★★ | 无摄入建议、无 Agent 注记通道 |
| 提取时 Agent 友好 | ★★★☆☆ | ★★★★★ | 无 JSON 输出、无图遍历、无批量上下文聚合 |
| 再组合与比对 | ★★★☆☆ | ★★★★★ | 无合成节点、无 diff、无跨维度比较、无批量 promote |
| 自主生长动态性 | ★★☆☆☆ | ★★★★★ | 无边界感知（gaps）、无 session 协议 |
| 整体架构完整性 | ★★★★☆ | ★★★★★ | 基础扎实，Evolution 层已就绪 |

---

## 第一阶段：夯实核心 + Agent 输出结构化（1-2 个月）

### P0：提取质量的可测量性

**背景**：当前最大盲区是不知道 Claims/Concepts 提取质量有多好，无法检测模型或 prompt 变更对质量的影响。

**任务**：

- [ ] 为 5-10 篇领域内熟悉的论文手工标注 Claims Golden Set（已完成 1 篇：GLOBOCAN 2020，F1=0.788）
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

### P0：Agent 输出结构化

**背景**：`rks output` 系列命令返回人类可读的散文文本，Agent 消费时需要二次解析，增加失败风险。当前建立问题上下文需要 5-10 次 round-trip。

**任务**：

- [ ] 为所有 `rks output` 子命令增加 `--format json` 选项
  - 覆盖：`answer`、`brief`、`disagreements`、`open-questions`、`opportunities`、`compare`
  - JSON schema 固定，字段有文档，可被 Agent skill 文件引用
- [ ] `rks show claim <id>` 增加 `--full-provenance` 选项
  - 返回：paper metadata → artifact path → section → quote → claim fields → linked concepts
- [ ] `rks context build --question "..." [--project-id P]`
  - 单次调用返回结构化的：相关 claims（按 confidence 排序）、支持 papers、已知 disagreements、evidence gaps
  - 目标是将 Agent 建立问题上下文的 round-trip 从 5-10 次降至 1 次

**退出标准**：

- Agent 可以用单条命令获得结构化的研究上下文，无需解析 prose text
- 所有输出命令的 JSON schema 有对应文档

---

## 第二阶段：降低使用门槛 + Agent 图谱探索（2-4 个月）

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

### P1：图遍历与知识边界感知

**背景**：Agent 只能点查已知 ID，无法从任意 concept 出发探索图谱，也无法感知系统的知识空白以指导下一步摄入。

**任务**：

- [ ] `rks graph walk <concept_id> --depth N [--relation-types r1,r2] [--format json]`
  - 从 concept 出发，沿边遍历，返回节点列表（claims、concepts、papers）和边列表
- [ ] `rks gaps [--scope-type topic|project|concept] [--scope-id ID] [--format json]`
  - 基于 `open-questions` 已有逻辑扩展，增加 `suggested_ingest_query` 字段
  - 每条 gap 附带 Agent 可直接执行的搜索建议，形成**感知 → 行动 → 回写**闭环
- [ ] `rks note agent-insight <target_type> <target_id> --content "..." [--session-id S]`
  - 专用 Agent 推理注记通道，`created_by = agent`，在 `rks note list` 中可按类型筛选

**退出标准**：

- Agent 可以从任意 concept 出发在图谱中导航
- `rks gaps` 输出可直接驱动 Agent 的摄入决策

---

## 第三阶段：Agent 协作深化 + 写回能力（3-6 个月）

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

### P2：Agent 写回与批量操作

**背景**：Agent 目前是单向读取者，无法将推导结果写回系统；候选关系大量积压时也无法批量处理。

**任务**：

- [ ] `rks synthesis create --source-claims c1,c2,c3 --text "..." --created-by agent`
  - 创建有明确来源声明的合成节点（标记类型，绑定 source claims，不能凭空写入）
  - 合成节点可被后续 `rks output` 和查询命令引用
- [ ] `rks review batch-promote --input <manifest.json>`
  - manifest：`[{source_claim_id, relation_type, target_claim_id, reviewed_by}]`
  - 允许 Agent 批量提交经判断的候选关系，每条仍记录 `reviewed_by`
- [ ] `rks output compare` 扩展：支持 `--type concept --id1 C1 --id2 C2 [--format json]`
  - 证据对比、支持论文对比、争议分布对比
- [ ] `rks evolution diff --from <date|snapshot_id> [--to <date>] [--format json]`
  - 返回：新增 claims/edges/冲突/支持的数量，以及 changed concepts 列表

**退出标准**：

- Agent 可以将跨论文推导的洞见写回系统，附带来源证明
- Agent 可以用 `evolution diff` 量化自己一轮工作的净贡献

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

## 第四阶段：Agent Session 协议（长期）

### P3：跨会话工作状态持久化

**背景**：Agent 每次启动都需要重新建立工作状态，这是当前自主研究工作流的主要摩擦点。长期自主研究需要 session 概念，让 Agent 在多次调用间保持目标和工作状态。

**任务**：

- [ ] Agent Session 协议
  - `rks session start --project-id P --goal "..."` → 返回 session_id
  - `rks session checkpoint --session-id S --summary "..." --pending-actions '[...]'`
  - `rks session status --session-id S` → goal + checkpoint 历史 + pending actions
  - `rks session list [--project-id P]`
- [ ] `rks note agent-insight` 支持 `--session-id S` 关联（与第二阶段任务合并实现，P3 补充 session 关联）
- [ ] `rks agenda next --project-id P [--session-id S] [--format json]`
  - 综合 `gaps` + `open-questions` + `review-priorities`，输出 Agent 下一步行动建议列表
  - 若传入 session_id，结合 checkpoint 历史排除已处理项

**退出标准**：

- Agent 可以跨多次调用持续推进一个研究项目，不需要每次重建上下文
- `rks session status` 返回足够信息供 Agent 恢复工作状态

---

## 永不做的事

| 方向 | 原因 |
|------|------|
| 自主网络爬取 | 破坏窄责任边界；质量不可控；与 RKS 定位冲突 |
| 无溯源的自由生成或 Agent 写入 | 违反证据绑定原则；synthesis 节点必须绑定 source claims |
| 绕过 Review 门控的批量写入 | 破坏审定与推断的区分，这是 RKS 核心信任基础 |
| Agent 直接写入 reviewed 层 | Agent 提交候选，promote 仍需显式调用，维护三层真值模型 |
| 绕过双轨合约的直接 LLM 调用 | 破坏可审计性，退化为普通 AI 工具 |
| 大而全的前端 Dashboard | 分散重心；超出本地研究工具定位 |

---

## 里程碑总览

```
2026 Q2 前半（第零阶段，2 周）⬅ 新增，最高优先级
├── ✦ 冻结新功能，聚焦核心价值验证
├── ✦ 构建 Demo Workspace + 3 分钟快速入门
├── ✦ 获取 3 名真实用户反馈
├── ✦ 明确用户定位（一句话 pitch）
├── ✦ 拆分 ResearchOperations god object
└── ✦ 扩展 Golden Set 到 20 篇 / 3+ 领域

2026 Q2 后半（第一阶段，1-2 个月）
├── ✦ 提取质量基线建立（Golden Set + CI 回归）
├── ✦ 端到端集成测试接入 CI
└── ✦ Agent 输出结构化（--format json + context build + full-provenance）

2026 Q3（第二阶段，2-4 个月）
├── ✦ 最小 Web UI 上线（论文浏览 + Claim 审阅）
├── ✦ Zotero / BibTeX 批量导入
└── ✦ Agent 图谱探索（graph walk + gaps + agent-insight note）

2026 Q4（第三阶段，3-6 个月）
├── ✦ 技能端到端行为验证体系
├── ✦ 冲突集群主动通知
├── ✦ Agent 写回能力（synthesis + batch-promote + evolution diff）
└── ✦ 多用户协作设计文档

2027 Q1+（第四阶段，长期）
└── ✦ Agent Session 协议（跨会话状态持久化 + agenda next）
```

---

## 与现有文档的关系

| 文档 | 状态 | 关系 |
|------|------|------|
| `product-priorities.md` | 已完成 | 本 roadmap 的起点，P0-P3 均已交付 |
| `research-output-roadmap.md` | 已完成 | Research Output 层已具备，本 roadmap 在其上构建 |
| `knowledge-evolution-design-zh.md` | 已完成 | Evolution 四层架构和三层真值模型的设计与实现记录 |
| `focus-optimization-plan.md` | 参考 | 约束原则与本 roadmap 一致 |
| `dual-track-llm-contract.md` | 参考 | 本 roadmap 所有新能力均在双轨合约框架内扩展 |
| `agent-usage-guide-zh.md` | 需同步 | 第二至四阶段能力实现后需更新 |
| `product-assessment-2026-03.md` | 参考 | 第零阶段的评估依据；记录了做对的事和问题诊断 |
| 本文档 | 进行中 | 合并自原 `roadmap-zh.md` 和 `agent-native-evolution-zh.md`，2026-03-29 新增第零阶段 |
