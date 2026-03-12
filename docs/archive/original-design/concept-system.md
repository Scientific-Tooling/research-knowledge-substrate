如果 **Research Knowledge Substrate (RKS)** 的核心是 **Claim Graph**，那么 **Concept System** 就相当于这张图的“坐标系”。没有稳定的 Concept 体系，Claim 很快会碎裂成大量无法合并的节点，例如 “Transformer”、“Transformers”、“Transformer model”、“attention-based architecture”等都会被当成不同对象，整个图谱的结构稳定性会迅速崩塌。因此 Concept System 的设计目标并不是做一个完美的学术本体论，而是建立一个 **稳定、可扩展、可自动维护的概念结构**，使 Research Graph 在规模增长时仍然保持可组织性。

从结构角度看，Concept System 可以被理解为 **研究领域的语义骨架（semantic backbone）**。它必须满足三个条件：首先，概念数量不能无限膨胀，否则系统会失去聚合能力；其次，概念之间必须有明确的层级关系，这样 agent 才能在不同抽象层级上进行推理；最后，概念必须能够自动对齐新论文中的术语，否则系统会需要大量人工维护。因此，一个适合 RKS 的 Concept System 可以被设计为 **三层结构 + 一套规范化机制**。

---

# 一、Concept 的三层结构

为了保持结构稳定性，Concept 不应该是扁平集合，而应该形成一个简单但稳定的层级体系。一个非常有效的设计是 **Domain → Concept → Instance** 三层模型。

```
Domain
  └── Concept
        └── Instance
```

**Domain** 表示研究领域的宏观类别，例如 “Machine Learning”、“Computer Vision”、“Genomics”、“Protein Structure Prediction”。Domain 的数量通常很少，并且变化很慢，它的作用是让系统在宏观层面上保持结构秩序。

**Concept** 是领域中的稳定学术概念，例如 “Transformer”、“Diffusion Model”、“Graph Neural Network”、“Self-Supervised Learning”。这些概念是研究讨论的主要对象，也是 Claim 中最常见的 Subject 或 Object。

**Instance** 则表示具体实现或变体，例如 “Vision Transformer”、“Stable Diffusion”、“AlphaFold”。Instance 连接具体论文或方法，而 Concept 保持更抽象的层级。

这样的结构允许系统既保持抽象稳定，又能容纳不断出现的新方法。

---

# 二、Concept 的基本结构

一个 Concept 节点可以具有如下字段：

```
Concept
  id
  name
  aliases
  description
  domain
  parent
```

其中 **aliases** 是非常关键的字段，因为科学论文中同一个概念往往会出现多种表达方式。例如：

```
Concept: Transformer
aliases:
  transformer model
  transformers
  attention-based model
```

通过 alias 机制，系统可以把不同术语映射到同一个 Concept，从而避免图谱碎裂。

---

# 三、Concept 层级关系

Concept 之间应该允许形成简单的层级结构：

```
Concept --is_a--> Concept
Concept --part_of--> Concept
Concept --related_to--> Concept
```

例如在机器学习领域可能形成这样的结构：

```
Machine Learning
  └── Neural Network
        ├── Convolutional Neural Network
        ├── Recurrent Neural Network
        └── Transformer
```

而 Transformer 又可能进一步细分：

```
Transformer
  ├── Vision Transformer
  ├── Sparse Transformer
  └── Decoder-only Transformer
```

这种层级结构的好处是 agent 可以在不同抽象层级进行查询，例如：

“所有 neural network 方法有哪些？”
或者
“Transformer 的变体有哪些？”

---

# 四、Concept 与 Claim 的连接

Concept System 的存在，是为了让 Claim Graph 具有语义结构。Claim 中的 subject 和 object 应当尽量链接到 Concept。

例如：

```
Claim:
Diffusion models outperform GANs in image generation
```

在图结构中会变成：

```
Claim
  subject → Concept: Diffusion Model
  object → Concept: GAN
```

这样系统就可以聚合所有关于 Diffusion Model 的研究主张。

---

# 五、Concept Normalization（概念规范化）

自动提取 Claim 时最大的挑战之一是 **术语不一致**。Concept System 必须有一套规范化流程，使新的术语能够自动映射到现有概念。

一个典型的流程可能是：

```
term detection
 ↓
alias matching
 ↓
concept similarity
 ↓
concept creation (if needed)
```

例如当系统遇到：

```
"attention-based architecture"
```

它可能通过 alias 或 embedding similarity 判断该术语与 “Transformer” 概念相似，从而进行链接。

如果无法匹配，系统才会创建新的 Concept。

---

# 六、Concept 的自动增长

Concept System 不可能一次性设计完成，因此它必须支持 **渐进式增长**。新论文进入系统时可能会带来新的概念，例如新的模型架构或算法名称。

为了保持结构稳定，可以设定一些规则，例如：

1. 新概念必须属于某个 Domain
2. 新概念必须指定 parent Concept
3. Instance 不自动升级为 Concept

这样系统可以避免概念爆炸。

---

# 七、Concept Graph 的作用

当 Concept System 稳定运行后，Research Knowledge Substrate 会形成两张相互叠加的图：

```
Concept Graph
Claim Graph
```

Concept Graph 提供领域结构，而 Claim Graph 提供知识内容。例如：

```
Transformer
   ↑
   │
Claim: Transformers scale with model size
```

随着时间推移，系统可以分析：

* 哪些概念的 Claim 增长最快
* 哪些概念之间关系最紧密
* 哪些概念形成新的研究方向

这实际上会形成一种 **研究领域演化图（scientific evolution graph）**。

---

# 八、为什么 Concept System 必须简单

很多知识图谱项目失败的原因，是试图建立过于复杂的本体系统。对于 RKS 来说，Concept System 的目标不是做一个完整的科学 ontology，而是提供 **最小但稳定的语义锚点**。

只要 Concept 能够：

1. 聚合相同研究对象
2. 建立简单层级关系
3. 规范术语表达

整个 Claim Graph 就能够保持长期结构稳定。
