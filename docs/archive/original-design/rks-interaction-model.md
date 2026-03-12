如果把 **Research Knowledge Substrate (RKS)** 理解为一个研究知识的基础层，那么 **Agent Interaction Model** 的设计实际上决定了整个系统的使用方式。传统文献管理工具是以 UI 为中心的系统，人类通过界面直接操作数据；而你提出的 RKS 是一个 **agent-first system**，它的核心假设是：**AI agent 是主要操作者，人类只是提出研究问题并审阅结果**。因此，Agent Interaction Model 的设计本质上是在回答一个问题——**研究任务如何被拆解为一系列对 Research Graph 的结构化操作**。

在这种架构下，agent 并不是直接访问数据库，而是通过一层稳定的 **Research API / Skill Layer** 与系统交互。这一层非常关键，因为它既为 agent 提供高层语义操作，又保证底层数据结构不会被随意破坏。换句话说，Agent Interaction Model 的核心思想是：**agent 不直接操作数据结构，而是调用研究操作（Research Operations）**。

首先需要定义 RKS 中最基本的 **Research Actions**。这些动作并不是传统 CRUD，而是围绕研究流程设计的语义操作。例如，一个 agent 在阅读论文时需要执行的操作包括导入文献、提取 claim、关联概念以及建立引用关系。因此可以定义一组最基本的操作，例如：

```
add_paper
extract_claims
link_claim_to_concept
add_citation
add_method
add_dataset
```

这些操作实际上就是 **Research Graph 的构建原语（graph primitives）**。当 agent 阅读一篇新论文时，它并不会直接写数据库，而是调用这些 primitives，从而逐步扩展 Research Graph。例如 agent 执行如下流程：导入一篇论文对象，然后运行 claim extraction pipeline，将论文中的结构化结论写入 Claim 节点，随后识别论文涉及的概念，并建立 Claim 与 Concept 的关系边，最后将该论文与其引用文献连接起来。通过这种方式，研究知识逐渐沉积为一个结构化网络，而不是一堆孤立的 PDF 文件。

然而，仅有写入操作是不够的。Agent Interaction Model 更重要的一部分是 **研究查询能力（Research Query）**。研究问题通常具有复杂的结构，例如“哪些研究支持某个理论”“某种方法在哪些数据集上表现良好”“某个领域过去五年的主要研究趋势是什么”。这些问题本质上都是对 Research Graph 的结构查询。因此 RKS 应该为 agent 提供一组高层查询接口，例如：

```
find_claims_about(concept)
find_papers_supporting(claim)
find_methods_used_for(problem)
trace_citation_path(paper)
```

当 agent 接收到一个研究问题时，它会先把自然语言问题转化为一系列结构查询，然后再从图中组合证据并生成回答。这样的架构能够避免 LLM 仅依赖向量检索带来的信息幻觉，因为回答始终建立在显式结构关系之上。

在此基础上，可以进一步引入 **Research Workflows**。Research Workflows 是比单个操作更高层的任务模板，它描述了一个完整研究过程的步骤。例如，一个典型的文献综述 workflow 可能包括：首先检索与某个概念相关的论文，然后提取所有相关 claim，接着根据 claim 的支持与反驳关系对研究进行分组，最后生成一个结构化综述报告。对于 agent 来说，这样的 workflow 相当于一种“研究技能”，它把复杂任务拆解为多个原子操作。随着系统演化，可以逐渐积累一系列研究 workflows，例如自动生成研究地图、检测研究争议点、发现尚未解决的问题等。

在实际系统中，Agent Interaction Model 还需要解决一个重要问题，即 **写入安全性**。由于 agent 会自动生成结构化知识，如果没有约束机制，Research Graph 很容易被污染。因此系统应该引入一种简单但有效的治理机制，例如每个 Claim 节点必须附带证据来源，Graph 中的关系必须经过 schema 校验，并且系统可以维护多个版本的 Research Graph。这样即使 agent 产生错误提取，也不会破坏整体结构稳定性。

最后一个关键点是 **交互方式**。在一个 CLI + agent 的系统中，人类通常只需要提出研究目标，例如“总结 CRISPR base editing 的主要技术路线”，或者“寻找支持某种假设的实验结果”。Agent 会将这个目标拆解为一系列 Research API 调用，然后在 Research Graph 中收集证据，最后返回一个结构化答案。如果系统设计得当，人类甚至可以要求 agent 解释推理路径，例如列出支持结论的 claim、对应论文以及引用关系。这种可追溯的推理路径正是 RKS 相比传统向量检索系统的核心优势。

从结构稳定性的角度看，一个良好的 Agent Interaction Model 应当形成三层清晰分工：**Research Graph 作为知识结构层，Research API 作为稳定接口层，而 AI agent 作为推理与任务执行层**。这样的结构使得 agent 能够不断进化，而底层知识系统仍然保持稳定。

如果继续深化这个体系，下一步就会进入 RKS 设计中最关键的一个问题，因为它决定了整个系统的长期价值：**RKS 的 Knowledge Evolution System（知识演化系统）应该如何设计**。换句话说，当越来越多论文被摄取、越来越多 claim 被提取之后，系统如何自动识别知识冲突、研究共识以及潜在的新理论方向。
