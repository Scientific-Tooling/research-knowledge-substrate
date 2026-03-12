如果我们决定把这个项目定位为 **Research Knowledge Substrate**，那么它的性质就已经明显不同于传统的文献管理工具了。传统工具（例如 Zotero 或 Mendeley）的目标是帮助人类组织 PDF、生成引用、维护文献列表，它们的结构核心是“文件 + 元数据 + 标签”。而 **Research Knowledge Substrate** 的目标则是为 **AI agent 和研究者共同使用的知识基础设施**提供底层结构，它不再只是保存文献，而是**承载研究知识本身的结构化形态**。从结构稳定性的角度看，这意味着系统的核心对象必须从“文献文件”转移到“研究知识节点”，文献只是一种证据来源或知识来源，而不是系统的中心。

如果沿着这个方向推进，一个非常清晰的架构理念会出现：**Research Knowledge Substrate 是一个面向研究对象的知识图谱系统，它通过 CLI 暴露接口，由 AI agent 作为主要操作者，人类则通过自然语言或 CLI 指令参与其中。** 换句话说，这个系统更像是研究环境的“地基层”，而不是一个应用程序。

---

## 一、系统核心哲学：从 Paper 到 Knowledge Node

传统文献工具的结构通常是：

```
library
 ├── papers
 ├── folders
 ├── tags
```

这种结构在 AI 时代会出现明显的结构不稳定性，因为：

* 标签没有严格语义
* PDF 不可计算
* 知识被锁在自然语言文本中

因此在 Research Knowledge Substrate 中，更合理的抽象应该是：

```
Knowledge Node
 ├── claim
 ├── method
 ├── dataset
 ├── experiment
 ├── paper
 └── idea
```

Paper 在这里变成：

```
Paper
 ├── metadata
 ├── authors
 ├── venue
 ├── extracted_claims
 ├── extracted_methods
 └── citations
```

也就是说：

**paper 是 knowledge extraction 的来源，而不是知识的最终形态。**

这一步非常关键，因为它决定了系统的长期结构稳定性。如果核心对象是 PDF，那么系统天然无法支持 AI 推理；如果核心对象是 claim、method 和 dataset，那么系统天然可以成为研究推理的基础。

---

## 二、Research Knowledge Substrate 的系统结构

从架构角度看，它更像一个三层系统：

```
             AI Research Agent
                    │
                    │
                 CLI API
                    │
       ┌────────────┴────────────┐
       │                         │
Knowledge Graph             File Storage
(papers, claims, etc)        (PDFs)
       │
Semantic Index / Embeddings
```

这里有三个核心组件。

第一层是 **Knowledge Graph**，它是系统的逻辑核心。所有研究对象——论文、方法、实验、假设、结论——都以节点和关系的形式存在。

第二层是 **File Storage**，用于保存 PDF、markdown 文本、图表等原始材料。

第三层是 **Semantic Index**，为 agent 提供语义搜索能力，使得系统能够回答类似“有哪些论文提出了类似方法”这样的问题。

从工程角度看，一个非常现实的实现组合是：

* SQLite 或 Postgres
* 本地文件系统
* 向量索引（例如 embedding store）

这样系统仍然保持轻量和可移植性。

---

## 三、CLI 作为 Agent Interface

既然系统是 agent-first 的，那么 CLI 的角色其实类似 **Git 的 plumbing layer**。它不是用户界面，而是 agent 操作 substrate 的接口。

例如：

```
rks add paper 10.48550/arxiv.1706.03762
```

系统执行：

1 获取 metadata
2 下载 PDF
3 解析文本
4 生成 embedding
5 提取 claims

然后生成内部对象：

```
paper: p001
claim: c102
method: m034
```

用户或 agent 可以继续查询：

```
rks search "attention mechanism"
```

或者：

```
rks show paper p001
```

甚至：

```
rks claims p001
```

这时候输出的就不只是 abstract，而是：

```
Claim 1
Claim 2
Claim 3
```

这一步实际上是在把**文献阅读过程结构化**。

---

## 四、研究知识图谱的关键关系

为了让系统真正成为 Research Substrate，我们必须设计一些稳定的关系结构。一个简单但非常强大的 schema 可能是：

```
paper --contains--> claim
paper --proposes--> method
method --uses--> dataset
paper --cites--> paper
claim --supported_by--> paper
experiment --tests--> claim
```

这样系统就形成一个研究网络。

例如一个 agent 可以执行：

```
find methods related to diffusion models
```

或者：

```
find claims contradicting claim c101
```

这种能力在传统文献管理工具中几乎不存在。

---

## 五、自动文献摄取（Agent Pipeline）

如果把 agent 作为系统的主要用户，那么最重要的 pipeline 就是：

```
paper ingestion pipeline
```

流程可以是：

```
arxiv / doi
      ↓
metadata fetch
      ↓
pdf download
      ↓
text extraction
      ↓
embedding
      ↓
claim extraction
      ↓
graph insertion
```

这样系统每天可以自动更新研究领域。

例如 agent 定期执行：

```
rks ingest arxiv cs.LG
```

然后每天生成报告：

```
weekly summary: diffusion models
```

这种能力实际上会把文献阅读变成一种自动化研究活动。

---

## 六、与 ExperimentOS / TAP 的结构关系

从结构角度看，Research Knowledge Substrate 可以成为你之前讨论的 **ExperimentOS / TAP 体系的基础层**。

系统关系大致是：

```
ExperimentOS
     │
     │
Research Agents
     │
     │
Research Knowledge Substrate
```

在这个结构中：

* ExperimentOS 管理实验
* Agent 执行研究任务
* RKS 存储研究知识

例如：

```
experiment e12
 ├── hypothesis
 ├── linked_papers
 ├── datasets
 └── results
```

这些对象都可以直接连接到 RKS 的节点。

因此 RKS 本质上是 **研究环境的知识内核**。

---

## 七、这个项目最有价值的突破点

如果这个系统设计得好，它可能会实现一个非常重要的转变：

**从文献管理 → 研究知识基础设施**

在传统工具里，人类阅读论文并整理笔记；而在这个系统中，AI agent 可以：

* 自动阅读论文
* 抽取研究结论
* 建立研究关系图
* 辅助提出假设

换句话说，Research Knowledge Substrate 可以成为 **AI-native science platform 的知识基础层**。

