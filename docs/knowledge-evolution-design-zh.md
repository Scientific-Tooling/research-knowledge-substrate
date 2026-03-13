# 强化知识演化能力设计

## 目的

本文基于 RKS 当前已经实现的本地研究知识底座，提出一套面向 `Knowledge Evolution System` 的强化设计。目标不是重写系统，而是在现有 `Paper / Claim / Concept / Edge / Hypothesis / Artifact / Task` 架构上，补齐“知识如何随时间沉积、冲突、收敛、被审阅确认”的能力。

这份设计的重点是回答四个问题：

- 当前架构已经具备哪些知识演化基础
- 当前还缺什么，导致系统只能“看见关系”，却还不能稳定地“管理演化”
- 应该增加哪些对象、流程和查询能力
- 如何分阶段落地，且不破坏现有 CLI、存储和 agent 工作流

## 当前架构评估

### 已具备的基础

当前实现已经具备做知识演化系统的核心地基。

#### 1. 稳定对象模型已存在

RKS 已经实现了最小研究图中的关键对象：

- `papers`
- `claims`
- `concepts`
- `methods`
- `datasets`
- `hypotheses`
- `edges`
- `artifacts`
- `tasks`

其中 `claims` 是核心知识单元，`concepts` 负责概念归一化，`edges` 负责图关系，`hypotheses` 负责项目级研究假设，`artifacts` 与 `tasks` 提供了可追溯的处理链路。这个对象集合足以支撑演化层的构建，而不需要推倒重来。

#### 2. Claim 已具有可计算结构

当前 `claims` 记录已经不只是文本，而包含：

- `predicate`
- `subject_concept_id`
- `object_concept_id`
- `object_text`
- `context_json`
- `evidence_json`
- `confidence`
- `status`

这使 Claim 可以作为知识演化图中的最小“命题节点”，而不是普通段落。

#### 3. 图关系与审阅闭环已存在

当前系统已经有两层 claim relation 机制：

- 查询时推断的 `inferred_relations`
- 经过审阅后持久化到 `edges` 的 `reviewed_relations`

CLI 也已经提供：

- `rks query claim-relations <claim_id>`
- `rks review promote-claim-relation ...`
- `rks review retract-claim-relation ...`

这意味着系统已经具备“候选关系 -> 审阅确认 -> 图谱固化”的基本演化闭环。

#### 4. 现有存储模式适合增量扩展

当前存储是 `SQLite + filesystem + embeddings` 的务实结构，且对象之间通过稳定 ID 连接。对于知识演化系统来说，这种结构有两个优点：

- 可以快速增加新的演化表或快照表，而不要求替换底层数据库
- 可以把“原始事实”和“演化派生结果”分层存储，降低治理风险

### 当前短板

当前架构虽然能做知识演化的原型，但还不足以把“演化”当作一等系统能力。

#### 1. 大部分 claim-to-claim 关系仍是查询时推断

现在 `supports / contradicts / refines` 很大一部分是在查询时由 `QueryService._infer_claim_relation()` 动态计算出来的，而不是稳定存储的对象。这带来三个问题：

- 同一个查询在不同算法版本下可能返回不同结果
- 无法记录“某个关系是何时首次发现、何时被审阅、何时被撤销”的历史
- 无法对候选关系进行批量治理、排序、审阅和重算

#### 2. 缺少时间维度上的演化对象

当前系统能存 Claim、Concept、Edge，但缺少“演化事件”这一层。系统还不能显式表达：

- 某个观点在什么时间段从边缘意见变成主流共识
- 某个 Concept 下的冲突在什么年份激增
- 某个 Hypothesis 是如何从提出、受支持、受挑战，再到收敛的

#### 3. 缺少候选层与稳定层之间的中间治理层

当前只有两种状态：

- 即时推断
- promote 后成为正式边

这对小规模系统足够，但对长期演化不够。系统需要一个中间层，来承接：

- 候选关系缓存
- 算法版本
- 审阅优先级
- 证据完整性评分
- 冲突强度与聚类

#### 4. 缺少面向演化的聚合查询

当前查询更偏对象级：

- 查某个 claim 的关系
- 查某个 concept 的证据
- 查某个 paper 的摘要

但知识演化系统需要更高层的问题模板，例如：

