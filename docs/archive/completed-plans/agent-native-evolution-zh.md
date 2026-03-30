# RKS Agent-Native 演进评估与路线图

**制定日期**：2026-03-24

---

## 背景与目标

本文档回答一个问题：**RKS 离一个真正以 Agent 为中心的知识记忆外挂系统，还有多远的距离？**

目标系统应满足以下三个标准：

1. **Agent 导入时**：系统能主动协助 Agent 判断摄入什么、如何存入，而不仅仅是被动接收
2. **Agent 提取时**：系统以 Agent 可直接消费的结构化形式输出知识，而不需要 Agent 解析人类可读文本
3. **Agent 再组合时**：系统支持跨论文、跨维度的知识比对与合成，Agent 可以将推导结果写回系统

系统结构本身应是**动态自主生长**的有机体，而不是需要人类管理员持续维护的静态图书馆。

### 与现有演化设计文档的关系

`knowledge-evolution-design-zh.md` 已经完成了知识演化系统的四层架构设计（Base Fact → Candidate Evolution → Evolution Event → Evolution Query），并大部分付诸实现：

- `claim_relation_candidates` 表及物化流程 ✅
- `claim_conflict_clusters` / `concept_timeline_snapshots` / `evolution_events` 表 ✅
- `rks evolution build-timeline / cluster-conflicts / conflict-graph / materialize-candidates` ✅
- `rks query review-priorities / open-questions / concept-controversies` ✅
- 三层真值模型（Observed / Candidate / Reviewed）架构原则 ✅

本文档在上述已实现能力的基础上，专注于 **Agent 操作界面层**的差距：Agent 如何高效读写这个系统，以及系统如何具备自主生长的感知和记忆能力。两份文档互补，不重叠。

---

## 一、现状评估

### 已做对的事

- **Artifact-first 工作流**：每步留下可检查中间产物，Agent 可恢复和审计状态
- **双轨 LLM 合约**（llm-api / agent）：LLM 工作有明确边界，无隐式调用
- **实体模型完备**：paper → claims → concepts → edges → hypotheses → projects 形成完整语义网络
- **Evolution 系统已就绪**：候选关系物化、时间线、冲突集群、审阅优先级均已实现（见 `knowledge-evolution-design-zh.md`）
- **Skill bundle**：将操作手册打包注入 Agent 上下文的机制已就位

### 真实存在的差距

当前系统的核心设计隐喻是**图书馆管理员**：被动接收材料，整理，应答查询。Evolution 系统让它能感知知识的历史变化，但 Agent 与系统之间的**操作界面**仍停留在"人类使用 CLI"的模式，而不是"Agent 直接消费结构化数据"的模式。具体差距体现在以下三个方向。

---

## 二、三个方向的差距分析

### 方向 1：数据导入时的 Agent 能力

**现状**：Agent 模式是"请求文件 → 外部处理 → 导入文件"的批次循环。Agent 是被调用的工具，而不是有主动性的探索者。

**核心缺口**：

| 问题 | 影响 |
|------|------|
| 没有"下一步应该摄入什么"的反馈机制 | Agent 不知道知识图谱的边界在哪，无法自主填补空白 |
| 导入来源高度论文化，无"Agent 主动发现"通道 | Agent 浏览、推理过程中产生的知识无法写入系统 |
| Confirmation rule 要求每次显式征得同意 | 阻断自主摄入循环，需要针对受信任 Agent 的授权豁免机制 |
| `rks note add` 无法区分用户注记与 Agent 推理注记 | Agent 产生的中间判断和疑问无法与用户注记分开管理 |

**需要的能力**：

- `rks agenda next --project-id P --question "..."` — 综合 `rks query open-questions` 和 `rks query review-priorities` 的已有输出，生成 Agent 下一步行动建议（可优先复用已有命令实现）
- `rks note agent-insight <target_type> <target_id> --content "..." [--session-id S]` — 专用 Agent 推理注记写入通道，`created_by` 标记为 agent，与用户注记区分
- 受信任 Agent 的摄入授权配置项（`trusted_agent_ingest: true`），在配置层面绕过 confirmation rule

