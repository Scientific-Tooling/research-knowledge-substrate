在 **Research Knowledge Substrate (RKS)** 的最小研究图中，Claim 是整个系统的核心节点，因此 Claim 不能只是“一段文本”。如果 Claim 只是自然语言句子，那么系统仍然停留在“可搜索文档”的层面；而如果 Claim 具有稳定的结构模型，那么 Claim 就可以成为 **AI agent 可以推理、比较、组合、甚至反驳的知识单元**。因此设计 **Structured Claim Model (SCM)** 的关键目标，是在保持表达能力的同时，使 Claim 具有**最小但可计算的语义结构**。

从科学研究的逻辑结构来看，一个科学主张通常包含四个核心元素：它讨论的是某个对象或概念，它断言某种关系或性质，它可能依赖某些条件或方法，并且它通常有证据来源。换句话说，一个 Claim 实际上可以被拆解为 **Subject、Predicate、Context、Evidence** 四个部分。如果我们把这种结构形式化，就可以得到一个非常稳定的 Claim 模型。

---

# 一、Structured Claim 的基本结构

Structured Claim 可以表示为一个带语义字段的对象：

```
Claim
  id
  subject
  predicate
  object
  context
  evidence
  confidence
  source_paper
```

这实际上是一个扩展的 **SPO（Subject–Predicate–Object）** 结构，但加入了科学研究所必须的上下文与证据信息。

例如一句典型的论文结论：

> “Transformers outperform RNNs in large-scale language modeling.”

在结构化表示中可以变为：

```
subject: Transformer
predicate: outperforms
object: RNN
context: large-scale language modeling
evidence: paper p123
```

这样 Claim 就不再是文本，而是一个可以计算的知识单元。

---

# 二、Claim 的核心字段

为了保证结构稳定性，我们需要明确每个字段的语义。

## 1 Subject

Subject 是 Claim 的主要研究对象，通常对应一个 Concept。

```
subject -> Concept
```

例如：

```
Transformer
Diffusion Model
Self-Supervised Learning
```

Subject 的作用是让系统能够聚合相关研究主张。

例如：

```
all claims about Transformer
```

---

## 2 Predicate

Predicate 描述 Subject 与 Object 之间的关系。为了保持系统稳定性，Predicate 应该来自一个**有限集合**。

例如：

```
improves
outperforms
reduces
increases
enables
requires
scales_with
```

如果 Predicate 完全自由文本，Claim 网络很快会变得混乱。

---

## 3 Object

Object 描述 Claim 的目标对象。

它可以是：

```
Concept
Method
Metric
Property
```

例如：

```
training efficiency
model accuracy
GAN
RNN
```

---

## 4 Context

科学主张几乎总是有条件的。例如：

“Transformers outperform RNNs **in large datasets**。”

Context 就用于表达这些条件：

```
dataset
task
scale
domain
assumption
```

例如：

```
task: language modeling
dataset_size: large
```

Context 的存在可以避免 Claim 被错误泛化。

---

## 5 Evidence

Evidence 表示 Claim 的证据来源。

```
Evidence
  paper_id
  section
  figure
  dataset
```

例如：

```
paper: p123
figure: 3
dataset: WikiText-103
```

Evidence 可以连接到 Paper 或 Dataset 节点。

---

## 6 Confidence

由于 Claim 往往由 AI agent 自动提取，因此需要记录一个置信度：

```
confidence: 0.85
```

未来系统也可以根据多个来源更新置信度。

---

# 三、Claim 之间的关系

在 Minimal Research Graph 中，Claim 之间的关系是科学知识演化的关键。

主要关系包括：

```
Claim --supports--> Claim
Claim --contradicts--> Claim
Claim --refines--> Claim
Claim --extends--> Claim
```

例如：

```
Claim A:
Transformers scale with model size

Claim B:
Sparse transformers reduce scaling cost
```

关系：

```
Claim B --refines--> Claim A
```

随着文献进入系统，Claim 网络会逐渐形成一个**研究争论图（scientific debate graph）**。

---

# 四、Claim 的层级结构

为了避免 Claim 过于碎片化，可以引入一个简单的层级结构：

```
Observation
Result
Hypothesis
Theory
```

例如：

```
Observation:
Model accuracy increases with dataset size

Hypothesis:
Scaling laws govern neural network performance

Theory:
Large-scale training leads to predictable scaling behavior
```

不同层级的 Claim 在科学推理中的权重不同。

---

# 五、Structured Claim 示例

假设我们摄取了著名的 Transformer 论文，其核心 Claim 可以表示为：

```
Claim c001

subject: Transformer
predicate: replaces
object: recurrent architectures
context:
  task: sequence modeling

evidence:
  paper: p001
```

另一个 Claim：

```
Claim c002

subject: Transformer
predicate: improves
object: translation accuracy

context:
  dataset: WMT 2014
  task: machine translation

evidence:
  paper: p001
```

这两个 Claim 就可以被 agent 组合为一个更高层总结。

---

# 六、为什么 Structured Claim 很重要

一旦 Claim 被结构化，系统就获得了新的能力。

例如 agent 可以执行：

**Claim aggregation**

```
find all claims where subject = Transformer
```

**Method comparison**

```
find claims comparing Transformer and RNN
```

**Scientific contradiction detection**

```
find claims contradicting claim c123
```

这实际上把文献阅读变成了一个**知识图谱构建过程**。

---

# 七、Claim 在整个 RKS 架构中的位置

在 Research Knowledge Substrate 中，Claim 处于图结构的中心位置：

```
Concept → Claim ← Paper
           |
           |
         Method
           |
         Dataset
```

Paper 提供来源，Method 提供实现路径，Dataset 提供证据，而 Claim 则是知识表达的核心。

因此可以说：

**RKS 的本质并不是 Paper Graph，而是 Claim Graph。**
