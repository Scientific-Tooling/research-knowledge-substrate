# 概念规范化的哲学基础与工程实现

## 背景

RKS 从学术文献中自动提取概念，并在知识图谱中维护唯一节点。当前实现的核心问题是：
同一概念在不同论文中以不同表面形式出现（`BERT`、`bert`、`Bidirectional Encoder Representations from Transformers`），
如果没有精确的规范化策略，它们会被建模为多个独立节点，导致知识图谱碎片化。

本文从五位哲学家的概念理论出发，分析这一问题的本质，并给出对应的工程优化方向。

---

## 一、Frege：涵义与指称的分离

**来源**：《论涵义与指称》（*Über Sinn und Bedeutung*，1892）

弗雷格指出，一个名称具有两个维度：

- **涵义（Sinn）**：名称的表达方式，即"以何种方式呈现对象"
- **指称（Bedeutung）**：名称实际指向的对象本身

经典例子："晨星"与"暮星"拥有相同的指称（金星），但涵义不同。
这是一个有认知意义的同一性陈述——因为你必须通过推断才能得知它们指同一对象。

**在 RKS 中的对应**：

```
涵义（Sinn）    ← name、aliases_json 中的每个字符串
指称（Bedeutung）← concepts 表中的 id（唯一节点）
```

当前系统用字符串匹配统一涵义，但缺少一个明确的"刚性锚点"来标识指称。
`aliases_json` 中所有形式地位平等，没有区分哪个是最可靠的跨论文匹配键。

**工程对应**：引入 `canonical_abbrev` 字段，存储刚性指示词（见第二节）。

---

## 二、Kripke：刚性指示词

**来源**：《命名与必然性》（*Naming and Necessity*，1980）

克里普克区分两类指称表达式：

- **刚性指示词（Rigid Designator）**：在所有可能世界中指称同一对象。
  专名（`BERT`、`GPT-4`、`ResNet`）是刚性的——无论在哪篇论文、哪个语境中出现，
  它就是那个模型，不随描述变化而漂移。
- **摹状词（Definite Description）**：通过描述指称，跨语境可漂移。
  "2018年最佳语言模型"不是刚性的，因为这个描述可以指向不同对象。

**在 RKS 中的含义**：

缩写（`BERT`、`LLM`、`MoE`）通常是刚性指示词，在跨论文匹配中比描述性全名更可靠。
描述性全名（"Bidirectional Encoder Representations from Transformers"）是摹状词，
不同论文可能用略有不同的描述措辞，不适合作为主匹配键。

**工程对应**：新增 `canonical_abbrev TEXT` 字段存储刚性指示词；
`find_by_name_or_alias` 优先匹配 `canonical_abbrev`，再匹配 `name` 和 `aliases_json`。

```
匹配优先级：canonical_abbrev（刚性）> name（规范全名）> aliases_json（其他变体）
```

---

## 三、Carnap：概念精确化（Explication）

**来源**：《意义与必然性》（*Meaning and Necessity*，1947）；《科学的逻辑基础》（1950）

卡尔纳普提出 **Explication**：把前科学的模糊概念（Explicandum）替换为精确的科学概念（Explicatum）。
一个好的 Explication 应满足四个标准：

1. **相似性**：Explicatum 在核心用法上与 Explicandum 一致
2. **精确性**：Explicatum 有明确的判定规则
3. **丰富性**：纳入尽可能多的相关信息
4. **简洁性**：不引入不必要的复杂度

`canonicalize_term()` 本质上是一个 Explication 过程：把原始词形精确化为规范术语。

按卡尔纳普的标准评估当前实现：

| 标准 | 现状 | 问题 |
|------|------|------|
| 相似性 | 基本满足 | 连字符变空格改变了词形外貌 |
| 精确性 | 满足 | 规则明确，输出确定 |
| 丰富性 | 不足 | `domain` 字段从未填充，丢失领域上下文 |
| 简洁性 | 满足 | — |

**工程对应**：`canonicalize_term` 的 Unicode/连字符/括号规范化已在上一轮实现；
`domain` 字段的填充作为后续优化方向保留。

---

## 四、Wittgenstein：家族相似

**来源**：《哲学研究》（*Philosophische Untersuchungen*，1953）

维特根斯坦反对"概念必须有充要定义"的传统观点：

