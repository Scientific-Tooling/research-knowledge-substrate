# RKS 手动测试说明

这份文档用于手动验证当前 RKS 的核心产品链路，重点覆盖：

- 输入完整性
- 语义审阅与持久化
- agent-facing CLI / HTTP 操作接口

不包含前端视觉检查，也不包含复杂 autonomous orchestration 测试。

## 1. 测试目标

建议优先验证下面三类能力：

1. 参考文献 ingest 后，系统是否能保留元数据、抽取文本，并在可能时获取原始 PDF。
2. claim relation 是否明确区分 `inferred` 和 `reviewed`，并能被 promote / retract。
3. CLI 与 HTTP 接口是否对外暴露同一套稳定操作，而不是各自拼装不同结果。

## 2. 测试前准备

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

建议先查看当前配置：

```bash
rks config show
```

重点确认：

- `data_dir` 指向当前工作目录下的数据目录
- `reference_pdf_acquisition` 默认是 `auto`

## 3. 场景一：本地 PDF ingest 与基础抽取

先准备一个最小 PDF 文件，例如：

```bash
printf '%s\n' '%PDF-1.4' 'Sparse Attention improves translation accuracy on WMT14.' > sample.pdf
```

执行 ingest：

```bash
rks ingest pdf sample.pdf
```

记录返回的 `paper_id`，例如 `p_000001`。

接着执行：

```bash
rks show paper p_000001
rks extract claims p_000001
rks claims p_000001
rks status paper p_000001
```

预期结果：

- `show paper` 中存在 `source_pdf` artifact
- `extract claims` 成功返回 `claim_count`
- `claims` 能列出至少一条 claim
- `status paper` 中 `stages.text=true`、`stages.claims=true`

同时检查文件系统：

- `data/papers/p_000001/source.pdf`
- `data/papers/p_000001/extracted_text.json`
- `data/papers/p_000001/structured_claims.json`

## 4. 场景二：DOI / arXiv 参考文献 ingest

测试 DOI：

```bash
rks ingest doi 10.48550/arXiv.1706.03762
```

或测试 arXiv：

```bash
rks ingest arxiv 1706.03762
```

记录返回的 `paper_id`，然后执行：

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

预期结果：

- 一定会有 `metadata` artifact
- 如果元数据含摘要，通常会有 `extracted_text` artifact
- 一定会有 `source_pdf_acquisition` artifact
- 如果 provider 暴露了可下载 PDF 且下载成功，`pdf_path` 不为空，并且 `source_pdf.available=true`

重点看 `status paper` 输出中的这部分：

- `source_pdf.available`
- `source_pdf.path`
- `source_pdf.acquisition.status`

可能的状态包括：

- `downloaded`
- `unavailable`
- `failed`
- `skipped`

对应文件系统检查：

- `data/papers/<paper_id>/metadata.json` 或 `metadata.xml`
- `data/papers/<paper_id>/source_pdf_acquisition.json`
- 如果成功下载，还应有 `data/papers/<paper_id>/source.pdf`

## 5. 场景三：claim relation 的候选与审阅闭环

这个场景建议用两到三个 paper 构造可对比的 claim。

### 5.1 准备三个占位 PDF

```bash
printf '%s\n' '%PDF-1.4' 'placeholder' > paper-1.pdf
printf '%s\n' '%PDF-1.4' 'placeholder' > paper-2.pdf
printf '%s\n' '%PDF-1.4' 'placeholder' > paper-3.pdf
```

依次 ingest：

```bash
rks ingest pdf paper-1.pdf
rks ingest pdf paper-2.pdf
rks ingest pdf paper-3.pdf
```

### 5.2 为每篇 paper 导入 claims

为第一篇构造：

```json
{
  "claims": [
    {
      "text": "Sparse Attention improves translation accuracy on WMT14.",
      "predicate": "improves",
      "object_text": "translation accuracy",
      "context": {
        "subject_text": "Sparse Attention",
        "dataset": "WMT14"
      },
      "evidence": {
        "paper_id": "p_000001"
      },
      "confidence": 0.9
    }
  ]
}
```

第二篇改成 `IWSLT`，第三篇改成 `does not improve`。分别保存成三个 JSON，然后执行：

```bash
rks import claims p_000001 paper-1-claims.json
rks import claims p_000002 paper-2-claims.json
rks import claims p_000003 paper-3-claims.json
```

先查看 anchor claim：

```bash
rks claims p_000001
```

拿到 `c_...` 之后执行：

```bash
rks query claim-relations <anchor_claim_id>
```

预期结果：

- `reviewed_relations` 初始应为空
- `inferred_relations` 中应出现至少一个 `refines`
- `inferred_relations` 中应出现至少一个 `contradicts`

### 5.3 promote 一个 reviewed relation

选择一个候选关系后执行：

