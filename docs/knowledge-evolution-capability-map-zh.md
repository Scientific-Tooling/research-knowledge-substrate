# 知识演化与发现系统能力地图

## 目的

本文将 `Knowledge Evolution and Discovery System` 拆解为一张分层能力地图，用来回答三个产品与架构问题：

- 哪些能力属于系统成立所必需的基础能力
- 哪些能力能够构成与普通研究工具的差异化能力
- 哪些能力一旦做深，会形成长期护城河能力

这里的“能力地图”不是功能清单，也不是版本计划，而是一个面向产品定位、架构优先级和长期竞争力判断的分层模型。

## 核心判断

对 RKS 来说，`Knowledge Evolution and Discovery System` 不是一个附加模块，而是系统最有潜力形成壁垒的高层能力。

但它不能脱离底层成立。更准确地说：

- 基础能力决定系统是否可靠可用
- 差异化能力决定系统是否区别于普通检索与摘要工具
- 护城河能力决定系统是否会随着数据积累和工作流沉淀而越来越强

因此，这三层不是互相替代关系，而是递进关系。

## 总体能力地图

```text
护城河能力
  知识演化建模
  研究发现引擎
  项目级研究判断与持续学习

差异化能力
  结构化研究图
  可审阅的 claim relation 治理
  grounded research outputs
  演化视角查询与研究工作流

基础能力
  ingest / extract / normalize / persist / inspect / query
  可追溯 artifact
  稳定 CLI / HTTP / agent-facing operations
```

## 一、基础能力

基础能力回答的问题是：系统能否稳定地把研究材料转成可追溯、可查询、可复用的研究对象。

如果这一层不成立，演化和发现都只会是脆弱的幻觉。

### 1. 文献摄取与对象落库

能力内容：

- ingest 本地 PDF、DOI、arXiv、PMID、canonical URL
- 建立稳定 paper ID
- 保存源文件、元数据与中间 artifact

这层能力的价值在于把“论文文件”变成系统中的稳定对象入口。

当前状态：已实现。

对应现状可见于 [README.md](README.md)、[docs/progress.md](docs/progress.md)。

### 2. 结构化抽取

能力内容：

- 提取 text、sections、claims、methods、datasets
- 形成可检查的中间产物
- 支持 `llm-api` 与 `agent` 双轨模式

这层能力的价值在于把非结构化文献内容转成后续图谱和推理可消费的结构化对象。

当前状态：已实现，且已具备较强工程实用性。

### 3. 概念归一化与对象连接

能力内容：

- 规范化 concept 名称与 alias
- 将 claim、method、dataset 等对象挂接到 concept
- 建立 `about`、`contains`、`proposes`、`uses`、`evaluated_on`、`cites` 等边

这层能力的价值在于防止知识被文本别名打碎。

当前状态：已实现，但 concept hierarchy 仍较浅。

### 4. 可追溯存储与事实边界

能力内容：

- 保留 artifact lineage
- 保存 evidence、offset、task status、schema version
- 区分 query-time inference 与 reviewed facts

这层能力的价值在于为后续知识演化提供可信的事实边界。

当前状态：已实现，是当前系统的一项重要工程优势。

### 5. 稳定的 agent-facing operations

能力内容：

- 稳定 CLI
- 稳定 HTTP surface
- 独立 operations layer
- agent 可调用的审阅与查询动作

这层能力的价值在于让系统不只是“能存数据”，而是能被 agent 安全使用。

当前状态：已实现。

### 基础能力的产品地位

这一层不是核心竞争力本身，但它决定了系统有没有资格去做更高层能力。

如果没有这一层，RKS 无法成为真正的研究 substrate。

### 基础能力的竞争判断

这一层重要，但不构成强护城河。

原因：

- 同类系统也可以实现 ingest、extract、search、summary
- 很多能力属于“必须有”，而不是“只有你有”
- 它们更多是进入比赛的门票，而不是最终胜负手

对 RKS 而言，基础能力的目标不是追求炫技，而是追求：

- 稳定
- 可追溯
- agent-friendly
- 足够严格地区分事实与派生结果

## 二、差异化能力

差异化能力回答的问题是：为什么 RKS 不只是另一个 PDF 工具、RAG 工具或研究摘要器。

这一层开始真正体现系统的独特性。

### 1. Structured Research Graph

能力内容：

- 不以 paper 为唯一核心单位
- 以 `Claim / Concept / Method / Dataset / Hypothesis` 为一等对象
- 支持围绕 concept 和 claim 进行 evidence aggregation

这层能力的重要性在于，它把系统从“文档系统”提升为“研究知识系统”。

差异化点：

- 多数工具停留在 document chunk 层
- RKS 把 Claim 作为可计算知识单元
- RKS 把 Concept 作为语义锚点

当前状态：已基本成立。

### 2. 可审阅的 Claim Relation 治理

能力内容：

- 区分 `inferred_relations` 与 `reviewed_relations`
- 支持 promote / retract
- 支持 agent 在稳定接口上完成知识审阅

