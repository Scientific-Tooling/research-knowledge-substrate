# RKS 用户手动操作说明

这份文档面向人工用户，说明如何直接通过 CLI 手动使用 RKS。重点是“怎么用”，不是“怎么测试”。

## 1. 适用场景

适合下面几类使用方式：

- 手动导入 PDF、DOI / arXiv / PMID 文献，或者规范 URL
- 手动查看论文、claim、concept、method、dataset
- 手动运行查询、搜索和总结
- 手动审阅 claim relation
- 手动检查 agent 任务和 paper 状态

如果你的目标是做回归验证，请看 [manual-testing-guide-zh.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/manual-testing-guide-zh.md)。

## 2. 环境准备

在仓库根目录执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

初始化本地工作区：

```bash
rks config init
rks init-db
rks migrate
```

查看当前配置：

```bash
rks config show
```

常用配置关注点：

- `data_dir`：数据目录
- `reference_pdf_acquisition`：参考文献 ingest 时是否尝试获取 PDF
- `llm.base_url`
- `llm.model`

## 3. 基本工作流

RKS 的基本使用顺序通常是：

1. ingest 文献
2. 抽取 text / claims / methods / datasets
3. 查看 paper 和 graph 对象
4. 运行 query / search / output / summarize
5. 审阅并持久化关键 relation

## 4. 导入文献

### 4.1 导入本地 PDF

```bash
rks ingest pdf path/to/paper.pdf
```

返回值里最重要的是 `paper_id`。

导入后建议立刻查看：

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

如果你想把阅读判断直接挂在 paper 上，可以立刻写笔记：

```bash
rks note add paper <paper_id> --content "重点核对 benchmark split 和评估口径。"
rks note list paper <paper_id>
```

`show paper` 现在也会返回 `notes` 字段，方便把 paper 记录和笔记一起看。

### 4.2 导入 DOI

```bash
rks ingest doi 10.48550/arXiv.1706.03762
```

这条路径会保存：

- paper 元数据
- metadata artifact
- 如果有摘要，则生成 text artifact
- 如果 provider 暴露 PDF 候选，则尝试获取 `source.pdf`

### 4.3 导入 arXiv

```bash
rks ingest arxiv 1706.03762
```

### 4.4 导入 PMID

```bash
rks ingest pmid 31452104
```

这条路径会把 PubMed 元数据以 XML artifact 落盘，并据此创建 paper。

### 4.5 通过 URL 导入

```bash
rks ingest url https://doi.org/10.48550/arXiv.1706.03762
rks ingest url https://pubmed.ncbi.nlm.nih.gov/31452104/
rks ingest url https://example.org/paper.pdf
```

当前支持的 URL 类型：

- DOI 解析 URL
- arXiv 摘要页或 PDF URL
- PubMed 论文 URL
- 直链 PDF URL

导入 DOI / arXiv / PMID / URL 后建议重点检查：

```bash
rks status paper <paper_id>
```

看这些字段：

- `source_pdf.available`
- `source_pdf.acquisition.status`
- `artifacts`

### 4.6 重复 paper 处理

如果同一篇 paper 被重复 ingest（例如先 ingest DOI，再 ingest 本地 PDF），可以先检测再合并：

```bash
rks papers find-duplicates
rks papers find-duplicates --mode identifiers
rks papers merge <target_paper_id> <source_paper_id> --prefer target
```

使用建议：

- `heuristic` 模式会使用 DOI、arXiv ID、规范化标题
- `identifiers` 模式只使用 DOI、arXiv ID
- `target_paper_id` 选你希望保留的 canonical 记录
- merge 后用 `rks show paper <target_paper_id>` 复核结果

## 5. 抽取研究对象

### 5.1 抽取 text

```bash
rks extract text <paper_id>
```

如果要显式指定模式：

```bash
rks extract text <paper_id> --mode heuristic
rks extract text <paper_id> --mode llm-api
rks extract text <paper_id> --mode agent
```