---

### 方向 2：数据提取时的 Agent 友好性

**现状**：`rks query review-priorities`、`rks query open-questions`、`rks evolution conflict-graph` 等命令已存在且功能完备。真正的问题是**输出格式**：这些命令返回人类可读的 prose text 或混合格式，Agent 消费时需要二次解析，增加失败风险。

**核心缺口**：

| 问题 | 影响 |
|------|------|
| `rks output answer/brief/disagreements/opportunities` 等返回散文文本 | Agent 无法可靠地从中提取结构化字段 |
| 无批量上下文聚合命令 | Agent 建立问题上下文需要 5-10 次 round-trip（papers list → claims → concepts → disagreements...）|
| 无图遍历接口 | Agent 无法从任意 concept 出发探索 N 跳内的相关 claims，只能点查已知 ID |
| `rks show claim <id>` 无完整证据链模式 | Agent 无法用单条命令建立 paper → section → quote → claim → concept 的完整溯源 |

**需要的能力**：

- 所有 `rks output` 子命令增加 `--format json` 选项，返回带稳定字段的结构化输出（schema 文档化，可被 skill 文件引用）
- `rks context build --question "..." [--project-id P]` — 单次调用返回相关 claims（按 confidence 排序）、支持 papers、已知 disagreements、evidence gaps，目标是将 Agent 建立上下文的 round-trip 从 5-10 次降至 1 次
- `rks graph walk <concept_id> --depth N [--relation-types r1,r2] [--format json]` — 从 concept 出发沿边遍历，返回节点列表和边列表
- `rks show claim <id> --full-provenance` — 返回从 paper → artifact path → section → quote → claim fields → linked concepts 的完整链条

---

### 方向 3：数据再组合与比对

**现状**：Evolution 系统已能检测冲突、建立时间线、生成候选关系。但 Agent 仍是单向的**读取者**，无法将推导结果写回系统；比对操作也局限于 paper-to-paper。

**核心缺口**：

| 问题 | 影响 |
|------|------|
| 无 Agent 可写入的"合成节点" | Agent 从多篇论文推导出的新洞见无处安放，只能存在于外部 Agent 的临时上下文中 |
| `rks output compare` 只支持 paper vs paper | 无法比较 concept vs concept 或 hypothesis vs hypothesis 的证据分布 |
| `rks review promote-claim-relation` 是单条操作 | Candidate relations 大量积压时 Agent 处理效率低，无法批量提交 |
| 无知识状态 diff | 无法追踪 Agent 一轮工作的净贡献（新增了哪些支持、哪些反驳、哪些冲突） |

**需要的能力**：

- `rks synthesis create --source-claims c1,c2,c3 --text "..." --created-by agent` — Agent 创建有明确来源声明的合成节点（标记为 synthesis 类型，绑定 source claims，不能凭空写入）
- `rks output compare --type concept --id1 C1 --id2 C2 [--format json]` — 扩展 compare 命令，支持 concept vs concept（证据对比、支持论文对比、争议分布对比）
- `rks review batch-promote --input <manifest.json>` — manifest 格式：`[{source_claim_id, relation_type, target_claim_id, reviewed_by}]`，允许 Agent 批量提交经过判断的候选关系
- `rks evolution diff --from <date|snapshot_id> [--to <date>] [--format json]` — 返回：新增 claims 数、新增 edges 数、新冲突数、新支持数、changed concepts

---

## 三、作为动态自主生长系统的结构性需求

以上三个方向解决的是"Agent 单次操作的效率问题"。要让系统本身成为动态有机体，还需要两个结构性增加：

### 3.1 知识边界感知

