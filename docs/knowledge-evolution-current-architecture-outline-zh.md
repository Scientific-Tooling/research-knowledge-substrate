# 知识演化文档改写提纲（面向当前架构）

## 目的

本文不是重新设计一个脱离现实的 `Knowledge Evolution System`，而是把 [docs/knowledge-evolution.md](docs/knowledge-evolution.md) 中最有价值的思想，翻译成一版适配当前 RKS 实现的改写提纲。

目标不是判断原文对错，而是回答三个更实际的问题：

- 原文哪些思想应当保留
- 这些思想在当前代码架构下应该如何重写
- 哪些概念现在还不适合直接进入正式设计文档

## 改写总原则

### 1. 保留“制度化演化”，不要写成“自动演化”

原文最重要的价值判断是：RKS 应该提供知识演化原语，而不是自动代替研究者做判断。

这一点应当保留，并改写为：

> RKS 的职责不是自动生成研究结论，而是把提出、支持、挑战、审阅、沉淀知识的过程制度化为可追溯结构操作。

这与当前项目已经实现的能力一致：

- `inferred_relations` 和 `reviewed_relations` 分离
- `promote-claim-relation` / `retract-claim-relation` 已存在
- `artifact`、`task`、`status` 已经构成可追溯的执行链

### 2. 保留“substrate”定位，但要贴近现有对象模型

原文强调 RKS 是 substrate，而不是自动科研机器，这个方向正确。

但在当前项目里，substrate 不是抽象空层，而是已经有明确对象边界的本地研究图系统。

因此建议改写为：

> RKS 是一个 agent-first 的本地研究知识底座。外部 agent 负责研究任务分解和判断，RKS 负责维护 paper-grounded 的知识对象、图关系、审阅结果和演化历史。

这里应显式写出当前已经存在的对象：

- `Paper`
- `Claim`
- `Concept`
- `Method`
- `Dataset`
- `Hypothesis`
- `Edge`
- `Artifact`
- `Task`

### 3. 所有演化能力都必须 paper-grounded

原文里的 primitive 很强，但表达上容易让人误解为“agent 可以直接凭空写知识”。

对于当前 RKS，这必须收紧。

建议在改写中明确：

> RKS 的正式知识层应保持 paper-grounded。外部 agent 可以提出候选解释、关系和项目判断，但正式进入知识图的内容应能够回溯到 `Paper`、`Claim`、`Evidence` 或显式的审阅动作。

## 原文核心思想的改写映射

下面按原文的重要概念，给出“保留什么”“如何改写”“当前不该怎么写”。

### 一、“RKS 是知识的 Git”

这是原文中最有冲击力的一句话，也是最需要谨慎改写的一句。

#### 应保留的意思

- RKS 的核心价值不在于自动判断真理
- RKS 的核心在于定义知识如何被提出、挑战、修订、审阅、保留历史
- RKS 更像知识演化机制，而不是知识生成器

#### 建议改写

不建议直接写“RKS 是知识的 Git”，因为这个比喻太强，容易把读者带向：

- 任意知识都可以像代码一样自由编辑
- 系统已经具备完整版本控制能力
- claim 已经支持完整 revision / merge / branch / revert 语义

当前更稳妥的改写方式是：

> RKS 的长期方向，是成为研究知识演化的版本化底座。

或者：

> RKS 试图为研究知识提供接近版本控制的治理机制，而不是把知识退化成一次性的摘要结果。

#### 当前不应直接声称

- 不应声称已经实现完整的“知识版本控制系统”
- 不应声称已经支持类似 Git 的 `merge`、`branch`、`revert` 完整语义
- 不应把这个比喻写成现状描述，更适合作为长期方向或设计愿景

### 二、Evolution Primitives

原文的 `Propose / Support / Challenge / Revise / Deprecate / Synthesize` 很有启发，但需要重新映射到当前系统。

#### 应保留的意思

- 演化应通过少量、明确、可审计的原语表达
- 外部 agent 应调用高层研究动作，而不是直接改数据库
- 知识演化应由显式动作推动，而不是由黑盒算法隐式决定