### 5.2 抽取 claims

```bash
rks extract claims <paper_id>
```

常用模式：

```bash
rks extract claims <paper_id> --mode heuristic
rks extract claims <paper_id> --mode llm-api
rks extract claims <paper_id> --mode agent
```

### 5.3 抽取 methods / datasets

```bash
rks extract methods <paper_id>
rks extract datasets <paper_id>
```

### 5.4 生成总结

```bash
rks summarize paper <paper_id>
```

也可以使用：

```bash
rks summarize paper <paper_id> --mode llm-api
rks summarize paper <paper_id> --mode agent
```

## 6. 查看对象

### 6.1 查看 paper

```bash
rks show paper <paper_id>
```

适合看：

- 标题和来源
- `pdf_path`
- artifact 列表

### 6.2 查看 claims

```bash
rks claims <paper_id>
rks show claim <claim_id>
```

`show claim` 更适合看：

- evidence
- context
- related edges
- reviewed relations

### 6.3 查看 concepts / methods / datasets

```bash
rks concepts <paper_id>
rks methods <paper_id>
rks datasets <paper_id>
```

如果你已经知道对象 ID，也可以用：

```bash
rks show method <method_id>
rks show dataset <dataset_id>
```

## 7. 查询与搜索

### 7.1 搜索

```bash
rks search Transformer
rks search "translation quality benchmark" --mode semantic
rks search "Sparse Attention" --mode hybrid
```

可选模式：

- `lexical`
- `semantic`
- `hybrid`

### 7.2 确定性查询

```bash
rks query claims-about Transformer
rks query papers-supporting <claim_id>
rks query evidence-for Transformer
rks query methods-for <paper_id>
rks query datasets-for <paper_id>
```

### 7.3 claim relation 查询

```bash
rks query claim-relations <claim_id>
```

这里最重要的是区分两层：

- `inferred_relations`：查询时推断出的候选关系
- `reviewed_relations`：已经被审阅并持久化的关系

不要把 `inferred_relations` 直接当成 durable truth。

## 8. 直接研究输出

RKS 现在还提供更直接面向用户的输出命令，用来“从图里拿内容”，而不只是查看底层对象。

回答研究问题：

```bash
rks output answer "Sparse Attention 目前有什么结论？"
```

生成主题 briefing：

```bash
rks output brief "Sparse Attention"
```

查看分歧与矛盾：

```bash
rks output disagreements "Sparse Attention"
```

生成研究机会与下一步建议：

```bash
rks output opportunities "Sparse Attention"
```

生成阅读路线、对比结果和审阅优先级：

```bash
rks output reading-list "Sparse Attention"
rks output compare p_000001 p_000002
rks output open-questions "Sparse Attention"
rks output review-priorities "Sparse Attention"
```

这些输出会把 claims、papers、methods、datasets 以及 reviewed / inferred relation 一起组织成更容易消费的结果。

## 9. 手动审阅 claim relation

先查看候选：

```bash
rks query claim-relations <claim_id>
```

如果你要确认其中一条关系，可以 promote：

```bash
rks review promote-claim-relation <source_claim_id> supports <target_claim_id> --reviewed-by human:review --note "checked manually"
```

支持的 relation type：

- `supports`
- `refines`
- `contradicts`

如果要撤回：

```bash
rks review retract-claim-relation <source_claim_id> supports <target_claim_id>
```

promote / retract 后建议重新运行：

```bash
rks query claim-relations <source_claim_id>
rks show claim <source_claim_id>
```

## 10. Agent 模式工作流

如果你想把某一步交给外部 agent，而不是让 RKS 直接调用 provider，可以用 `--mode agent`。

### 9.1 text

```bash
rks extract text <paper_id> --mode agent
rks import text <paper_id> path/to/agent_text.json
```

### 9.2 claims