这层能力的重要性在于，它把“LLM 推断”变成了“可治理知识流程”。

差异化点：

- 普通系统只做推断，不治理推断
- RKS 已经明确把 query-time candidate 和 durable fact 区分开
- 这使知识图不会因为自动抽取而直接失控

当前状态：已成立，但治理层还偏窄。

### 3. Grounded Research Outputs

能力内容：

- 直接产出 answer、brief、disagreements、opportunities、reading-list、review-priorities
- 输出必须回指 claim、paper、method、dataset 等 evidence object
- 不把自由生成文本当作最终产品

这层能力的重要性在于，系统开始直接服务研究判断，而不是只暴露内部图状态。

差异化点：

- 普通工具返回摘要
- RKS 返回 evidence-backed research output
- 输出层和底层 graph/claim/evidence 是连通的

当前状态：已实现第一阶段。

### 4. 演化视角查询

能力内容：

- 查询 claim 关系
- 查看 concept 证据
- 暴露 disagreements、review priorities、open questions
- 为未来 timeline、consensus、controversy 查询预留路径

这层能力的重要性在于，它开始把“静态知识查询”推进到“动态研究判断”。

差异化点：

- 不是只问“有哪些论文”
- 而是问“知识之间是什么关系”“哪里有冲突”“哪里值得继续研究”

当前状态：部分成立，仍需补齐物化候选层和时间维度。

### 5. Agent-First Research Workflow

能力内容：

- 系统主要服务 agent 而不是重 UI 操作
- 工作流围绕 inspect、review、promote、query、output 展开
- 外部 agent 负责发现输入，RKS 负责治理和沉淀研究知识

这层能力的重要性在于，它明确了边界：RKS 不是通用 web agent，而是研究知识底座。

差异化点：

- 很多系统试图把所有事情塞进一个大模型工作流
- RKS 更强调 substrate、stable operations、governed facts

当前状态：已成立，是当前产品方向的鲜明特征。

### 差异化能力的产品地位

这一层已经构成 RKS 当前最清晰的产品差异化。

如果用户问：“为什么不用普通文献管理或 RAG？”答案主要来自这一层，而不是基础层。

### 差异化能力的竞争判断

这一层具备明显竞争力，但还不构成真正护城河。

原因：

- 竞争对手也可以模仿输出层和 review flow
- 目前很多高层能力还没有形成时间维度与持续学习闭环
- claim relation 治理虽然重要，但范围仍偏窄

换句话说，这一层让 RKS 变得“明显不同”，但还没有让它“越来越难被替代”。

## 三、护城河能力

护城河能力回答的问题是：随着数据、关系、审阅记录和研究项目不断积累，系统是否会越来越强，而不是只是在做重复性的摘要和检索。

这才是 `Knowledge Evolution and Discovery System` 真正的核心竞争力所在。

### 1. 知识演化建模

能力内容：

- 追踪 claim-to-claim 关系如何随时间出现、变化、被审阅确认
- 区分候选关系、正式关系、撤销关系、 superseded 关系
- 形成 concept 级别的 timeline、consensus、controversy 视图

这层能力的关键不在“有没有 supports / contradicts”，而在“能不能把这些关系当作一个长期演化系统来管理”。

为什么它是护城河：

- 需要稳定数据模型
- 需要长时间积累的 candidate / review / event 历史
- 需要事实层与派生层严格分离
- 需要持续重算与回放能力

当前状态：方向明确，但尚未完成产品化。

### 2. 研究发现引擎

能力内容：

- 自动发现争议密集区
- 自动发现证据稀薄区
- 自动发现方法与数据集覆盖空白
- 自动发现值得审阅和继续研究的问题

这层能力不是随意“生成灵感”，而是从结构化图和演化事实中推出新的研究机会。

为什么它是护城河：

- 它依赖长期积累的 claim graph
- 它依赖 reviewed relation 和冲突结构
- 它依赖 hypothesis 与 project context
- 它越用越强，因为历史和上下文会不断增厚

当前状态：已有 `opportunities`、`open-questions`、`review-priorities` 雏形，但还偏 output template，尚未成为完整 discovery engine。

### 3. 项目级研究判断与假设演化

能力内容：

- 围绕 hypothesis 追踪支持与挑战证据的变化
- 让 project context 参与演化优先级排序
- 让系统判断“下一步最值得补什么证据、审什么关系、读什么论文”

这层能力的意义在于，系统开始从 topic-level synthesis 走向 project-level research decision support。

为什么它是护城河：

- 它深度依赖用户真实工作流
- 它积累的是项目特有的判断历史，而不只是公共文献摘要
- 一旦形成项目记忆，迁移成本就会迅速提高

当前状态：已有 project 和 hypothesis 基础设施，但演化联动仍较早期。

### 4. 可审计的研究记忆

能力内容：

