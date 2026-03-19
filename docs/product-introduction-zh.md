# RKS 产品介绍

Research Knowledge Substrate（RKS）是一个面向 agent 的本地研究图谱系统。
它用于导入论文、抽取结构化研究对象、审阅证据关系，并生成有证据支撑的研究输出。

本文档回答三个核心问题：RKS 是什么、适合谁、系统边界在哪里。

## 1. 产品定位

RKS 面向“证据驱动”的研究工作流，不是通用笔记工具，也不是通用网页爬虫。

当你需要以下能力时，RKS 最合适：

- 构建本地、可检查的论文知识图谱
- 保留可复查的抽取产物与流程痕迹
- 将“推断 relation”和“审阅后 relation”明确分离
- 同时支持人工与 agent 的稳定操作接口

## 2. 目标用户

RKS 主要服务两类用户：

- 直接通过 CLI 操作的研究人员与工程人员
- 通过 CLI/HTTP 驱动 RKS 的外部 AI agent（如 Codex、Claude Code）

系统默认用户关注可追溯性、可检查性和可重复执行。

## 3. 核心原则

### 3.1 本地优先、可检查

RKS 数据默认落在本地（SQLite + 文件系统 artifact）。
关键步骤应留下可检查证据，而不是隐藏在黑盒状态里。

### 3.2 Artifact 优先

导入和抽取流程强调“先产物，后结构化持久化”。
你可以看到每一步的输入输出，而不是只看到最终结果。

### 3.3 审阅驱动持久化

系统推断出的 claim relation 默认不是长期真值。
只有经过明确审阅动作的关系才应作为 durable graph facts。

### 3.4 CLI-first 外部边界

`rks` CLI 是规范语义的主接口。
HTTP 是镜像传输层，用于集成和一致性检查，而非平行控制面。

### 3.5 职责边界收敛

RKS 负责：

- 接收稳定输入（本地 PDF、DOI、arXiv、PMID、规范 URL）
- 抽取并组织研究对象
- 提供确定性查询、审阅和输出能力

RKS 不负责开放式网页发现和非规范来源清洗。

## 4. 能力全景

RKS 能力可分为六层：

1. 导入层：
   PDF / DOI / arXiv / PMID / URL
2. 抽取层：
   text / claims / methods / datasets / summary
3. 图谱层：
   概念标准化、边关系、引用关系、审阅关系持久化
4. 检索与推理层：
   搜索、确定性 query、evidence 聚合
5. 研究输出层：
   answer / brief / disagreements / opportunities / reading-list / project outputs
6. 运维与治理层：
   状态检查、任务队列、relation promotion/retraction

## 5. 数据模型概览

核心对象类型：

- `paper`：论文与来源锚点
- `claim`：带 evidence 的结构化断言
- `concept`：标准化术语节点
- `method`、`dataset`：一等研究对象
- `edge`：显式类型关系（如 `about`、`supported_by`、`uses`）
- `project`、`hypothesis`：用户策划的研究上下文与假设跟踪
- `task`：agent 模式请求/回写生命周期

该模型可同时支持“从证据出发”与“从研究问题出发”两种工作方式。

## 6. 接口说明

### 6.1 CLI

CLI 是产品语义主入口。
典型命令包括：

- `rks ingest ...`
- `rks extract ...`
- `rks query ...`
- `rks review ...`
- `rks output ...`

### 6.2 HTTP

RKS 提供本地 HTTP 服务用于轻量 UI 与 agent 集成。
HTTP 应镜像 CLI 能力，不应独立演化为另一套产品语义。

## 7. LLM 双轨模型

所有 LLM 相关任务采用 dual-track：

- `llm-api`：RKS 直接调用模型 API
- `agent`：外部 agent 执行并通过 import 回写

如果任务存在本地确定性实现，允许使用 `heuristic`。

## 8. 典型工作流

1. 初始化配置和数据库
2. 导入论文或文献引用
3. 检查状态与 artifacts
4. 执行抽取与总结
5. 检索、查询、核对证据
6. 审阅关键 relation 并持久化
7. 生成研究输出支持决策

## 9. RKS 的非目标

RKS 不是：

- 通用文献发现爬虫
- 替代外部 agent 规划层的编排系统
- 无审阅即可直接作为事实真值引擎的系统

RKS 的价值在于：为研究流程提供透明、可追溯、可审阅的本地知识基座。

## 10. 相关文档

- 用户操作：`docs/user-usage-guide-zh.md`
- Agent 操作：`docs/agent-usage-guide-zh.md`
- 手动测试：`docs/manual-testing-guide-zh.md`
- 约束边界：`docs/system-constraints.md`
- 进度里程碑：`docs/progress.md`