`rks query open-questions` 已能返回证据稀疏区和未支持假设，但其输出格式是人类可读的，且不包含"Agent 下一步动作"的直接建议。需要一个机器可读的知识空白地图：

```
rks gaps [--scope-type topic|project|concept] [--scope-id ID] [--format json]
# 返回: [{concept, evidence_count, controversy_score, suggested_ingest_query}, ...]
```

`suggested_ingest_query` 字段可以直接作为 Agent 搜索下一篇文献的输入，形成**感知 → 行动 → 回写**的闭环。这与 `open-questions` 的区别在于：`open-questions` 面向人类判断，`gaps` 面向 Agent 直接执行。

### 3.2 Agent 工作记忆协议

当前 Agent 每次操作都是无状态的（通过 artifacts 传递）。长期自主研究工作流需要 session 概念，让 Agent 在多次调用间保持目标和工作状态：

```
rks session start --project-id P --goal "..."   # 返回 session_id
rks session checkpoint --session-id S --summary "..." --pending-actions '[...]'
rks session status --session-id S               # 返回 goal + checkpoint 历史 + pending actions
rks session list [--project-id P]
```

没有 session 概念，Agent 每次启动都需要重新建立工作状态，这是当前自主研究工作流的主要摩擦点。

---

## 四、能力评分总览

| 维度 | 当前水平 | 目标水平 | 主要缺口 |
|------|---------|---------|---------|
| 导入时 Agent 能力 | ★★★☆☆ | ★★★★★ | 无摄入建议、无 Agent 注记通道 |
| 提取时 Agent 友好 | ★★★☆☆ | ★★★★★ | 无 JSON 输出、无图遍历、无批量上下文聚合 |
| 再组合与比对 | ★★★☆☆ | ★★★★★ | 无合成节点、无 diff、无跨维度比较、无批量 promote |
| 自主生长动态性 | ★★☆☆☆ | ★★★★★ | 无边界感知（gaps）、无 session 协议 |
| 整体架构完整性 | ★★★★☆ | ★★★★★ | 基础扎实，Evolution 层已就绪 |

---

## 五、路线图

本路线图是对 `roadmap-zh.md` 的补充，专注于 Agent-Native 界面层演进，与现有路线图并行推进。

---

### 第一阶段：Agent 输出结构化（P0）

**目标**：消除 Agent 消费 RKS 输出时的解析摩擦，不涉及数据模型变更。

**任务**：

- [ ] 为所有 `rks output` 子命令增加 `--format json` 选项
  - `answer`、`brief`、`disagreements`、`open-questions`、`opportunities`、`compare`
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

### 第二阶段：图遍历与知识边界感知（P1）

**目标**：让 Agent 能主动探索知识图谱，感知系统的无知边界，不依赖预先知道的 ID。

**任务**：

- [ ] `rks graph walk <concept_id> --depth N [--relation-types r1,r2] [--format json]`
  - 从 concept 出发，沿边遍历，返回节点列表（claims、concepts、papers）和边列表
- [ ] `rks gaps [--scope-type topic|project|concept] [--scope-id ID] [--format json]`
  - 基于 `open-questions` 已有逻辑扩展，增加 `suggested_ingest_query` 字段
  - 每条 gap 附带 Agent 可直接执行的搜索建议
- [ ] `rks note agent-insight <target_type> <target_id> --content "..." [--session-id S]`
  - 专用 Agent 推理注记通道，`created_by = agent`，在 `rks note list` 中可按类型筛选

**退出标准**：
- Agent 可以从任意 concept 出发在图谱中导航
- `rks gaps` 输出可直接驱动 Agent 的摄入决策

---

### 第三阶段：Agent 写回与批量操作（P2）

**目标**：让 Agent 从读取者升级为贡献者，能将推导结果写回系统，并高效处理大批量候选关系。

**任务**：