- 某个概念过去三年的共识变化
- 哪些 claim 形成了冲突簇
- 哪些假设正在从弱支持变成强支持
- 哪些关系最值得优先审阅

## 设计目标

### 核心目标

1. 让知识演化成为持久化、可审计、可重算的系统能力，而不是查询时副产物。
2. 把“候选关系”“审阅确认关系”“时间维度上的演化事件”明确分层。
3. 在不破坏当前架构的前提下，为 Query Layer 和 Agent Workflow 增加演化视角。
4. 让系统既能服务单条 Claim 的局部判断，也能服务 Concept 和 Hypothesis 级别的长期趋势分析。

### 非目标

本文不试图一次性实现：

- 完整学术本体论
- 复杂因果推理引擎
- 自动判定“科学真理”
- 全自动无人工治理的知识图谱

这里的目标更务实：先把“演化事实可存、可审、可查、可回放”做实。

## 设计原则

### 1. 原始事实与派生结论分层

论文、Claim、Concept、已审阅 Edge 属于原始或治理后事实；趋势、冲突簇、共识分数、优先级属于派生结果。二者必须分开存储，避免派生分析反向污染底层事实层。

### 2. 候选关系必须可回放

任意一个候选演化关系都应当能回答：

- 它由哪个算法版本生成
- 生成时使用了哪些 Claim / Paper / Artifact
- 当时的评分是多少
- 为什么会被 promote 或被忽略

### 3. 演化首先是时间问题，其次才是图问题

如果没有时间戳、状态变迁和可重建历史，系统只能做静态图查询，而不能做知识演化。

### 4. 人机协同优先于全自动写入

系统可以自动发现候选关系、冲突和趋势，但正式进入“稳定知识层”的内容仍应经过 promote 或 review。

`project-scoped acceptance` 可以存在，但它只能影响项目内排序、工作流状态或 project view，不能替代全局 reviewed fact，也不能直接写入正式知识层。

### 5. 证据锚点必须保持 paper-grounded

演化层可以围绕 `Concept`、`Hypothesis` 或 `Project` 做聚合与排序，但证据本身仍应回到 `Paper` 或 `Claim`。

这意味着：

- `Concept` 可以是聚合锚点、主题标签、timeline 入口
- `Concept` 不是一手 evidence object
- project context 可以决定“看什么”，但不能决定“什么算事实”

## 目标架构

在当前架构之上，建议把知识演化能力拆为四层：

```text
Base Fact Layer
  papers / claims / concepts / methods / datasets / reviewed edges / hypotheses

Candidate Evolution Layer
  materialized relation candidates / conflict clusters / consensus candidates

Evolution Event Layer
  relation reviews / hypothesis state changes / concept trend snapshots

Evolution Query Layer
  timeline / consensus / controversy / open-question / review-priority queries
```

### 第一层：Base Fact Layer

这一层继续沿用当前对象模型，不做结构颠覆。

保留现有事实对象：

- `claims`
- `concepts`
- `papers`
- `edges`
- `hypotheses`
- `project_links`
- `hypothesis_evidence_links`

其中：

- `claims` 继续承载结构化命题
- `edges` 继续承载经过审阅确认的正式图关系
- `hypotheses` 继续承载项目级研究目标与待验证命题

### 第二层：Candidate Evolution Layer

这是当前系统最缺的部分。建议新增一组“候选演化对象”，用于把动态推断结果 materialize 成可治理实体。

建议新增表：

#### `claim_relation_candidates`

用于持久化当前查询时推断出来的 claim 关系候选。

建议字段：

- `id`
- `source_claim_id`
- `target_claim_id`
- `relation_type`
- `score`
- `status`
- `reason_json`
- `evidence_json`
- `generator_name`
- `generator_version`
- `generated_at`
- `superseded_by_candidate_id`

推荐状态：

- `active`
- `promoted`
- `rejected`
- `superseded`

这一层的意义是把“推断”变成“候选事实”，从而支持缓存、排序、批审和历史追踪。

#### `claim_conflict_clusters`

用于将多个彼此矛盾、彼此竞争，或围绕同一主题形成显著分歧的 Claim 聚合为一个冲突/争议单元。