#### 当前架构下的改写方式

建议将原文 primitive 改写为两组。

第一组：当前已存在或接近存在的原语

- `ingest_paper`
- `extract_claims`
- `link_claim_to_concept`
- `inspect_claim_relations`
- `promote_claim_relation`
- `retract_claim_relation`
- `add_project_link`
- `add_hypothesis_evidence`

第二组：当前架构上应新增但尚未正式实现的演化原语

- `materialize_claim_relation_candidates`
- `record_evolution_event`
- `build_concept_timeline`
- `cluster_claim_conflicts`
- `refresh_hypothesis_evolution`

这种写法的好处是：

- 不脱离当前 CLI 和存储模型
- 能直接对应现有 operations layer
- 能自然形成后续 roadmap

#### 当前不应直接照搬的 primitive

- `propose_claim`
- `revise_claim`
- `deprecate_claim`
- `merge_claims`
- `create_theory`

这些概念不是不能做，而是当前系统还没有足够成熟的事实模型来承接。

### 三、Propose Claim

原文把 `propose_claim` 当作第一原语，但这与当前 RKS 的事实入口不一致。

#### 为什么不能直接照搬

当前 RKS 的 claim 主要来自：

- 论文导入后的 claim extraction
- agent-mode 的 claim import
- 与具体 `Paper` 关联的 evidence-backed claim persistence

也就是说，当前系统不是“自由命题系统”，而是“paper-grounded claim system”。

#### 建议改写

把 `propose_claim` 改写为：

- `extract_claims_for_paper`
- `import_claims_for_paper`
- `propose_hypothesis_for_project`

其中：

- `Claim` 继续是从证据源中提取出的结构化主张
- `Hypothesis` 才更适合作为 agent 主动提出的研究判断对象

这是非常关键的边界。

### 四、Add Evidence / Challenge Claim

这两项思想非常适合当前系统，而且几乎可以直接转译。

#### Add Evidence 的启发

当前系统已经有：

- `evidence_json`
- `papers_supporting`
- `hypothesis_evidence_links`

建议改写为：

> RKS 应允许围绕 Claim 和 Hypothesis 持续追加 evidence-backed links，并把这些链接视为知识演化的基础操作之一。

#### Challenge Claim 的启发

当前系统已经有：

- `contradicts`
- `reviewed_relations`
- `promote` / `retract`

建议改写为：

> 对 RKS 而言，challenge 不是自动裁决真伪，而是把结构张力显式写入候选层、审阅层和事件层。

这里最值得保留的是“张力”这个概念。

### 五、Revise / Deprecate / Merge Claims

这是原文里最容易误导实现方向的一组概念。

#### 原文的价值

- 它在强调知识不能被覆盖式更新
- 它在强调旧主张需要保留历史
- 它在暗示知识系统最终应支持版本化与谱系化

#### 当前架构下更适合的改写

不要把它们写成“立即可实现的 claim 编辑语义”，而应写成“未来的 lineage / supersession / status 模型方向”。

更适合当前项目的表达是：

> 在现阶段，RKS 更适合通过 `candidate`、`reviewed edge`、`evolution event` 和 `project-scoped acceptance` 表达知识状态变化，而不是直接把 Claim 设计成可频繁编辑和重写的对象。

这样既保留了原文的长期方向，也不误导当前实现。

### 六、Create Theory / Synthesize

原文把 Theory Graph 作为一层独立结构，这在长期上有吸引力，但当前不应优先落地。

#### 应保留的意思

- 多个 claim 可以组成更高层研究判断
- 系统不应永远停留在局部 claim 关系
- 用户最终关心的是主题判断、共识结构、理论方向和研究问题

#### 当前架构下的改写

当前不建议引入 `Theory` 作为正式一等对象。

更适合的承接层是：

- `Hypothesis`
- `Project`
- `research outputs`

因此建议改写为：

> 在当前阶段，RKS 先通过 `Hypothesis`、`Project` 和 grounded research outputs 承接高层综合能力，而不是直接引入新的 Theory object model。

