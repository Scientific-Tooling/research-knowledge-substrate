如果我们把 **Research Knowledge Substrate (RKS)** 当作一个真正的基础设施来设计，那么 **MVP 的关键不在于功能多，而在于结构稳定**。在一个长期演化的系统中，只要核心对象模型稳定、接口稳定、数据摄取流程稳定，其它能力（agent、分析、可视化、研究自动化）都可以逐步叠加。因此在定义 MVP 时，我们需要做的其实是三件事：首先定义研究知识的最小对象集合，其次定义一套能够长期稳定存在的 CLI 接口语义，最后定义文献进入系统的自动化 pipeline。只要这三层结构成立，整个系统就可以成为一个真正的 **AI-native research substrate**。

下面我给出一个**尽可能简洁但结构完整的 MVP 设计**。

---

# 一、核心对象 Schema（Research Knowledge Graph）

在 Research Knowledge Substrate 中，paper 只是知识来源，而不是知识主体。因此核心对象需要围绕 **研究结论、方法和证据结构**展开。

一个非常稳定且足够表达研究过程的最小对象集合可以是：

```text
Paper
Claim
Method
Dataset
Note
```

这些对象之间形成一个简单但表达力很强的图结构。

---

## 1 Paper

Paper 是文献来源节点。

```
Paper
  id
  title
  authors
  year
  venue
  doi
  arxiv_id
  abstract
  pdf_path
  text_path
```

重要原则：

**Paper 是 evidence container。**

它保存原始文本和引用关系，但不承担知识表达的主要任务。

---

## 2 Claim

Claim 是整个系统最重要的对象。

```
Claim
  id
  text
  paper_id
  confidence
  created_by
```

例如：

```
Claim:
"Transformers scale predictably with model size and dataset size."
```

Claim 可以互相关联：

```
Claim --supports--> Claim
Claim --contradicts--> Claim
```

这样系统就能表示**科学争论结构**。

---

## 3 Method

Method 描述论文提出的技术或研究方法。

```
Method
  id
  name
  description
  paper_id
```

关系：

```
Paper --proposes--> Method
Method --implements--> Claim
```

例如：

```
Method: Transformer
Method: Diffusion Model
Method: LoRA
```

---

## 4 Dataset

Dataset 是研究证据的重要组成部分。

```
Dataset
  id
  name
  description
  source
```

关系：

```
Method --uses--> Dataset
Paper --evaluates_on--> Dataset
```

---

## 5 Note

Note 是人类或 agent 的研究记录。

```
Note
  id
  content
  linked_object
  created_by
  timestamp
```

Note 可以连接到任何对象。

---

## 6 Graph Relations

MVP 的关系集合建议限制在：

```
paper --cites--> paper
paper --contains--> claim
paper --proposes--> method
method --uses--> dataset
claim --supported_by--> paper
claim --contradicts--> claim
note --about--> object
```

这是一个**非常小但表达能力很强的 research graph**。

---

# 二、CLI Command Spec

CLI 的目标不是用户界面，而是 **agent interface**。
因此命令应该遵循两个原则：

1 简洁
2 语义稳定

建议使用一个命令前缀，例如：

```
rks
```

---

## 1 Ingestion

添加文献：

```
rks add doi <doi>
rks add arxiv <id>
rks add pdf <file>
```

系统自动执行：

```
metadata fetch
pdf download
text extraction
embedding generation
claim extraction
```

返回：

```
paper_id
```

---

## 2 Query

搜索：

```
rks search "diffusion models"
```

返回：

```
paper list
claim list
method list
```

---

查看对象：

```
rks show paper <id>
rks show claim <id>
rks show method <id>
```

---

## 3 Knowledge Extraction

列出论文 claims：

```
rks claims <paper_id>
```

列出 methods：

```
rks methods <paper_id>
```

---

## 4 Linking

创建关系：

```
rks link claim <c1> supports <c2>
rks link claim <c1> contradicts <c2>
```

---

## 5 Note

添加笔记：

```
rks note add paper <id>
rks note add claim <id>
```

---

## 6 Agent Query

这是 CLI 中最重要的一类命令：

```
rks ask "what are alternatives to transformers?"
```

Agent workflow：

```
search papers
extract methods
summarize
```

---

## 7 Topic Mapping

构建研究图：

```
rks map "diffusion models"
```

输出：

```
topic graph
```

---

# 三、Paper Ingestion Pipeline

文献摄取 pipeline 是系统自动化的关键。

流程应该设计为 **可重复、可扩展、可回溯**。

---

## Step 1 Metadata Fetch

输入：

```
doi / arxiv id
```

输出：

```
title
authors
year
abstract
pdf url
```

数据来源：

* Crossref
* arXiv API

---

## Step 2 PDF Acquisition

下载 PDF：

```
storage/papers/<paper_id>.pdf
```

---

## Step 3 Text Extraction

将 PDF 转为 markdown：

```
storage/text/<paper_id>.md
```

建议 pipeline：

```
PDF
 ↓
layout parser
 ↓
clean markdown
```

---

## Step 4 Embedding

生成 semantic embedding：

```
embedding/<paper_id>.vec
```

用途：

```
semantic search
topic clustering
```

---

## Step 5 Claim Extraction

使用 LLM：

```
extract_claims(text)
```

输出：

```
Claim objects
```

例如：

```
Claim 1
Claim 2
Claim 3
```

写入数据库：

```
paper --contains--> claim
```

---

## Step 6 Method Detection

从论文中提取：

```
Method objects
```

例如：

```
Diffusion Model
Vision Transformer
```

---

## Step 7 Graph Update

更新关系：

```
paper --proposes--> method
method --supports--> claim
```

---

# 四、MVP 技术实现建议

为了保证项目快速落地，可以采用一个非常轻量的技术栈：

```
Python
Typer (CLI)
SQLite
DuckDB / simple graph layer
local filesystem
embedding store
```

目录结构：

```
rks/

  cli/
  ingestion/
  graph/
  storage/
  agent/

library/

  papers/
  text/
  embeddings/
```

---

# 五、MVP 的能力边界

MVP 不需要解决所有问题。

只要完成三件事就成功：

1 自动 ingest 论文
2 结构化提取 claim / method
3 支持 semantic query

这已经足以让 agent 进行基本的研究辅助。
