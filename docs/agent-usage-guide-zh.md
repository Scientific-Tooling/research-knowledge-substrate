# RKS Agent 操作说明

这份文档面向外部 AI agent，例如 Codex、Claude Code 或其他能够执行终端命令和 HTTP 请求的 agent。重点是如何把 RKS 当成一个可驱动的产品接口来使用。

## 1. 适用目标

适合下面几类 agent 任务：

- 帮用户 ingest 文献并构建 graph
- 从已有 graph 中回答问题
- 执行 claim relation 审阅闭环
- 驱动 `agent` 模式的 request / import 工作流
- 调用 HTTP 接口做读写和一致性检查
- 运行自动化验证或演示流程

如果你是人工用户，请看 [user-usage-guide-zh.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/user-usage-guide-zh.md)。

## 2. Agent 的基本原则

外部 agent 操作 RKS 时，遵守这几条：

- 从仓库根目录运行
- 优先使用 `rks` CLI，必要时再使用 HTTP 接口
- 永远从命令输出中读取 `paper_id`、`claim_id`、`task_id`
- 不要手工改数据库
- 写操作之后一定重新读取状态
- claim relation 必须区分 `inferred_relations` 和 `reviewed_relations`
- reference ingest 之后必须检查 `source_pdf_acquisition`

## 3. 初始化工作区

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

初始化 RKS：

```bash
rks config init
rks init-db
rks migrate
rks config show
```

agent 需要特别关注：

- `data_dir`
- `reference_pdf_acquisition`
- `llm` 配置

如果还需要把仓库专用 skills 一并交给 agent，安装后可以直接导出：

```bash
rks skills list
rks skills export ./rks-agent-kit
```

导出目录会包含：

- `./rks-agent-kit/skills/`
- `./rks-agent-kit/skills-index.json`
- `./rks-agent-kit/AGENTS.md`
- `./rks-agent-kit/CLAUDE.md`

推荐交付方式：

- Codex：使用 `AGENTS.md` 和 `skills/`
- Claude Code：使用 `CLAUDE.md` 和 `skills/`
- 其他 agent 工具：读取 `skills-index.json` 和原始 `SKILL.md`

## 4. Agent 的标准操作路径

一个通用的 agent 工作流通常如下：

1. 初始化环境
2. ingest 数据
3. 检查 artifacts 和 status
4. 抽取 claims 或导入 agent 结果
5. 执行 query / search / output / summarize
6. 审阅 claim relations
7. 使用 HTTP 接口交叉验证
8. 输出结构化结果

## 5. Ingest 与构图

### 5.1 本地 PDF

```bash
rks ingest pdf <path>
```

拿到 `paper_id` 后：

```bash
rks show paper <paper_id>
rks status paper <paper_id>
rks extract claims <paper_id>
```

### 5.2 DOI / arXiv

```bash
rks ingest doi <doi>
rks ingest arxiv <id>
```

拿到 `paper_id` 后必须检查：

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

最重要的检查点：

- `metadata` artifact
- `source_pdf_acquisition` artifact
- `source_pdf.available`
- `source_pdf.acquisition.status`

如果下载成功，还要确认：

- `data/papers/<paper_id>/source.pdf` 存在

如果需要把人工判断或后续动作挂到 paper 上，不要只留在 agent 对话里，直接写成 paper note：

```bash
rks note add paper <paper_id> --content "需要人工对照 follow-up reproduction。" --created-by agent:review
rks note list paper <paper_id>
```

对应的 HTTP 入口：

```bash
curl -s http://127.0.0.1:8765/api/papers/<paper_id>/notes
curl -s -X POST http://127.0.0.1:8765/api/papers/<paper_id>/notes -H 'Content-Type: application/json' -d '{"content":"需要人工对照 follow-up reproduction。","created_by":"agent:review"}'
```

### 5.3 重复 paper 检测与合并

如果出现重复 paper，先检测再合并：

```bash
rks papers find-duplicates
rks papers find-duplicates --mode identifiers
```

确认后合并到一个 canonical paper ID：

```bash
rks papers merge <target_paper_id> <source_paper_id> --prefer target
rks show paper <target_paper_id>
```

