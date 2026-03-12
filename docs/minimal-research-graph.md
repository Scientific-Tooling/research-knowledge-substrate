如果我们希望 **Research Knowledge Substrate (RKS)** 成为一个长期稳定的研究基础设施，那么 **Minimal Research Graph (MRG)** 的设计必须遵循一个非常重要的原则：**图模型必须足够小，以保证结构稳定；但表达能力必须覆盖科学研究的基本逻辑结构**。换句话说，这个图不是要表达所有细节，而是要抓住科学活动中最核心的关系骨架，使得 AI agent 能够在其上进行推理、搜索和综合。

从科学研究的结构本质来看，一篇论文实际上在做三件事：提出某种 **主张（claim）**，使用某种 **方法（method）**，并通过 **证据（evidence，例如数据或实验）**来支持这些主张。论文只是承载这些内容的容器。因此，一个稳定的最小研究图必须围绕 **Claim—Method—Evidence** 这一三角结构展开，而 Paper 只是连接这些对象的来源节点。

---

# 一、Minimal Research Graph 的核心节点

MRG 的节点类型可以被严格限制为五种，这样既保持极简，又能表达研究结构。

```
Paper
Claim
Method
Dataset
Concept
```

这五种节点实际上对应五种不同层级的研究对象。

**Paper** 是文献来源节点，它记录论文的元数据与引用关系，但并不直接承担知识表达的主体角色。

**Claim** 是研究结论或科学主张，是整个系统最重要的节点。科学知识在本质上是由一系列可被支持或反驳的主张构成的，因此 Claim 是知识图谱中的核心。

**Method** 描述论文提出或使用的技术方法，它连接研究问题与研究结果。

**Dataset** 是经验性证据来源，它使研究主张可以被验证。

**Concept** 是领域概念，例如 “Transformer”、“Diffusion Model”、“Self-Supervised Learning”。Concept 的作用是形成知识分类结构，使图谱不会退化为无序文本。

---

# 二、Minimal Research Graph 的核心关系

在一个研究图中，如果关系过多，系统很快会变得不可维护；如果关系过少，又无法表达研究结构。因此我们需要选择一组**结构稳定且普遍存在的关系类型**。

最小关系集合可以是：

```
Paper --cites--> Paper

Paper --contains--> Claim
Paper --proposes--> Method
Paper --uses--> Dataset

Claim --about--> Concept
Method --about--> Concept

Claim --supported_by--> Paper
Claim --contradicts--> Claim

Method --evaluated_on--> Dataset
```

这些关系形成一个非常清晰的研究逻辑结构。

例如，一篇论文可以：

* 提出一个方法
* 声称一个结论
* 使用一个数据集
* 引用之前的研究

而不同论文之间的 Claim 又可以互相支持或互相矛盾，从而形成科学讨论网络。

---

# 三、研究图的最小结构模式

如果我们把上述节点与关系组合起来，就可以得到一个非常典型的研究结构模式：

```
          Concept
             ↑
             │
          Claim
             ↑
             │ supported_by
           Paper
          /   \
         /     \
    proposes   uses
      /           \
   Method        Dataset
      |
      |
    Concept
```

这个结构模式之所以重要，是因为它与科学研究的逻辑结构高度一致：概念定义研究领域，方法提供研究工具，数据提供证据，而论文将这些元素组织成可传播的知识。

---

# 四、Claim 中心化的知识结构

在 MRG 中，Claim 是整个系统的中心节点。一个研究领域实际上可以被看作是一个 **Claim Network**。

例如在深度学习领域，可能会出现这样的结构：

```
Claim A:
Transformers scale well with model size

Claim B:
Diffusion models outperform GANs in image generation

Claim C:
Sparse attention improves transformer efficiency
```

这些 Claim 可以通过关系连接：

```
Claim C --supports--> Claim A
Claim B --contradicts--> Claim D
```

随着论文不断进入系统，Claim 网络会逐渐形成一张**科学知识演化图**。

这种结构对于 AI agent 特别重要，因为 agent 可以执行如下推理任务：

* 找到支持某个主张的论文
* 找到反驳某个主张的研究
* 分析一个领域的共识结构

---

# 五、Concept 作为领域结构

如果没有 Concept 节点，图谱很容易退化成大量无序 Claim。Concept 的作用是提供一种稳定的领域分类结构。

例如：

```
Concept:
Transformer
Diffusion Model
Reinforcement Learning
Scaling Law
```

Claim 与 Method 都可以连接到 Concept：

```
Claim --about--> Transformer
Method --about--> Diffusion Model
```

这样系统就可以回答一些重要问题，例如：

“Transformer 相关的所有研究主张是什么？”

或者：

“Diffusion Model 相关的方法有哪些？”

---

# 六、Minimal Research Graph 的形式化定义

如果用更形式化的方式描述，MRG 可以表示为：

```
Nodes:
  Paper
  Claim
  Method
  Dataset
  Concept

Edges:
  cites
  contains
  proposes
  uses
  about
  supported_by
  contradicts
  evaluated_on
```

这是一个**非常小但表达能力极强的 schema**。

它的优势在于：

1. **结构稳定**
2. **适合自动提取**
3. **适合 agent 推理**

---

# 七、MRG 如何支持 AI Agent

当这个研究图逐渐增长时，AI agent 就可以执行许多高级研究任务。

例如：

**研究地图**

```
find all claims about diffusion models
```

**方法比较**

```
compare methods for image generation
```

**科学争议分析**

```
find claims contradicting claim X
```

**研究趋势**

```
find concepts with rapidly increasing claims
```

这实际上让系统从“文献管理”升级为“研究知识分析平台”。

---

# 八、为什么这是“最小”模型

MRG 的设计目标不是表达所有科学细节，而是抓住科学研究的骨架结构。只要系统能够表达：

* 研究主张
* 方法
* 数据证据
* 概念分类
* 文献来源

那么几乎所有研究活动都可以映射到这个图中。

换句话说，MRG 是一种 **科学知识的最小可计算表示（minimal computable representation of research knowledge）**。
