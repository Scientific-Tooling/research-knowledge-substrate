# 知识演化系统

## 目的

本文描述 RKS 在当前代码架构下应如何强化 `Knowledge Evolution System` 能力。

这里的重点不是重新发明一个抽象的知识图系统，而是基于当前已经存在的本地研究知识底座，回答一个更实际的问题：

> 当越来越多论文、Claim、Concept、Hypothesis 和审阅动作进入系统后，RKS 如何把这些对象组织成一个可追溯、可审阅、可时间化的知识演化 substrate。

## 系统定位

如果 RKS 的操作者主要是外部 agent，而不是系统内部自治 agent，那么知识演化系统的定位应当非常明确：

**RKS 不是自动科研系统，而是知识演化机制的 substrate。**

这意味着：

- 外部 agent 负责研究任务分解、问题判断和工作流决策
- RKS 负责维护 paper-grounded 的知识对象、图关系、审阅结果和演化历史
- RKS 不自动裁决科学真理，也不应把 query-time inference 直接当作正式知识

从结构稳定性的角度看，这种定位的核心优点是：

**知识演化逻辑被制度化，而不是被算法化。**

也就是说，系统更接近：

```text
Agent 决策
      ↓
调用稳定的 RKS 操作与查询
      ↓
RKS 更新知识结构、审阅状态和演化历史
```

而不是：

```text
RKS 自动决定知识如何变化
```

## 当前架构中的演化基础

RKS 之所以已经具备建设知识演化系统的基础，不是因为它有一个宏大的愿景，而是因为它已经具备了关键事实层对象。

当前实现中已经存在：

- `Paper`
- `Claim`
- `Concept`
- `Method`
- `Dataset`
- `Hypothesis`
- `Edge`
- `Artifact`
- `Task`

这些对象的作用大致可以概括为：

- `Paper` 是证据锚点
- `Claim` 是最小结构化命题单元
- `Concept` 是概念归一化与主题聚合锚点
- `Hypothesis` 是项目级研究判断对象
- `Edge` 是正式图关系
- `Artifact` 与 `Task` 提供过程可追溯性

更重要的是，当前系统已经建立了一个非常关键的边界：

- `inferred_relations` 属于查询时推断候选
- `reviewed_relations` 属于经过 promote 后的正式图事实

这条边界意味着 RKS 已经不是“自动写知识”的系统，而是“区分候选与正式知识”的治理系统。

## 核心原则

### 1. 正式知识层必须保持 paper-grounded

RKS 可以围绕 `Concept`、`Hypothesis` 或 `Project` 做聚合、排序和总结，但正式知识层仍应回到 `Paper`、`Claim`、`Evidence` 和显式审阅动作。

这意味着：

- `Concept` 可以是聚合锚点
- `Hypothesis` 可以是项目判断对象
- `Project` 可以决定工作流视角
- 但正式事实不应脱离 paper-backed evidence 独立漂浮

### 2. 候选关系与正式关系必须分层

知识演化系统不能把“模型推断出的关系”和“经审阅确认的事实”混在一起。

当前 RKS 已经开始这样做：

- 查询时生成 `supports / contradicts / refines` 候选
- 审阅后将正式关系持久化到 `edges`

下一步应当把这套能力进一步制度化，而不是继续停留在 query-time 推断层。

### 3. 演化首先是时间问题，其次才是图问题

如果系统只能回答“现在有哪些关系”，却不能回答“关系何时出现、何时被确认、何时被撤销”，那它仍然只是一个静态研究图，而不是真正的知识演化系统。

### 4. 冲突是研究信号，不是噪音

研究系统不应只围绕支持关系组织知识，也应显式捕捉挑战、矛盾、分歧和未解决 tension。

对 discovery 来说，争议结构往往比共识更有价值。

## 面向当前架构的演化原语

原先把知识演化抽象为 `Propose / Support / Challenge / Revise / Deprecate / Synthesize` 有启发，但对当前 RKS 来说，应该改写成更贴近现有系统的原语集合。

### 当前已存在或基本成立的原语

- `ingest_paper`
- `extract_claims`
- `import_claims_for_paper`
- `link_claim_to_concept`
- `inspect_claim_relations`
- `promote_claim_relation`
- `retract_claim_relation`
- `add_project_link`
- `add_hypothesis_evidence`
- `query_evidence_for`
- `generate_grounded_output`

这些操作的共同点是：

- 都建立在现有 CLI、HTTP 和 operations layer 之上
- 都不要求 agent 直接改数据库
- 都保持了事实层与推断层的边界

### 下一阶段应新增的演化原语

- `materialize_claim_relation_candidates`
- `record_evolution_event`
- `build_concept_timeline`
- `cluster_claim_conflicts`
- `refresh_hypothesis_evolution`
- `rank_review_priorities`

这些原语才是 RKS 从“结构化研究图”走向“知识演化系统”的关键补充。