```bash
rks review promote-claim-relation <anchor_claim_id> contradicts <target_claim_id> --reviewed-by agent:review --note "manual verification"
```

然后再次查询：

```bash
rks query claim-relations <anchor_claim_id>
rks show claim <anchor_claim_id>
```

预期结果：

- `reviewed_relations` 中出现一条 `contradicts`
- 该 relation 带有 `relation_source=reviewed`
- `created_by` 为 `agent:review`
- `metadata.note` 为你写入的说明
- `show claim` 中也能看到 `reviewed_relations`

### 5.4 retract 已审阅关系

```bash
rks review retract-claim-relation <anchor_claim_id> contradicts <target_claim_id>
```

再次查询：

```bash
rks query claim-relations <anchor_claim_id>
```

预期结果：

- 刚才 promote 的 relation 不再出现在 `reviewed_relations`
- 但相应候选关系仍可能继续出现在 `inferred_relations`

这一步很重要，因为它验证了“候选层”和“事实层”确实是分离的。

## 6. 场景四：paper status 的 agent-facing 操作接口

先启动本地服务：

```bash
rks serve --host 127.0.0.1 --port 8765
```

另开一个终端窗口调用 HTTP 接口。

### 6.1 健康检查

```bash
curl -s http://127.0.0.1:8765/health
```

预期结果：

```json
{"status":"ok"}
```

### 6.2 查询 paper status

```bash
curl -s http://127.0.0.1:8765/api/status/<paper_id>
```

预期结果：

- 返回 `paper`
- 返回 `artifacts`
- 返回 `stages`
- 返回 `source_pdf`
- 返回 `tasks`

这个结果应与：

```bash
rks status paper <paper_id>
```

在语义上保持一致。

### 6.3 查询 claim relations

```bash
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
```

预期结果：

- 同时包含 `reviewed_relations`
- 同时包含 `inferred_relations`
- 两层语义不要混成一个不可区分的数组

### 6.4 通过 HTTP promote / retract relation

promote：

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "contradicts",
    "target_claim_id": "c_000003",
    "reviewed_by": "agent:http",
    "note": "manual api test"
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

预期结果：

- promote 返回一条 edge payload
- retract 返回 `deleted: true`
- 再次调用 `GET /api/claims/<claim_id>/relations` 时，结果应同步变化

## 7. 场景五：agent 模式任务链路

选择一个 paper 执行：

```bash
rks extract text <paper_id> --mode agent
rks extract claims <paper_id> --mode agent
rks summarize paper <paper_id> --mode agent
```

预期结果：

- 命令返回 `task_id`
- `tasks list` 能看到 `queued` 状态任务
- `status paper <paper_id>` 的 `tasks` 和 `task_summary` 会反映当前状态

接着用已有 schema 的结果文件导入：

```bash
rks import text <paper_id> agent_text.json
rks import claims <paper_id> agent_claims.json
rks import summary <paper_id> agent_summary.json
```

预期结果：

- 相应任务会转为 `completed`
- `result_artifact_id` 被填充
- 对应 artifact 出现在 paper 目录和 `show paper` 中

如果需要模拟失败：

```bash
rks tasks fail <task_id> "manual failure simulation"
```

预期结果：

- 任务状态变成 `failed`
- `status paper` 的 `task_summary.failed` 增加

## 8. 推荐检查项

每完成一个场景，建议都检查三层是否一致：

1. CLI 输出是否正确
2. `data/papers/<paper_id>/` 下工件是否存在
3. HTTP 接口返回是否与 CLI 语义一致

如果三层有一层不一致，通常就说明产品操作面还没有真正收敛。

## 9. 常见问题

### 9.1 DOI / arXiv ingest 没有拿到 PDF，是不是失败了？

不一定。只要有 `source_pdf_acquisition` artifact，就说明系统已经把结果记录下来了。需要看它的 `status` 是：

- `unavailable`：provider 没给可用 PDF 候选
- `failed`：尝试过，但下载失败
- `skipped`：配置或流程明确跳过

### 9.2 为什么 retract 之后关系还会出现？

如果它仍出现在 `inferred_relations`，这是正常的。因为 retract 删除的是 reviewed durable edge，不会关闭 query-time inference。

### 9.3 需要重点关注哪些回归风险？

- reference ingest 成功但没有落 `source_pdf_acquisition`
- reviewed relation 被 extraction rerun 清掉
- CLI 与 HTTP 返回结构不一致
- `show claim` 看不到 reviewed relation
- `status paper` 不再反映 source PDF 获取状态

## 10. 建议的最小验收集

如果你时间有限，至少执行这 6 步：

1. `rks ingest pdf sample.pdf`
2. `rks ingest arxiv 1706.03762`
3. `rks status paper <paper_id>`
4. `rks query claim-relations <claim_id>`
5. `rks review promote-claim-relation ...`
6. `curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations`

这 6 步已经能覆盖当前最重要的产品链路。
