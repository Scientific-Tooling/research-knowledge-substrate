# RKS 安装说明

这份文档说明用户如何安装 RKS，以及不同使用场景下推荐的安装方式。

## 1. 安装方式概览

仓库现在已经补到可正式发布到 PyPI 的状态，但在真正上传 release 之前，最稳妥的默认方式仍然是从源码本地安装。

适合：

- 本地个人使用
- 开发与调试
- 使用 Codex / Claude Code 等 agent 在仓库内操作 RKS

等 release 真正上传到 PyPI 之后，也可以直接安装：

```bash
python -m pip install research-knowledge-substrate
```

Homebrew 和独立桌面安装器目前仍不在范围内。

## 2. 环境要求

安装前请确认本机具备：

- Python `>=3.10`
- `python3`
- `pip`
- 可选：`uv`
- 能正常创建虚拟环境

你可以先检查：

```bash
python3 --version
python3 -m pip --version
uv --version
```

## 3. 从源码安装

### 3.1 获取代码

```bash
git clone <repo-url>
cd research-knowledge-substrate
```

### 3.2 创建虚拟环境

```bash
python3 -m venv .venv
. .venv/bin/activate
```

如果你习惯用 `uv`，也可以这样：

```bash
uv venv
. .venv/bin/activate
```

### 3.3 安装 RKS

```bash
python -m pip install -e .
```

如果使用 `uv`：

```bash
uv pip install -e .
```

这里使用的是 editable install，适合当前项目阶段：

- 安装后可以直接运行 `rks`
- 仓库内代码变动会立刻反映到当前环境

## 4. 发布到 PyPI 之后的安装方式

当 release 已经上传到 PyPI 后，标准安装方式会变成：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install research-knowledge-substrate
```

对应的 `uv` 安装方式：

```bash
uv venv
. .venv/bin/activate
uv pip install research-knowledge-substrate
```

## 5. 初始化工作区

安装完成后，建议立刻初始化：

```bash
rks config init
rks init-db
rks migrate
```

查看生效配置：

```bash
rks config show
```

## 6. 验证安装是否成功

至少执行这几步：

```bash
rks --help
rks config show
rks init-db
```

如果命令能正常执行，说明安装基本成功。

你也可以继续试一条最小 ingest：

```bash
printf '%s\n' '%PDF-1.4' 'Hello RKS.' > sample.pdf
rks ingest pdf sample.pdf
```

## 7. LLM / Agent 相关准备

### 6.1 使用 `llm-api` 模式

如果你要让 RKS 直接调用模型接口，需要设置 API key，例如：

```bash
export RKS_LLM_API_KEY=...
export RKS_LLM_MODEL=gpt-4.1-mini
```

然后可以执行：

```bash
rks extract text <paper_id> --mode llm-api
rks extract claims <paper_id> --mode llm-api
rks summarize paper <paper_id> --mode llm-api
```

### 6.2 使用外部 agent 模式

如果你使用 Codex、Claude Code 或其他 agent，则通常不需要让 RKS 自己持有模型调用权限，可以直接使用：

```bash
rks extract text <paper_id> --mode agent
rks extract claims <paper_id> --mode agent
rks summarize paper <paper_id> --mode agent
```

然后通过 `import` 路径导入 agent 结果。

## 8. 推荐安装形态

### 7.1 普通用户

推荐：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

如果用户本来就偏好 `uv`，也可以直接用：

```bash
uv venv
. .venv/bin/activate
uv pip install -e .
```

这是当前最稳妥的方式。

### 7.2 开发者

同样推荐 editable install，因为你很可能会改文档、代码或测试。

### 7.3 Agent 操作环境

如果仓库会被 Codex / Claude Code 直接操作，也推荐 editable install，并且确保：

- 虚拟环境已激活
- `rks` 命令在当前 shell 可用
- 数据目录写入权限正常

## 9. 卸载或重建

如果你想重建环境，最简单的方法通常是删除虚拟环境后重新创建：

```bash
rm -rf .venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

如果只是想清空当前工作区数据，可以删除工作目录下的 `data/`，但这会移除本地数据库和 artifacts。

## 10. 常见问题

### 9.1 `rks` 命令找不到

通常原因是：

- 虚拟环境没有激活
- `pip install -e .` 没有成功执行

请先重新执行：

```bash
. .venv/bin/activate
python -m pip install -e .
```

如果你使用的是 `uv`，可以改成：

```bash
. .venv/bin/activate
uv pip install -e .
```

### 9.2 Python 版本不够

请升级到 Python `3.10` 或更高版本。

### 9.3 初始化后没有看到数据库文件

执行：

```bash
rks config show
```

确认 `data_dir` 指向哪里。数据库通常在：

```text
<data_dir>/rks.sqlite3
```

## 11. 后续阅读

安装完成后，建议继续阅读：

- [user-usage-guide-zh.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/user-usage-guide-zh.md)
- [agent-usage-guide-zh.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/agent-usage-guide-zh.md)
- [manual-testing-guide-zh.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/manual-testing-guide-zh.md)
- [pypi-publishing-guide-zh.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/pypi-publishing-guide-zh.md)
