如果 **Research Knowledge Substrate (RKS)** 被定位为一个长期演化的研究基础设施，那么 **Storage Architecture** 的设计必须优先保证两件事情：**结构稳定性**和**可演化性**。在一个研究知识系统中，数据量会持续增长，数据结构也会不断扩展，如果存储层过于耦合或依赖单一技术栈，系统很容易在规模扩大后变得难以维护。因此，一个合理的存储架构应当把不同类型的数据结构分离，并通过稳定的对象 ID 进行连接，从而形成一种 **多存储层协同的结构化系统**。

从数据结构的角度来看，RKS 实际上包含四种性质完全不同的数据：结构化研究对象、图关系、文本内容以及语义向量。如果把这些数据强行塞进同一种数据库，系统很快会变得复杂且低效。因此更合理的设计是将存储系统拆分为四个相互协作的层次：**Object Store、Graph Store、Document Store、Vector Store**。这些层之间通过统一的 ID 空间连接，构成 RKS 的底层数据基础。

---

# 一、整体存储结构

RKS 的存储架构可以理解为一个分层系统：

```
                Query / Reasoning Engine
                         │
                         │
              Research Graph API Layer
                         │
        ┌───────────────┼────────────────┐
        │               │                │
     Object Store    Graph Store     Vector Store
        │               │                │
        └──────────── Document Store ────┘
```

每一层承担不同职责，而不是互相替代。

---

# 二、Object Store（核心对象存储）

Object Store 是整个系统最基础的层，用于保存 **结构化研究对象**。这些对象包括 Paper、Claim、Method、Dataset、Concept 等。Object Store 不负责复杂关系查询，它只负责稳定地存储对象数据。

例如一个 Paper 对象：

```
Paper
  id
  title
  authors
  year
  venue
  doi
  abstract
  pdf_path
```

Claim 对象：

```
Claim
  id
  subject
  predicate
  object
  context
  evidence
  confidence
```

这些对象可以使用简单的关系数据库保存，例如 SQLite 或 PostgreSQL。Object Store 的核心原则是 **对象结构稳定且可版本化**，这样即使系统扩展新的字段，也不会破坏旧数据。

---

# 三、Graph Store（研究关系图）

Graph Store 用于存储研究对象之间的关系，例如：

```
Paper --cites--> Paper
Paper --contains--> Claim
Claim --about--> Concept
Method --uses--> Dataset
Claim --contradicts--> Claim
```

这些关系本质上构成 Research Graph。Graph Store 可以使用两种实现方式：一种是使用专门的图数据库，例如 Neo4j；另一种是使用关系数据库中的边表来表示图结构。例如：

```
Edge
  id
  source_id
  target_id
  relation_type
```

在 MVP 阶段，用关系数据库实现 Graph Store 往往更简单，因为整个系统的数据仍然可以通过 SQL 查询。

Graph Store 的作用是支持 **结构化研究查询**，例如寻找某个概念相关的所有 Claim，或者找到支持某个 Claim 的论文。

---

# 四、Document Store（原始文献与文本）

Document Store 用于保存原始研究材料，例如：

* PDF 文件
* Markdown 文本
* 图表提取结果

这些内容通常不适合存储在数据库中，因此最简单的方式是使用文件系统。例如：

```
library/
  papers/
    p001.pdf
    p002.pdf

  text/
    p001.md
    p002.md
```

Paper 对象中只保存文件路径。这样可以避免数据库体积过大，并且方便未来替换解析工具。

Document Store 的作用是为 Claim Extraction Pipeline 提供数据来源。

---

# 五、Vector Store（语义索引）

Vector Store 用于保存 embedding，用于语义检索。例如：

```
Embedding
  object_id
  vector
  type
```

type 可以表示：

```
paper_embedding
claim_embedding
concept_embedding
```

当 agent 执行语义查询时，例如：

“transformer alternatives”

系统会先在 Vector Store 中搜索相关对象，然后再通过 Graph Store 扩展关系。

Vector Store 的存在，使 RKS 能够同时支持 **语义搜索与结构推理**。

---

# 六、统一 ID 系统

为了让这些存储层协同工作，RKS 需要一个统一的对象 ID 系统。例如：

```
p_001   Paper
c_102   Claim
m_021   Method
d_015   Dataset
k_004   Concept
```

Graph Store、Vector Store 和 Document Store 都使用这些 ID。这样系统可以轻松地在不同存储层之间建立连接。

例如：

```
Claim c102
  evidence → p001
```

Vector Store 中也可以保存：

```
embedding(c102)
```

---

# 七、存储层的数据流

当系统摄取一篇新论文时，数据会流入不同存储层：

```
Paper ingestion
      │
      │
      ↓
Object Store ← metadata
      │
      ↓
Document Store ← PDF
      │
      ↓
Claim Extraction
      │
      ↓
Object Store ← Claim
      │
      ↓
Graph Store ← relationships
      │
      ↓
Vector Store ← embeddings
```

这种结构保证每一层职责清晰。

---

# 八、为什么需要多存储层

很多系统试图把所有数据放进一个数据库，例如只使用图数据库。但在研究知识系统中，不同数据类型的访问模式完全不同：

| 数据类型           | 访问模式 |
| -------------- | ---- |
| Paper metadata | 精确查询 |
| Claim Graph    | 图遍历  |
| PDF 文本         | 顺序读取 |
| Embedding      | 向量搜索 |

因此多存储层设计能够显著提高系统稳定性和性能。

---

# 九、可扩展性设计

当 RKS 规模增长时，存储系统仍然可以逐步升级。例如：

初始阶段：

```
SQLite
local filesystem
simple vector index
```

中等规模：

```
PostgreSQL
object storage
vector database
```

大规模研究平台：

```
distributed graph store
object storage cluster
large vector index
```

因为各层之间通过 ID 连接，所以升级某一层不会破坏系统结构。

---

# 十、Storage Architecture 的核心原则

RKS 的存储架构应该遵循一个非常重要的原则：

**对象、关系、文本和语义索引必须解耦。**

换句话说：

```
Object Store → 保存研究对象
Graph Store → 保存研究关系
Document Store → 保存原始文献
Vector Store → 保存语义索引
```

这种设计不仅使系统更稳定，也让 AI agent 可以在不同层级进行操作。