> "游戏"这个词涵盖了棋盘游戏、扑克、球类运动……没有一个特征是所有游戏共享的。
> 它们之间只有相互交叠的相似性网络——家族相似（Familienähnlichkeit）。

**在 RKS 中的含义**：

概念变体之间往往是家族相似关系，不存在一个唯一的充要描述：

```
Attention  ←──→  Self-Attention  ←──→  Multi-Head Attention
    ↑                                          ↑
Scaled Dot-Product Attention  ←──→  Cross-Attention
```

当前的 `find_by_name_or_alias` 是集合成员判断（要么在、要么不在），
对家族相似关系无能为力——两个概念只要不完全命中，就会创建两个节点。

**工程对应**：`concept find-duplicates` 命令（后续实现）。
该命令不要求精确匹配，而是通过相似度评分（如 trigram 或编辑距离）
找出高相似度的概念对，提示用户人工确认后执行 `concept merge`。

---

## 五、Aristotle：属加种差

**来源**：《范畴篇》（*Categoriae*）；《形而上学》（*Metaphysica*）

亚里士多德的经典定义方法：

```
概念 = 上位类（genus）+ 区分特征（differentia）

例：人 = 动物（genus）+ 理性（differentia）
例：Vision Transformer = Transformer（genus）+ 视觉输入处理（differentia）
```

这与 `parent_concept_id` 的设计完全吻合。但当前父概念推断只取最后一个词：

```python
# 当前实现
"Sparse Mixture of Experts" → parent = "Expert"    # ✗ 应为 "Mixture of Experts"
"Vision Transformer"        → parent = "Transformer" # ✓
"Gradient Descent Method"   → parent = None          # ✓（Method 是停用词）
```

亚里士多德要求 genus 是实质性的上位类，而不是词序上恰好在最后的词。

**工程对应**：改进 `_infer_parent_term`，使用中心词检测替代简单的"取最后词"策略。
扩展停用词集，识别多词停用词组（`of experts` 不应截断为 `experts`）。

---

## 工程实现总览

### 已实现（上一轮）

| 层 | 改动 | 哲学依据 |
|----|------|---------|
| LLM Prompt | 5 条命名规则（全名优先、Title Case、缩写入 aliases） | Kripke + Carnap |
| contract.py | `check_concept_alias_format()` 格式警告 | Carnap（精确性标准） |
| normalize.py | Unicode NFC、连字符→空格、括号缩写提取 | Carnap |
| concept_repository.py | `get_or_create` 自动注册缩写别名 | Frege（涵义收集） |

### 本轮实现

| 层 | 改动 | 哲学依据 |
|----|------|---------|
| DB Migration | `concepts` 表新增 `canonical_abbrev TEXT` 列 | Kripke（刚性指示词存储） |
| ConceptRecord | 新增 `canonical_abbrev: Optional[str]` 字段 | Frege（涵义/指称分离） |
| find_by_name_or_alias | 优先匹配 `canonical_abbrev`，再匹配 name/aliases | Kripke（刚性优先） |
| get_or_create | 从 `extract_abbreviation` 填充 `canonical_abbrev` | Kripke + Frege |
| _infer_parent_term | 中心词检测，扩展停用词集 | Aristotle（属加种差） |

### 后续方向

| 功能 | 哲学依据 | 优先级 |
|------|---------|--------|
| `concept find-duplicates` 命令 | Wittgenstein（家族相似） | 中 |
| `domain` 字段填充 | Carnap（丰富性标准） | 低 |
| 刚性指示词跨论文优先匹配评分 | Kripke | 中 |

---

## 核心设计原则（结论）

综合五位哲学家的思想，RKS 概念规范化应遵循以下原则：

1. **指称唯一性**（Frege）：同一研究对象在图谱中只有一个节点，所有涵义变体通过 aliases 收敛到同一 id。

2. **刚性锚点优先**（Kripke）：缩写（专名）比描述性全名更适合作为跨论文的匹配键，应存储为独立字段并赋予更高匹配优先级。

3. **精确化而非固化**（Carnap）：规范化的目标是提升精确性，而不是抹去有意义的变体信息；aliases 应完整保留所有表面形式。

4. **相似度作为辅助**（Wittgenstein）：对无法精确匹配的家族相似概念，用相似度评分辅助人工判断，而不是静默创建新节点。

5. **层次结构实质化**（Aristotle）：父概念应是实质性的上位类，而不是词序上的偶然结果。