- 记录谁在何时 promote、retract、annotate、accept 了哪些关系或结论
- 记录某个趋势判断是由哪个版本算法在何时生成
- 记录研究输出背后的证据与审阅路径

这层能力的意义在于，系统不是“不断生成新文本”，而是在沉淀一套可审计研究记忆。

为什么它是护城河：

- 这类记忆很难靠一次性导入复制
- 它与团队、项目、研究习惯深度耦合
- 一旦长期累积，会形成明显的迁移壁垒

当前状态：artifact 和 task 基础已在，但还需要 evolution event layer 才能真正完整。

### 护城河能力的产品地位

这一层才是 RKS 最终应该占据的价值高地。

如果系统只做到差异化能力，它会是一个优秀的研究知识工具；如果系统把这一层做深，它才可能成为真正的研究基础设施。

### 护城河能力的竞争判断

这一层一旦成立，竞争优势会具备复利特征。

原因：

- 数据越多，争议和趋势判断越有价值
- 审阅越多，正式知识层越稳固
- 项目越多，假设演化和研究记忆越难迁移
- 输出越多，发现引擎就越能形成反馈闭环

这意味着护城河不是来自某个单点算法，而是来自：

- 长期沉积的结构化知识
- 审阅治理历史
- 项目上下文
- 演化事件与发现工作流

## 四、三层能力之间的依赖关系

### 基础能力是地基

没有 ingest、extract、normalize、persist、artifact、stable operations，就没有可信的事实层。

### 差异化能力是当前产品形态

结构化研究图、claim relation review、grounded outputs、agent-first workflow，使 RKS 已经区别于传统研究工具。

### 护城河能力是长期价值上限

知识演化建模、研究发现引擎、项目级研究判断，会决定 RKS 最终是一个“更好的工具”，还是一个“越来越强的研究系统”。

## 五、当前能力归类

基于当前代码与文档，RKS 的能力大致可以归类如下。

### 已经成立的基础能力

- 文献 ingest 与 source acquisition
- 可检查 extraction artifacts
- structured claim extraction
- concept normalization
- graph persistence
- hybrid search
- stable CLI / HTTP / operations
- task / status / artifact tracking

### 已经成立的差异化能力

- claim 为核心知识单元
- reviewed claim relation flow
- grounded research outputs
- agent-first product boundary
- project / hypothesis object model

### 正在形成中的差异化能力

- topic disagreements
- opportunities / open questions
- review priorities
- 更高层 research workflow templates

### 尚未真正做深的护城河能力

- materialized candidate evolution layer
- evolution events
- concept timelines
- consensus / controversy scoring
- conflict clustering
- hypothesis evolution tracking
- discovery engine driven by evolution structure
- durable research memory across projects and reviews

## 六、能力优先级判断

如果目标是尽快增强项目的核心竞争力，优先级不应平均分配，而应遵循下面的顺序。

### Priority A：补齐护城河的最小骨架

优先做：

- claim relation candidate materialization
- evolution event logging
- concept timeline snapshots

原因：

- 这三项是把“演化”从口号变成系统能力的最小条件
- 它们能直接提升 review、output、discovery 三条线

### Priority B：让 discovery 建立在 evolution 上

优先做：

- controversy-aware open questions
- evidence-gap driven opportunities
- review-priority ranking based on evolution state

原因：

- discovery 如果不建立在演化结构上，就很容易退化成泛泛的建议生成
- 只有基于 evolution state，发现能力才有积累性

### Priority C：把项目工作流接上去

优先做：

- hypothesis evolution
- project-scoped review priorities
- project memory and acceptance traces

原因：

- 一旦和真实研究项目绑定，系统的迁移成本和复利效应都会显著增强

## 七、对外表述建议

如果要对外描述 RKS，可以使用如下分层话术。

### 对基础层的表述

RKS 是一个 agent-first 的本地研究知识底座，能够把论文、Claim、Concept、Method、Dataset 和 Hypothesis 组织为可追溯的研究图。

### 对差异化层的表述

RKS 不只是检索论文和生成摘要，它把研究主张、证据关系和审阅动作变成可治理的知识流程，并直接产出 grounded research outputs。

### 对护城河层的表述

RKS 的长期目标不是做更聪明的摘要器，而是构建一个知识演化与发现系统，让研究结论、争议结构、假设变化和下一步研究机会随着时间持续沉积和增强。

## 结论

“知识演化与发现系统”应被视为 RKS 的高层核心竞争力，但它不是凭空成立的。它建立在一层已经较强的基础能力之上，通过一层已经初步成型的差异化能力，最终指向真正具备复利效应的护城河能力。

因此，对 RKS 的能力地图可以做如下总结：

- 基础能力让系统可用、可靠、可治理
- 差异化能力让系统明显不同于普通研究工具
- 护城河能力让系统随着知识、审阅和项目积累而越来越强

如果只做前两层，RKS 会是一个优秀的研究知识工具；如果第三层真正成立，RKS 才会成为一个难以替代的研究基础设施。