- [ ] `rks synthesis create --source-claims c1,c2,c3 --text "..." --created-by agent`
  - 创建有明确来源声明的合成节点（标记类型，绑定 source claims，不能凭空写入）
  - 合成节点可被后续 `rks output` 和查询命令引用
- [ ] `rks review batch-promote --input <manifest.json>`
  - manifest：`[{source_claim_id, relation_type, target_claim_id, reviewed_by}]`
  - 允许 Agent 批量提交经判断的候选关系，每条仍记录 `reviewed_by`
- [ ] `rks output compare` 扩展：支持 `--type concept --id1 C1 --id2 C2`
  - 证据对比、支持论文对比、争议分布对比，返回 JSON
- [ ] `rks evolution diff --from <date|snapshot_id> [--to <date>] [--format json]`
  - 返回：新增 claims/edges/冲突/支持的数量，以及 changed concepts 列表

**退出标准**：
- Agent 可以将跨论文推导的洞见写回系统，附带来源证明
- Agent 可以用 `evolution diff` 量化自己一轮工作的净贡献

---

### 第四阶段：Agent Session 协议（P3）

**目标**：支持长期自主研究工作流，Agent 在多次调用间保持研究目标和工作状态。

**任务**：

- [ ] Agent Session 协议
  - `rks session start --project-id P --goal "..."` → 返回 session_id
  - `rks session checkpoint --session-id S --summary "..." --pending-actions '[...]'`
  - `rks session status --session-id S` → goal + checkpoint 历史 + pending actions
  - `rks session list [--project-id P]`
- [ ] `rks note agent-insight` 支持关联 `--session-id S`（与 P1 任务合并实现，P3 补充 session 关联）
- [ ] `rks agenda next --project-id P [--session-id S] [--format json]`
  - 综合 `gaps` + `open-questions` + `review-priorities`，输出 Agent 下一步行动建议列表
  - 若传入 session_id，结合 checkpoint 历史排除已处理项

**退出标准**：
- Agent 可以跨多次调用持续推进一个研究项目，不需要每次重建上下文
- `rks session status` 返回足够信息供 Agent 恢复工作状态

---

## 六、里程碑总览

```
第一阶段（约 2-4 周）
└── ✦ output --format json + context build + full-provenance
    → Agent 单次调用获得结构化上下文

第二阶段（约 1-2 个月）
├── ✦ graph walk + gaps + agent-insight note
└── → Agent 主动探索知识边界

第三阶段（约 2-3 个月）
├── ✦ synthesis create + batch-promote + evolution diff
└── → Agent 从读取者升级为贡献者

第四阶段（约 3-5 个月）
├── ✦ Agent Session 协议 + agenda next
└── → 长期自主研究循环，跨会话保持状态
```

---

## 七、与现有文档的关系

| 文档 | 关系 |
|------|------|
| `knowledge-evolution-design-zh.md` | 本文的基础；Evolution 系统四层架构和三层真值模型已在其中设计并实现，本文不重复 |
| `roadmap-zh.md` | 平行文档；本文专注 Agent-Native 界面层，对方专注提取质量和 Web UI |
| `dual-track-llm-contract.md` | 本文不修改双轨合约，在合约框架内扩展 Agent 能力 |
| `system-constraints.md` | 本文所有新能力均遵守现有约束（证据绑定、写入需显式）|
| `agent-usage-guide-zh.md` | 本文路线图实现后，需同步更新该使用指南 |

---

## 八、不做的事

| 方向 | 原因 |
|------|------|
| 无溯源的 Agent 自由生成写入 | synthesis 节点必须绑定 source claims，不能凭空写入 |
| 绕过双轨合约的直接 LLM 调用 | 破坏可审计性，退化为普通 AI 工具 |
| Agent 直接写入 reviewed 层 | Agent 提交候选，promote 仍需显式调用，维护三层真值模型的完整性 |
| 自主网络爬取 | 这是 Agent 的责任，不是 RKS 的责任 |