这里应优先围绕 `contradicts` 与其他明确表示立场分歧的关系建模，而不是把 `refines` 默认视为冲突。`refines` 更适合作为补充上下文或局部结构信息，用于解释争议簇内部的细化路径，而不是直接计入 controversy。

建议字段：

- `id`
- `anchor_concept_id`
- `topic_label`
- `status`
- `summary_json`
- `created_at`
- `updated_at`

#### `claim_conflict_cluster_members`

- `cluster_id`
- `claim_id`
- `role`
- `stance`
- `confidence`
- `created_at`

这个结构的目的是让系统不只返回一堆 pairwise relations，而是能围绕一个主题给出“争议结构”。

### 第三层：Evolution Event Layer

候选关系和正式关系本身还不够。知识演化系统真正需要的是“事件流”。

建议新增表：

#### `evolution_events`

用于统一记录与知识演化相关的重要状态变更。

建议字段：

- `id`
- `event_type`
- `object_id`
- `object_type`
- `related_object_id`
- `related_object_type`
- `project_id`
- `before_json`
- `after_json`
- `evidence_json`
- `created_by`
- `created_at`

典型事件：

- claim relation candidate created
- claim relation promoted
- claim relation retracted
- hypothesis confidence updated
- concept entered controversy state
- concept consensus strengthened

这一层让系统第一次能够回答“发生过什么”，而不仅是“现在是什么”。

#### `concept_timeline_snapshots`

用于存储面向 Concept 的时间分桶聚合结果。

建议字段：

- `id`
- `concept_id`
- `time_bucket`
- `claim_count`
- `paper_count`
- `support_count`
- `contradict_count`
- `refine_count`
- `consensus_score`
- `controversy_score`
- `basis_layer`
- `summary_json`
- `generator_version`
- `created_at`

这个表不属于原始事实，而是演化分析缓存。它适合驱动：

- timeline query
- trend visualization
- topic health monitoring

其中 `basis_layer` 用于明确该快照是基于 `reviewed`、`candidate` 还是混合视图生成。第一版应优先支持 `reviewed` basis，候选层时间线如果存在，应作为单独的 exploratory 视图返回，避免不同真值层混算后让时间序列失去可解释性。

### 第四层：Evolution Query Layer

在 Query Service 之上增加专门的演化查询，而不是继续把所有能力都压进对象级 query。

建议新增查询接口：

- `query concept-timeline <concept>`
- `query concept-consensus <concept>`
- `query concept-controversies <concept>`
- `query hypothesis-evolution <hypothesis_id>`
- `query review-priorities <concept|project>`
- `query open-questions <concept|project>`

这些查询都应返回结构化 JSON，而不是自由文本。生成性总结应当建立在结构结果之上。

## 与当前表结构的关系

本设计强调“增强”而非“替换”，所以需要明确新旧对象之间的分工。

### `edges` 继续承载正式图事实

当前 `edges` 表适合保存经过人工或 agent 审阅确认的稳定关系，因此不建议把所有候选推断直接写进 `edges`。否则会混淆：

- 已确认知识
- 待审查候选
- 暂时派生结果

因此建议：

- `edges` 只保存正式关系
- `claim_relation_candidates` 保存待治理候选
- `evolution_events` 保存状态变化历史

### `artifacts` 与 `tasks` 负责回放与批处理

当前已有 `artifacts` 和 `tasks`，非常适合作为演化批处理的控制平面。

可以新增任务类型：

- `materialize_claim_relations`
- `build_concept_timeline`
- `cluster_claim_conflicts`
- `refresh_hypothesis_evidence`

对应产物可写为 artifact：

- `claim_relation_candidates.json`
- `concept_timeline_snapshot.json`
- `claim_conflict_clusters.json`

这样新能力不会破坏现有 extraction pipeline，而是以独立批任务形式叠加。

### `hypotheses` 与项目工作流是演化层的高价值入口

当前系统已经有：

- `research_projects`
- `hypotheses`
- `hypothesis_evidence_links`

这是知识演化系统非常重要的落脚点。原因很简单：真正高价值的“演化”不是看所有 Claim 漫无边界地漂浮，而是观察某个研究问题或某个假设如何随着新证据而变化。

因此建议把项目与假设视为演化系统的第一批正式用户，而不是附属对象。

## 核心流程设计