### 七、Knowledge Timeline / Evolution Log

这是原文最值得直接吸收的部分之一。

#### 应保留的意思

- 没有时间历史，就没有真正的知识演化
- 知识系统不仅要回答“现在有什么”，还要回答“何时发生了什么变化”
- 事件日志比一次性的静态图更接近研究过程

#### 当前架构下的改写

建议明确转译为：

- `evolution_events`
- `claim_relation_candidates`
- `concept_timeline_snapshots`
- `hypothesis evolution views`

这组概念与当前 [docs/knowledge-evolution-design-zh.md](docs/knowledge-evolution-design-zh.md) 已经形成的方向一致，应视为优先级最高的吸收点。

### 八、Conflict Graph / Knowledge Tension

这也是原文极有价值的部分。

#### 应保留的意思

- 冲突不是噪音，而是研究最重要的信号之一
- 系统不只应聚合支持证据，也应显式聚合冲突结构
- discovery engine 的重要输入应来自争议密度和未解决 tension

#### 当前架构下的改写

建议改写为：

> RKS 应把 conflict / controversy 视为 discovery 的核心输入，并围绕 claim relation candidates、reviewed contradictions、conflict clusters 与 concept timeline 构建争议分析能力。

这也能自然连接当前已有的：

- `disagreements`
- `open-questions`
- `review-priorities`

## 建议的文档重写结构

如果要把 [docs/knowledge-evolution.md](docs/knowledge-evolution.md) 改写成适配当前项目的版本，建议结构如下。

### 1. 重新定义系统角色

建议标题：

`RKS 是知识演化的 substrate，而不是自动科研系统`

这一节要明确：

- 外部 agent 负责研究决策
- RKS 负责事实对象、审阅流程、演化历史、结构查询
- 正式知识层保持 paper-grounded

### 2. 描述当前已具备的演化基础

应写清：

- Claim 是结构化命题
- reviewed / inferred relation 已分离
- promote / retract 已存在
- hypothesis / project 已存在
- artifacts / tasks / outputs / operations 已存在

这会让整篇文档建立在真实代码基础上，而不是悬浮设计。

### 3. 定义面向当前架构的演化原语

建议只写两类：

- 已实现原语
- 下一阶段应新增的原语

避免一上来定义大量当前无法落地的抽象操作。

### 4. 明确当前最缺的三层

建议聚焦：

- candidate layer
- event layer
- timeline layer

这三层才是从“静态研究图”走向“知识演化系统”的关键。

### 5. 把发现系统建立在演化之上

这一节要明确：

- `disagreements`
- `open-questions`
- `review-priorities`
- `opportunities`

这些高层输出不应只是模板，而应建立在演化结构之上。

### 6. 把长期方向收束为 lineage，而不是 Theory Graph

如果要保留愿景部分，建议把重点放在：

- claim lineage
- hypothesis evolution
- controversy history
- research memory

而不是优先引入 `Theory` 这种当前过早抽象化的对象。

## 可直接保留的关键词

原文中这些关键词非常有价值，建议在改写后继续保留：

- substrate
- evolution primitives
- knowledge history
- knowledge tension
- conflict graph
- timeline
- evolution log
- lineage

## 建议弱化或延后的关键词

原文中这些词不适合直接作为当前版本的正式系统承诺：

- knowledge Git
- revise claim
- deprecate claim
- merge claims
- theory graph
- system belief at time T

这些概念可以保留为长期研究方向，但不应写成当前设计已准备落地的能力。

## 一句话总结

如果把 [docs/knowledge-evolution.md](docs/knowledge-evolution.md) 改写成适配当前 RKS 的版本，最重要的不是删掉它的野心，而是把它的野心重新锚定到当前已经存在的对象、边界和治理模式上。

对当前项目最正确的翻译不是：

> RKS 直接成为知识的 Git。

而是：

> RKS 正在从一个结构化研究底座，演进为一个可审阅、可回放、可时间化的知识演化 substrate。