## 当前不应直接承诺的原语

有些概念在长期上有吸引力，但不应直接写成当前架构下的正式承诺：

- `propose_claim`
- `revise_claim`
- `deprecate_claim`
- `merge_claims`
- `create_theory`

原因不是这些方向不值得做，而是当前 RKS 的事实入口和治理模型还不支持把 Claim 当作可频繁编辑、分支、合并的对象。

在现阶段：

- `Claim` 更适合作为 paper-grounded 的结构化抽取对象
- `Hypothesis` 更适合作为 agent 主动提出的研究判断对象
- 更高层综合能力应优先通过 `Project` 和 grounded outputs 承接

## 知识演化的三种结构动力

在当前 RKS 中，知识演化可以先被理解为三种结构变化，而不是更复杂的理论化对象。

### 1. Expansion

新的论文进入系统，新的 Claim、Method、Dataset、Concept 被提取并连接，研究图谱扩大。

这一层当前已经成立。

### 2. Tension

不同 Claim 之间出现 `contradicts`、局部不一致、证据竞争或解释分歧，系统开始出现张力结构。

这一层当前部分成立：

- query-time contradiction inference 已存在
- reviewed contradiction edges 已存在
- disagreement outputs 已存在

但还缺少可持久化的 candidate layer 和 conflict clustering。

### 3. Stabilization

多个 Claim 在同一主题下形成稳定支持结构，系统开始出现较强共识或较稳定的 project-level 判断。

这一层当前已有雏形：

- `papers_supporting`
- `evidence_for`
- `hypothesis_evidence_links`
- grounded answer / brief / compare / opportunities

但仍缺少 timeline、consensus score 和长期演化视图。

## RKS 不做什么

为了保持结构稳定，RKS 当前不应自动做这些事情：

- 不自动判定 Claim 是否为真
- 不自动删除历史 Claim
- 不自动把局部支持结构提升为正式理论对象
- 不自动把 query-time candidates 当作正式知识

这些判断应由：

- 外部 agent
- 审阅工作流
- 项目上下文
- 后续演化查询和研究输出层

共同完成。

RKS 负责保证的是：

- 结构一致性
- 证据可追溯性
- 候选与正式事实分层
- 演化历史可回放

## 下一步最关键的三层

要让当前 RKS 真正进入知识演化阶段，最值得补齐的不是更多抽象对象，而是以下三层。

### 1. Candidate Layer

建议把当前 query-time claim relation inference 物化为可治理候选层，例如：

- `claim_relation_candidates`

这一层应至少支持：

- 候选关系缓存
- 关系打分
- 算法版本记录
- promote / reject / supersede 状态

这是将“推断”升级为“治理对象”的关键。

### 2. Event Layer

建议增加：

- `evolution_events`

用来记录：

- 关系候选首次生成
- 关系被 promote
- 关系被 retract
- hypothesis 置信度或状态变化
- concept 进入高争议状态

没有 event layer，系统只能看到静态结果，不能看到演化过程。

### 3. Timeline Layer

建议增加：

- `concept_timeline_snapshots`
- `hypothesis evolution views`

用来回答：

- 某个 Concept 的支持和反驳在过去几年如何变化
- 某个 Hypothesis 是变得更稳固还是更脆弱
- 哪些主题正在快速进入争议区

## 冲突图与发现系统

对当前项目来说，`Conflict Graph` 不是一个独立炫目的概念，而应成为 discovery engine 的核心输入。

这意味着未来的：

- `disagreements`
- `open-questions`
- `review-priorities`
- `opportunities`

不应只是输出模板，而应建立在以下结构上：

- reviewed contradictions
- relation candidates
- conflict clusters
- controversy density
- evidence gaps

只有这样，发现系统才会随着知识与审阅记录的积累而越来越强，而不是持续重复生成相似建议。

## 长期方向：从演化到谱系

如果要保留更长远的愿景，当前最值得写入的不是 `Theory Graph`，而是 `Lineage`。

原因是：

- `Theory` 作为对象在当前阶段过于抽象
- `Lineage` 更贴近当前已有的 Claim、Hypothesis 和 relation history
- `Lineage` 能自然连接 revision、supersession、controversy history 和 project memory

因此长期方向更适合表述为：

> RKS 的长期目标，是让研究主张、争议结构和项目假设形成可回放的知识谱系，而不是停留在一次性的检索或摘要结果上。

## 一句话总结

RKS 当前最正确的知识演化定位不是“知识的 Git”已经成立，而是：

> RKS 正在从一个结构化研究知识底座，演进为一个可审阅、可回放、可时间化的知识演化 substrate。

这一定义既保留了原始设计的野心，也更符合当前代码、存储和工作流的真实边界。

如果 RKS 设计好这个系统，它会变成 **人类历史上第一个可以计算“思想进化”的科研系统**。