```bash
rks extract claims <paper_id> --mode agent
rks import claims <paper_id> path/to/agent_claims.json
```

### 9.3 summary

```bash
rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> path/to/agent_summary.json
```

这条路径的特点是：

- RKS 负责创建 request artifact
- 外部 agent 负责生成结果
- RKS 负责 import、校验和持久化

## 11. 任务与状态

查看全部任务：

```bash
rks tasks list
```

查看某个 paper 的任务：

```bash
rks tasks list --paper-id <paper_id>
```

查看单个任务：

```bash
rks tasks show <task_id>
```

标记失败：

```bash
rks tasks fail <task_id> "reason"
```

查看 paper 总体状态：

```bash
rks status paper <paper_id>
```

`status paper` 是最重要的总览命令之一，适合看：

- artifacts
- stages
- readiness level
- missing steps
- blockers
- suggested next commands
- source PDF 状态
- 任务状态
- 持久化的 `agent_reports`
- 针对 queued / running / failed 任务的 `recovery_guidance`

## 12. 批量操作

### 11.1 批量 ingest

```bash
rks batch ingest manifest.json
```

manifest 示例：

```json
[
  {"source_type": "pdf", "path": "paper-1.pdf"},
  {"source_type": "doi", "source_ref": "10.48550/arXiv.1706.03762"},
  {"source_type": "pmid", "source_ref": "31452104"},
  {"source_type": "url", "source_ref": "https://pubmed.ncbi.nlm.nih.gov/31452104/"}
]
```

### 11.2 批量 extract

```bash
rks batch extract claims manifest.json
rks batch extract summary manifest.json --mode agent
rks batch output answer output-manifest.json
```

extract manifest 示例：

```json
[
  {"paper_id": "p_000001"},
  {"paper_id": "p_000002", "mode": "agent"}
]
```

现在 batch 命令都会返回一个 `audit` 区块，用来汇总 success、failure 和该工作流特有的计数。

如果想对单篇 paper 先做高层准备计划，或者直接补齐本地缺失步骤，可以执行：

```bash
rks prepare paper-output <paper_id>
rks prepare paper-output <paper_id> --apply
```

## 13. 导出、导入和服务

导出 graph snapshot：

```bash
rks export graph snapshot.json
```

导入 graph snapshot：

```bash
rks import graph snapshot.json
```

启动本地服务：

```bash
rks serve --host 127.0.0.1 --port 8765
```

## 14. HTTP 接口的基本使用

健康检查：

```bash
curl -s http://127.0.0.1:8765/health
```

查看 paper status：

```bash
curl -s http://127.0.0.1:8765/api/status/<paper_id>
```

查看 claim relations：

```bash
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
```

promote relation：

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "supports",
    "target_claim_id": "c_000014",
    "reviewed_by": "human:http",
    "note": "checked from API"
  }'
```

retract relation：

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "supports",
    "target_claim_id": "c_000014"
  }'
```

## 15. 推荐的最小日常使用集

如果你只想掌握最常用的一组命令，优先记住这些：

```bash
rks ingest pdf <path>
rks show paper <paper_id>
rks extract claims <paper_id>
rks claims <paper_id>
rks output answer "这个主题目前有什么结论？"
rks query claim-relations <claim_id>
rks review promote-claim-relation <source_claim_id> supports <target_claim_id>
rks status paper <paper_id>
```

这组命令已经覆盖了：

- ingest
- graph construction
- 内容输出
- query
- review
- status inspection
问答输出：

```bash
curl -s "http://127.0.0.1:8765/api/output/answer?q=Sparse%20Attention%20outlook"
```

brief 输出：

```bash
curl -s "http://127.0.0.1:8765/api/output/brief?topic=Sparse%20Attention"
```

分歧输出：

```bash
curl -s "http://127.0.0.1:8765/api/output/disagreements?topic=Sparse%20Attention"
```

研究机会输出：

```bash
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=Sparse%20Attention"
```
