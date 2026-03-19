# RKS 使用说明手册

本手册提供一套可直接执行的 RKS 全流程操作说明，面向日常研究工作。

## 1. 前置条件

- Shell 中可用 Python 3.10+
- 已获取仓库代码
- 本地目录具备写权限

LLM 模式可选配置：

- `RKS_LLM_API_KEY`
- `RKS_LLM_MODEL`
- `RKS_LLM_BASE_URL`（若不使用默认 OpenAI-compatible 端点）

## 2. 安装与初始化

在仓库根目录执行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

初始化本地状态：

```bash
rks config init
rks init-db
rks migrate
rks config show
```

## 3. 快速上手（10 分钟路径）

```bash
rks ingest pdf path/to/paper.pdf
rks extract claims <paper_id>
rks claims <paper_id>
rks query claims-about Transformer
rks output brief "Transformer"
```

最重要的实践：始终从命令输出读取 ID（`paper_id`、`claim_id` 等），不要手写猜测。

## 4. 导入文献

### 4.1 本地 PDF

```bash
rks ingest pdf path/to/paper.pdf
rks show paper <paper_id>
rks status paper <paper_id>
```

### 4.2 DOI / arXiv / PMID

```bash
rks ingest doi 10.48550/arXiv.1706.03762
rks ingest arxiv 1706.03762
rks ingest pmid 31452104
```

导入后建议检查：

- 是否生成 metadata artifact
- `source_pdf.acquisition.status`
- `rks status paper <paper_id>` 给出的下一步建议

### 4.3 规范 URL

```bash
rks ingest url https://doi.org/10.48550/arXiv.1706.03762
rks ingest url https://pubmed.ncbi.nlm.nih.gov/31452104/
rks ingest url https://example.org/paper.pdf
```

## 5. 抽取流程

### 5.1 抽取 text

```bash
rks extract text <paper_id>
rks extract text <paper_id> --mode heuristic
rks extract text <paper_id> --mode llm-api
rks extract text <paper_id> --mode agent
```

### 5.2 抽取 claims

```bash
rks extract claims <paper_id>
rks extract claims <paper_id> --mode heuristic
rks extract claims <paper_id> --mode llm-api
rks extract claims <paper_id> --mode agent
```

### 5.3 抽取 methods / datasets

```bash
rks extract methods <paper_id>
rks extract datasets <paper_id>
```

### 5.4 生成 summary

```bash
rks summarize paper <paper_id>
rks summarize paper <paper_id> --mode llm-api
rks summarize paper <paper_id> --mode agent
```

## 6. 查看与检索

### 6.1 对象查看

```bash
rks show paper <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
rks methods <paper_id>
rks datasets <paper_id>
rks show claim <claim_id>
```

### 6.2 搜索与确定性查询

```bash
rks search Transformer
rks search "translation quality benchmark" --mode semantic
rks query claims-about Transformer
rks query papers-supporting <claim_id>
rks query evidence-for Transformer
rks query claim-relations <claim_id>
```

## 7. 审阅并持久化 Claim Relation

先查看候选关系：

```bash
rks query claim-relations <claim_id>
```

提升为已审阅关系：

```bash
rks review promote-claim-relation <from_claim_id> supports <to_claim_id> --reviewed-by human:analyst
```

撤回已审阅关系：

```bash
rks review retract-claim-relation <from_claim_id> supports <to_claim_id>
```

## 8. 项目与假设工作流

创建项目并关联证据：

```bash
rks project create --name "Sparse Attention Review" --research-question "Which papers matter most for realistic long-context evaluation?"
rks project add-paper <project_id> <paper_id> --link-type key_evidence
rks project add-link <project_id> claim <claim_id> --link-type key_evidence
rks project links <project_id>
rks show project <project_id>
```

创建并跟踪假设：

```bash
rks hypothesis create <project_id> --text "Sparse attention gains hold only under realistic benchmarks."
rks hypothesis add-evidence <hypothesis_id> paper <paper_id> --relation-type supported_by
rks hypothesis evidence <hypothesis_id>
rks show hypothesis <hypothesis_id>
```

## 9. 研究输出

按主题输出：

```bash
rks output answer "What does the graph say about Sparse Attention?"
rks output brief "Sparse Attention"
rks output disagreements "Sparse Attention"
rks output opportunities "Sparse Attention"
rks output reading-list "Sparse Attention"
rks output open-questions "Sparse Attention"
rks output review-priorities "Sparse Attention"
```

按项目输出：

```bash
rks output project-answer <project_id> --question "What does current evidence support?"
rks output project-brief <project_id>
rks output project-reading-list <project_id>
rks output project-disagreements <project_id>
rks output project-open-questions <project_id>
rks output project-review-priorities <project_id>
```

## 10. Agent 模式请求/回写

`agent` 模式下的标准回路：

```bash
rks extract text <paper_id> --mode agent
rks import text <paper_id> path/to/text_result.json
rks extract claims <paper_id> --mode agent
rks import claims <paper_id> path/to/claims_result.json
rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> path/to/summary_result.json
```

查看任务生命周期：

```bash
rks tasks list
rks tasks show <task_id>
rks status paper <paper_id>
```

## 11. 批处理与导出

批处理：

```bash
rks batch ingest manifest.json
rks batch extract claims manifest.json
rks batch output brief manifest.json
```

图谱快照导入导出：

```bash
rks export graph snapshot.json
rks import graph snapshot.json
```

## 12. 本地服务与 HTTP 镜像接口

启动服务：

```bash
rks serve --host 127.0.0.1 --port 8765
```

常用接口：

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s "http://127.0.0.1:8765/api/output/brief?topic=Sparse%20Attention"
```

## 13. 常见问题排查

### 13.1 `rks: command not found`

- 确认已激活虚拟环境
- 运行 `python -m pip install -e .`
- 或在仓库根目录使用 `PYTHONPATH=src python3 -m rks ...`

### 13.2 LLM API 报错

- 检查 `RKS_LLM_API_KEY`
- 检查 `llm.base_url`
- 可切回 `--mode heuristic` 做本地兜底

### 13.3 导入后输出缺失

- `rks status paper <paper_id>`
- `rks show paper <paper_id>` 检查 artifacts
- 关注 `source_pdf` 获取状态是 unavailable / failed / skipped

## 14. 操作最佳实践

- 永远从输出读取 ID，不手写猜测
- 每次写操作后都立刻读回对象核对
- 关系持久化通过 `review` 命令，不直接改库
- 项目和假设链接要显式，保证决策可追溯
- CLI 为主语义，HTTP 用于集成和交叉检查

## 15. 相关文档

- 产品介绍：`docs/product-introduction-zh.md`
- 用户操作：`docs/user-usage-guide-zh.md`
- Agent 操作：`docs/agent-usage-guide-zh.md`
- 手动测试：`docs/manual-testing-guide-zh.md`
