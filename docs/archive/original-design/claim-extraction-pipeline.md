如果 **Research Knowledge Substrate (RKS)** 的核心是 **Claim Graph**，那么系统真正的技术难点并不在数据库、CLI 或 graph schema，而在于一个关键能力：**从论文中自动生成 Structured Claim**。换句话说，我们需要设计一条 **Claim Extraction Pipeline**，把非结构化论文文本逐步转化为结构化研究知识。这个 pipeline 的目标不是完美理解论文，而是稳定地提取出“足够正确”的研究主张，并将其放入 Research Graph 中。

从系统工程角度看，这个问题必须通过 **多阶段结构化流程**来解决，而不是试图一次性让模型理解整篇论文。一个稳定的 pipeline 应该逐步收敛，从文本到语义，再到结构化 Claim。下面给出一个适合 RKS 的 **分层提取架构**。

---

# 一、Claim Extraction 的整体流程

一个稳定的 pipeline 可以设计为六个阶段：

```
PDF
 ↓
Structured Text Extraction
 ↓
Scientific Section Detection
 ↓
Claim Candidate Detection
 ↓
Claim Normalization
 ↓
Structured Claim Construction
 ↓
Graph Integration
```

每一层的目标都非常明确：**减少语义复杂度并逐步结构化信息**。

---

# 二、Stage 1：Structured Text Extraction

论文首先必须从 PDF 转换为结构化文本。简单的文本提取是不够的，因为科学论文的结构信息（标题、图表、章节）非常重要。

输出结构应类似：

```
Document
  title
  abstract
  sections
    introduction
    related_work
    method
    experiments
    conclusion
```

每个 section 再包含段落：

```
Paragraph
  text
  section
```

这样做的原因是：**绝大多数 Claim 出现在特定 section 中**。

例如：

| Section      | Claim 密度 |
| ------------ | -------- |
| Abstract     | 极高       |
| Introduction | 高        |
| Method       | 中        |
| Experiments  | 高        |
| Conclusion   | 高        |

而 Related Work 中的 Claim 通常是对别人的引用。

---

# 三、Stage 2：Claim Candidate Detection

接下来需要找出**可能是 Claim 的句子**。

科学论文中的 Claim 通常具有明显语言模式，例如：

* “We propose …”
* “Our results show …”
* “This method improves …”
* “We demonstrate that …”
* “Experiments indicate …”

因此可以先通过 **Claim Sentence Detector** 提取候选句。

输出：

```
ClaimCandidate
  text
  section
  paragraph_id
  confidence
```

例如：

```
"Our experiments show that diffusion models outperform GANs in image generation."
```

---

# 四、Stage 3：Claim Normalization

论文中的 Claim 往往带有大量语言噪声，例如：

> “Our extensive experiments clearly demonstrate that our proposed method significantly improves performance.”

但真正的科学主张可能只有：

```
Method X improves performance
```

因此需要进行 **Claim Normalization**，即：

* 去除修辞语言
* 去除作者指代
* 转换为客观表述

例如：

原句：

```
We show that our transformer variant significantly improves translation accuracy.
```

规范化后：

```
Transformer variant improves translation accuracy
```

这一阶段的输出可以是：

```
NormalizedClaim
  text
  source_sentence
```

---

# 五、Stage 4：Structured Claim Parsing

接下来将 Normalized Claim 转换为 **Structured Claim Model**。

需要提取：

```
subject
predicate
object
context
```

例如：

```
Transformer improves translation accuracy on WMT14
```

结构化为：

```
subject: Transformer
predicate: improves
object: translation accuracy
context:
  dataset: WMT14
  task: machine translation
```

这个步骤实际上是一个 **semantic parsing** 任务。

---

# 六、Stage 5：Concept Linking

为了让 Claim 融入 Research Graph，subject 和 object 必须链接到 Concept。

例如：

```
Transformer → Concept: Transformer
GAN → Concept: Generative Adversarial Network
```

这一步的目标是避免出现：

```
transformer
transformers
Transformer model
```

这些重复节点。

因此需要一个 **Concept Resolver**。

---

# 七、Stage 6：Evidence Binding

Claim 还需要绑定证据。

证据通常来自：

```
paper
figure
table
dataset
```

例如：

```
evidence:
  paper: p123
  section: experiments
  dataset: ImageNet
```

这样 Claim 就具备科学证据链。

---

# 八、最终 Claim 对象

经过 pipeline 之后，一个 Claim 对象可能是：

```
Claim c102

subject: Diffusion Model
predicate: outperforms
object: GAN

context:
  task: image generation
  dataset: CIFAR-10

evidence:
  paper: p451
  section: experiments

confidence: 0.87
```

然后系统写入 Research Graph：

```
Paper p451 --contains--> Claim c102
Claim c102 --about--> Diffusion Model
```

---

# 九、Pipeline 的稳定性策略

为了保证系统长期稳定运行，有几个关键策略。

### 1 Claim 数量限制

每篇论文只提取：

```
5–15 claims
```

否则 Graph 会被噪声淹没。

---

### 2 Claim 类型分类

Claim 可以分为三类：

```
Contribution Claim
Result Claim
Observation Claim
```

例如：

```
Contribution:
"We propose method X"

Result:
"Method X improves accuracy"

Observation:
"Accuracy increases with dataset size"
```

不同类型的 Claim 价值不同。

---

### 3 多轮提取

Pipeline 可以运行多轮：

```
Initial extraction
 ↓
Graph context
 ↓
Refinement
```

当 Graph 已经包含大量知识时，Agent 可以利用已有 Concept 改进提取质量。

---

# 十、为什么这个 Pipeline 很关键

如果 Claim Extraction Pipeline 成功运行，那么 RKS 会逐渐积累一种非常强大的结构：

```
Scientific Claim Network
```

例如：

```
Claim A: Transformers scale well
Claim B: Sparse transformers reduce cost
Claim C: Diffusion models outperform GANs
```

随着论文不断进入系统，这张网络会自动成长为一个 **科学知识图谱**。

从结构上看，这意味着 RKS 不再只是文献数据库，而是变成：

**一个可以被 AI agent 推理的科学知识基础设施。**

---

如果继续推进设计，下一步其实会出现一个非常关键的系统问题，也是很多研究知识系统失败的原因：

**Concept System（概念体系）应该如何设计。**

因为如果 Concept 体系不稳定，整个 Claim Graph 很快就会变成一堆重复节点。
