如果 **Research Knowledge Substrate (RKS)** 的数据层已经形成三种核心结构——**Concept Graph、Claim Graph、Paper Graph**——那么系统的真正价值并不在于“存储知识”，而在于 **如何在这些结构之上进行研究级查询与推理**。因此 RKS 的 Query / Reasoning Engine 本质上不是传统数据库查询引擎，而是一个 **Research Reasoning Layer**：它需要能够理解研究问题、在图结构中导航、整合证据，并最终生成可解释的研究结论。

从结构稳定性的角度看，这个引擎不应该试图实现复杂的 AI 推理系统，而是应当构建一个 **分层推理架构**。也就是说，将研究查询拆解为一系列稳定、可组合的操作，让 agent 通过这些操作完成更复杂的分析任务。一个非常有效的设计是 **三层查询体系：Graph Query → Semantic Retrieval → Reasoning Layer**。

---

# 一、Query / Reasoning Engine 的总体结构

整个系统可以被理解为一个逐层收敛的信息处理过程：

```
User / Agent Query
        ↓
Query Planner
        ↓
Graph Query Layer
        ↓
Semantic Retrieval Layer
        ↓
Reasoning Layer
        ↓
Structured Answer
```

每一层解决不同的问题。Graph Query 负责精确结构查询，Semantic Retrieval 负责语义搜索，而 Reasoning Layer 则负责整合这些信息形成研究级回答。

---

# 二、Graph Query Layer

Graph Query Layer 是整个系统中最稳定的一层，它直接在 Research Graph 上执行结构查询。这一层类似于数据库查询语言，但语义是研究对象。

例如系统应当支持如下基本查询：

```
find claims about <concept>
find methods proposed by <paper>
find datasets used by <method>
find papers supporting <claim>
```

这些查询本质上是 **graph traversal**。例如：

```
Concept → Claim → Paper
```

查询：

```
find claims about Transformer
```

可能执行：

```
MATCH (c:Concept{name="Transformer"}) 
←[:about]-
(cl:Claim)
RETURN cl
```

这一层的特点是：

* 精确
* 可解释
* 可组合

但它的局限是：它只能回答**结构化问题**。

---

# 三、Semantic Retrieval Layer

很多研究问题并不是精确结构查询，例如：

“有哪些论文提出了 transformer 的替代方案？”

这种问题需要语义搜索。因此系统需要一个 **embedding-based retrieval layer**。

流程通常是：

```
query embedding
      ↓
vector search
      ↓
retrieve claims / papers
```

例如：

```
query: alternatives to transformers
```

系统可能检索到：

```
Claim:
Mamba provides an alternative architecture for sequence modeling

Claim:
RWKV combines RNN and transformer features
```

Semantic Retrieval 的作用是：

* 发现相关知识
* 补充 graph 查询

它为 Reasoning Layer 提供候选信息。

---

# 四、Reasoning Layer

Reasoning Layer 是 Query Engine 中最关键的一层。它的作用不是“搜索”，而是**组织研究证据**。

在研究问题中，推理通常包括三个步骤：

1. 找到相关 Claim
2. 判断这些 Claim 的关系
3. 综合成结论

例如一个查询：

```
What are alternatives to transformers?
```

系统可能执行：

Step 1
搜索 Concept：

```
Transformer
```

Step 2
寻找相关 Claim：

```
Claim:
State space models can replace transformers

Claim:
RWKV combines RNN and attention mechanisms
```

Step 3
聚合 Method：

```
Method:
Mamba
RWKV
Linear RNN
```

最后生成结构化答案：

```
Alternative architectures to transformers include:

1. State Space Models (e.g., Mamba)
2. Hybrid RNN-transformer models (e.g., RWKV)
3. Linear attention models
```

Reasoning Layer 的核心是 **graph-aware synthesis**。

---

# 五、Query Planner

为了让系统支持复杂研究问题，需要一个 **Query Planner**。它的作用是把自然语言研究问题分解为一系列 graph operations。

例如问题：

```
Which methods outperform GANs in image generation?
```

Query Planner 可能生成如下步骤：

```
1 find claims where predicate = outperform
2 filter object = GAN
3 filter context.task = image generation
4 retrieve associated methods
```

然后执行：

```
Claim → Paper → Method
```

这种结构使 agent 可以系统化地进行研究分析。

---

# 六、Research Reasoning Patterns

在研究环境中，有几类查询模式会频繁出现，因此 Query Engine 应该内置这些 **reasoning templates**。

例如：

### Evidence aggregation

```
find evidence supporting claim X
```

### Method comparison

```
compare methods for concept Y
```

### Contradiction detection

```
find claims contradicting claim X
```

### Research trend analysis

```
find concepts with increasing claims
```

这些模式可以构成一个 **Research Query DSL**。

---

# 七、Research Query DSL

为了让 agent 更容易使用 RKS，可以定义一个简单的 DSL，例如：

```
claims about <concept>

methods for <task>

papers supporting <claim>

compare methods for <task>
```

例如：

```
rks query claims about "diffusion models"
```

或：

```
rks query compare methods for image generation
```

DSL 的好处是：

* agent 容易生成
* 查询可解释
* 结构稳定

---

# 八、证据驱动的回答结构

Reasoning Engine 输出不应该只是文本，而应该是 **Evidence-backed answer**。

例如：

```
Conclusion:
Diffusion models outperform GANs in image generation.

Supporting Evidence:
Paper A
Paper B
Paper C
```

这种结构对于科学研究非常重要，因为每个结论都可以追溯到 Claim 和 Paper。

---

# 九、长期演化后的能力

当 Claim Graph 逐渐扩大之后，Query Engine 会逐渐获得一些非常强大的能力，例如：

**Research landscape mapping**

```
map research area diffusion models
```

**Scientific debate detection**

```
find competing claims about scaling laws
```

**Knowledge synthesis**

```
summarize methods for protein folding
```

在这个阶段，RKS 实际上会成为一种 **AI-native research infrastructure**。

---

# 十、一个非常关键的设计原则

为了保证系统长期稳定，Query Engine 必须遵循一个原则：

**所有推理都应当以 Claim Graph 为基础，而不是直接基于论文文本。**

换句话说：

```
Text → Claim → Reasoning
```

而不是：

```
Text → Reasoning
```

这样系统的推理过程才能保持可解释性和可追溯性。