### 流程 1：Claim 关系候选物化

当前是：

1. 查询 claim relation
2. 即时推断 supports / contradicts / refines
3. 仅当 promote 时才落到 `edges`

建议改为：

1. 后台任务扫描 claims
2. 生成 `claim_relation_candidates`
3. 为每条候选打分、记录原因与算法版本
4. query 层优先读取 candidate 表；若 candidate 缺失、过期，或 generator_version 落后于当前要求，则回退到即时推断，并显式标记结果来源
5. promote 时写 `edges` 并写 `evolution_events`
6. retract 时标记 event 与 candidate / edge 状态

这会把“推断”升级为“可治理的候选库存”。

### 流程 2：Concept 演化时间线构建

目标是回答：

- 某个概念的支持/反驳是否在增强
- 某个领域是否正在进入争议期
- 某个主题的论文量和命题量是否持续增长

建议流程：

1. 按 Concept 聚合相关 Claim 与 Paper
2. 按年或季度建立时间桶
3. 统计各类关系数、论文数、Claim 数
4. 计算 `consensus_score` 与 `controversy_score`
5. 生成 `concept_timeline_snapshots`

推荐的务实评分：

```text
consensus_score = support_count / max(1, support_count + contradict_count)
controversy_score = min(support_count, contradict_count) / max(1, support_count + contradict_count)
```

这两个分数并不代表真理，只代表“结构上的共识程度”和“结构上的争议密度”。

第一版建议明确：

- 正式 timeline 默认只基于 `Reviewed` relations 计算
- `Candidate` relations 只用于 exploratory timeline、审阅优先级或候选发现
- 不同 `basis_layer` 的时间线不能在同一条趋势线上直接混合比较

### 流程 3：Hypothesis 演化跟踪

针对每个 `hypothesis`，系统应能持续回答：

- 有哪些新证据进入
- 证据倾向是支持还是挑战
- 当前假设状态是更稳固还是更脆弱

建议：

1. 保持 `hypothesis_evidence_links` 的 evidence object 以 `Claim`、`Paper` 为主
2. `Concept` 可以作为 hypothesis 的聚合锚点、topic filter 或分析入口，但不应被视为一手 evidence
3. 定期生成假设的支持/反驳聚合
4. 变更置信度时写入 `evolution_events`
5. 输出 hypothesis timeline

这样，Knowledge Evolution System 就不再停留在 Claim 图层，而能支撑真实研究项目。

### 流程 4：审阅优先级排序

知识演化系统不应该要求人或 agent 手工检查所有候选关系。系统需要生成“最值得审”的队列。

建议优先级函数综合考虑：

- 候选关系分数
- 关联 Concept 的热度
- 是否涉及高争议主题
- 是否直接影响某个活跃 hypothesis
- 是否来自新论文或新时间桶

输出可作为：

- `rks query review-priorities <concept>`
- `rks query review-priorities --project <project_id>`

## 数据治理模型

### 三层真值模型

为避免系统把派生结果误当成最终知识，建议明确三层真值状态：

#### 第一层：Observed

来自论文和抽取流水线的原始 Claim / Concept / Evidence。

#### 第二层：Candidate

由算法推断出的 relation candidate、cluster、trend、priority。它们可以指导研究，但不是正式知识。

#### 第三层：Reviewed

经过人工或受信 agent promote 后，写入 `edges` 的全局 reviewed facts。

如果系统引入项目内 acceptance / dismissal，它们应被视为 project-scoped workflow state，而不是 `Reviewed` 全局真值；查询与 UI 必须把这两者显式区分。

这三层必须在查询和 UI 上显式区分。

### 可追溯性要求

任何一个演化结论都应能追溯到：

- 关联 Claim
- 关联 Paper
- 生成算法版本
- 审阅人或 agent 身份
- 相关 artifact

否则演化分析将失去研究可信度。

## API 与 CLI 扩展建议

### 新增查询命令

建议增加：

```bash
rks query concept-timeline <concept>
rks query concept-consensus <concept>
rks query concept-controversies <concept>
rks query hypothesis-evolution <hypothesis_id>
rks query review-priorities <concept_or_project>
rks query open-questions <concept_or_project>
```

### 新增批处理命令