agent 建议：

- 如果更关注精确率，优先使用 `--mode identifiers`
- merge 时优先保留 metadata 更完整或已被 project/hypothesis 引用的记录作为 `target_paper_id`

## 6. Agent 模式的 request / import 闭环

对于需要外部 agent 产出的任务，RKS 用 `agent` 模式暴露 request/import 边界。

### 6.1 text

```bash
rks extract text <paper_id> --mode agent
```

然后由 agent 生成结果，再导入：

```bash
rks import text <paper_id> <json_path>
```

### 6.2 claims

```bash
rks extract claims <paper_id> --mode agent
rks import claims <paper_id> <json_path>
```

### 6.3 summary

```bash
rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> <json_path>
```

关键要求：

- 不要跳过 import 路径直接改库
- 先记录 `task_id`
- import 后重新检查 `tasks show` 和 `status paper`

## 7. 查询与回答

### 7.1 最常用读取命令

```bash
rks show paper <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
rks show claim <claim_id>
rks methods <paper_id>
rks datasets <paper_id>
```

### 7.2 搜索与 query

```bash
rks search <query>
rks search <query> --mode semantic
rks query claims-about <concept>
rks query papers-supporting <claim_id>
rks query evidence-for <target>
rks query claim-relations <claim_id>
```

agent 在回答用户问题时，推荐顺序是：

1. `rks search`
2. `rks query claims-about`
3. `rks show claim`
4. `rks query claim-relations`
5. `rks output answer`
6. `rks summarize paper`

### 7.3 直接输出层

回答研究问题：

```bash
rks output answer "Sparse Attention 目前有什么结论？"
```

生成主题 briefing：

```bash
rks output brief "Sparse Attention"
```

查看分歧：

```bash
rks output disagreements "Sparse Attention"
```

生成研究机会：

```bash
rks output opportunities "Sparse Attention"
```

生成阅读路线、对比结果和审阅优先级：

```bash
rks output reading-list "Sparse Attention"
rks output compare c_000001 c_000002
rks output open-questions "Sparse Attention"
rks output review-priorities "Sparse Attention"
```

当用户真正想要“内容、综合、灵感、下一步建议”时，这组命令应优先于只返回底层 graph 对象的命令。

### 7.4 单篇文献讨论闭环（用户 <-> agent）

当用户希望围绕单篇文献持续讨论时，建议执行这个闭环：

1. 锚定 paper
2. 从 RKS 读取上下文
3. 按用户问题扩展证据
4. 用明确 ID 回答
5. 把结论写回 RKS

最小命令序列：

```bash
rks show paper <paper_id>
rks status paper <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
rks note list paper <paper_id>
```

若状态显示抽取缺失：

```bash
rks extract text <paper_id>
rks extract claims <paper_id>
rks extract methods <paper_id>
rks extract datasets <paper_id>
rks summarize paper <paper_id>
```

针对后续问题扩展证据：

```bash
rks query claims-about <concept_or_concept_id>
rks query papers-supporting <claim_id>
rks query claim-relations <claim_id>
rks search "<follow-up query>"
```

把讨论结论持久化（不要只留在聊天记录里）：

```bash
rks note add paper <paper_id> --content "<结论或下一步动作>" --created-by agent:discussion
rks note list paper <paper_id>
```

如果讨论是在 project 范围内：

```bash
rks note add project <project_id> --content "<讨论结论>" --created-by agent:discussion
rks hypothesis create <project_id> --text "<可检验假设>" --status draft --created-by agent:discussion
rks hypothesis add-evidence <hypothesis_id> claim <claim_id> --relation-type supported_by --created-by agent:discussion
```

## 8. claim relation 审阅闭环

### 8.1 先看候选关系

```bash
rks query claim-relations <claim_id>
```

返回里通常有：

- `inferred_relations`
- `reviewed_relations`

agent 必须先读取候选，再决定是否 promote。

### 8.2 promote

```bash
rks review promote-claim-relation <source_claim_id> <relation_type> <target_claim_id> --reviewed-by agent:review --note "why promoted"
```

### 8.3 retract