```bash
rks evolve materialize-claim-relations
rks evolve build-concept-timelines
rks evolve cluster-claim-conflicts
rks evolve refresh-hypothesis-evidence
```

### 新增审阅命令

在已有 promote / retract 基础上，可以进一步增加：

```bash
rks review accept-candidate <candidate_id>
rks review reject-candidate <candidate_id>
rks review annotate-conflict-cluster <cluster_id>
```

这些命令的重点不是功能数量，而是让“候选治理”成为显式操作。

## 实现分期

### Phase 1：把推断关系变成候选库存

目标：先解决“演化不可持久化”的问题。

工作项：

- 新增 `claim_relation_candidates`
- 为当前 relation inference 输出打分与理由
- 增加批处理任务 `materialize_claim_relations`
- `query claim-relations` 优先显示候选库存，但在库存缺失或过期时保留即时推断回退，并显式返回来源
- promote / retract 写入 `evolution_events`

完成后系统能力提升：

- 关系推断可缓存
- 可批量审阅
- 可记录算法版本
- 可保留历史

### Phase 2：增加 Concept 时间线与争议结构

目标：让系统从“关系查询”升级到“主题演化分析”。

工作项：

- 新增 `concept_timeline_snapshots`
- 新增 `claim_conflict_clusters`
- 实现 `concept-timeline` 与 `concept-controversies` 查询
- 增加 review-priority 排序逻辑

完成后系统能力提升：

- 可以看主题趋势
- 可以识别争议集中区
- 可以给出审阅队列

### Phase 3：把演化能力与项目假设打通

目标：让 Knowledge Evolution System 直接服务研究工作流。

工作项：

- 实现 `hypothesis-evolution`
- 让候选关系和冲突簇影响 hypothesis evidence ranking
- 增加 open question 发现逻辑
- 让 research output 生成器直接使用 evolution query 结果

完成后系统能力提升：

- 可观察假设的动态变化
- 可自动发现证据薄弱区与争议点
- 可生成更像“研究判断”而不是“检索摘要”的输出

## 风险与控制

### 风险 1：候选关系爆炸

如果所有 Claim 两两比较，候选数量会快速膨胀。

控制方式：

- 先按 Concept 或 subject 聚类后再比较
- 只对时间窗口内或语义相近的 Claim 建候选
- 设置最小得分阈值

### 风险 2：启发式推断质量不足

当前 relation inference 规则较轻，直接大规模物化会放大误差。

控制方式：

- 保留 candidate 层，不直接写正式边
- 记录 `generator_version`
- 用任务重跑和 supersede 机制替换旧候选

### 风险 3：派生分析污染事实层

如果 trend、cluster、priority 直接混入 `edges` 或 `claims`，系统会变得难以治理。

控制方式：

- 派生结果单独存表
- 所有派生结果都带版本和生成时间
- 只允许 reviewed 事实进入正式图层

### 风险 4：查询层复杂度上升

如果所有演化逻辑都堆进单一 `QueryService`，代码会很快失控。

控制方式：

- 新增独立的 evolution service
- 把 object query 与 evolution query 分开
- 将 timeline、cluster、priority 做成独立方法或模块

## 验收标准

当以下问题可以稳定回答时，可以认为第一版 Knowledge Evolution System 已成立：

1. 一个 claim relation 候选是否可以被持久化、排序、审阅和回放。
2. 一个 concept 是否可以看到按时间分桶的支持、反驳与争议变化。
3. 一个 hypothesis 是否可以看到证据如何推动其状态变化。
4. 一个 agent 是否可以拿到“最值得审阅的候选关系列表”。
5. 所有演化结论是否都能追溯到 claim、paper、artifact 和 reviewer。

## 结论

基于当前 RKS 架构，构建 Knowledge Evolution System 是完全可行的，而且不需要重构核心系统。真正需要补齐的，不是新的基础对象，而是位于 `claims / concepts / edges / hypotheses` 之上的一层“演化治理与时间化分析层”。

最小可行路径应当是：

1. 先把动态 claim relation inference 物化为候选库存。
2. 再引入事件流和时间线快照。
3. 最后把这些能力接到 hypothesis、research output 和 agent workflow 上。

这样演化能力就不再是查询层的临时技巧，而会成为 RKS 的正式系统能力。