```bash
rks review retract-claim-relation <source_claim_id> <relation_type> <target_claim_id>
```

### 8.4 promote / retract 后必须重读

```bash
rks query claim-relations <source_claim_id>
rks show claim <source_claim_id>
```

agent 需要确认：

- `reviewed_relations` 是否变化
- `inferred_relations` 是否仍独立存在
- `created_by` 是否正确

## 9. 任务与状态

查看任务：

```bash
rks tasks list
rks tasks list --paper-id <paper_id>
rks tasks show <task_id>
```

标记失败：

```bash
rks tasks fail <task_id> "reason"
```

查看 paper 状态：

```bash
rks status paper <paper_id>
```

对 agent 来说，`status paper` 是最重要的综合检查入口之一。

优先看这些字段：

- `readiness.current_level`
- `missing_steps`
- `blockers`
- `suggested_next_commands`
- `recovery_guidance`
- `agent_reports`
- `task_summary`

如果想让系统先给出单篇 paper 的高层准备计划，或者直接补齐本地缺失步骤，可以执行：

```bash
rks prepare paper-output <paper_id>
rks prepare paper-output <paper_id> --apply
```

## 10. HTTP 接口使用方式

### 10.1 启动服务

```bash
rks serve --host 127.0.0.1 --port 8765
```

### 10.2 读取接口

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
curl -s "http://127.0.0.1:8765/api/output/answer?q=Sparse%20Attention%20outlook"
curl -s "http://127.0.0.1:8765/api/output/brief?topic=Sparse%20Attention"
curl -s "http://127.0.0.1:8765/api/output/disagreements?topic=Sparse%20Attention"
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=Sparse%20Attention"
curl -s -X POST http://127.0.0.1:8765/api/prepare/papers/<paper_id>/output \
  -H 'Content-Type: application/json' \
  -d '{"apply": false}'
```

### 10.3 写接口

promote：

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "contradicts",
    "target_claim_id": "c_000003",
    "reviewed_by": "agent:http",
    "note": "promoted through http"
  }'
```

retract：

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "contradicts",
    "target_claim_id": "c_000003"
  }'
```

### 10.4 CLI / HTTP 一致性要求

agent 在调用 HTTP 写接口之后，建议立刻再用 CLI 校验：

```bash
rks query claim-relations <source_claim_id>
rks show claim <source_claim_id>
```

不要只看单一通道。

## 11. 推荐给 Agent 的输出格式

agent 最后回报时，建议按这个结构输出：

1. 环境状态
2. 使用的对象 ID
3. ingest 结果
4. artifact / status 结果
5. query / retrieval 结果
6. reviewed relation 结果
7. CLI / HTTP 一致性结果
8. 失败项与原因

## 12. 常见错误

### 12.1 猜 ID

错误做法：

- 直接假设 `p_000001`
- 直接假设某个 claim ID

正确做法：

- 从 JSON 输出读取 ID

### 12.2 跳过 artifact 检查

错误做法：

- 只看命令返回成功

正确做法：

- 再看 `show paper`
- 再看 `status paper`
- 必要时检查 `data/papers/<paper_id>/`

### 12.3 把 inferred 当成 durable truth

错误做法：

- 看到 `inferred_relations` 就直接对用户说“系统已经确认”

正确做法：

- 只有 `reviewed_relations` 才代表持久化后的审阅事实

### 12.4 import 之外直接改库

错误做法：

- 通过 SQL 直接插入 task、claim 或 edge

正确做法：

- 用 `import`、`review`、CLI 或 HTTP 操作面

## 13. 推荐的最小 Agent 操作集

如果一个 agent 只需要掌握最小的一套 RKS 操作，至少覆盖这些：

```bash
rks config show
rks ingest pdf <path>
rks show paper <paper_id>
rks status paper <paper_id>
rks extract claims <paper_id>
rks claims <paper_id>
rks query claim-relations <claim_id>
rks review promote-claim-relation <source_claim_id> supports <target_claim_id>
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
```

这套已经足够让 agent：

- ingest
- inspect
- build graph
- query
- review
- 做 CLI / HTTP 交叉验证
