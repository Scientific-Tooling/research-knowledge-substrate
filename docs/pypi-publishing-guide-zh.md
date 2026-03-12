# PyPI 发布指南

这份文档说明如何把 RKS 以可重复的方式发布到 PyPI。

## 1. 这里所说的“PyPI-ready”

当前仓库达到 “PyPI-ready” 的含义是：

- [pyproject.toml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/pyproject.toml) 中的包元数据已经补齐到可公开分发的程度
- PyPI 展示用 README 单独收敛到 [README-PYPI.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/README-PYPI.md)
- 迁移文件已经随 wheel 一起打包到 [src/rks/migrations](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/src/rks/migrations)
- 可以构建出 `sdist` 和 `wheel`
- 生成的分发包能通过 `twine check`

这份文档本身不会执行发布，它定义的是维护者应该遵循的流程。

## 2. 维护者的一次性准备

1. 在 PyPI 上创建项目，或先确认包名可用。
2. 决定仓库使用哪种发布方式：
   - GitHub Actions secret `PYPI_API_TOKEN`
   - GitHub Trusted Publishing
3. 如果使用 token 方式，在 GitHub 仓库里配置 `PYPI_API_TOKEN`。

仓库当前附带的 workflow 默认按 token 方式写好了。

## 3. 本地发布前校验

先创建一个干净的虚拟环境，并安装 release 工具：

```bash
python3 -m venv .release-venv
. .release-venv/bin/activate
python -m pip install -U pip
python -m pip install .[release]
```

运行测试：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

构建分发包：

```bash
python -m build --sdist --wheel
```

检查包元数据和 README 渲染：

```bash
python -m twine check dist/*
```

预期结果：

- `dist/` 下出现 source distribution
- `dist/` 下出现 wheel
- `twine check` 通过，没有元数据或渲染错误

## 4. 版本管理

当前包版本定义在 [src/rks/__init__.py](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/src/rks/__init__.py)，并通过 [pyproject.toml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/pyproject.toml) 的 dynamic metadata 暴露出去。

每次发布前：

1. 更新 `rks.__version__`
2. 确认 release notes 和文档同步
3. 重新构建分发包

## 5. GitHub Actions

仓库现在包含两个 workflow：

- [package-check.yml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/.github/workflows/package-check.yml)
  负责跑测试、构建包、执行 `twine check`
- [publish-pypi.yml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/.github/workflows/publish-pypi.yml)
  在推送 `v0.1.0` 这类 tag 时发布到 PyPI，前提是 `PYPI_API_TOKEN` 已配置

## 6. 发布流程

1. 确认 `main` 干净，所有需要发布的改动已经合并。
2. 在 [src/rks/__init__.py](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/src/rks/__init__.py) 里 bump 版本号。
3. 运行第 3 节的本地校验。
4. 提交版本号和 release notes。
5. 创建并推送 tag：

```bash
git tag v0.1.0
git push origin v0.1.0
```

6. 在 GitHub Actions 里观察 `publish-pypi` workflow。
7. 发布完成后，从 PyPI 做一次真实安装验证：

```bash
python3 -m venv /tmp/rks-smoke
. /tmp/rks-smoke/bin/activate
python -m pip install research-knowledge-substrate
rks --help
```

## 7. 说明

- 运行时默认仍然是本地 workspace，根目录来自当前目录或 `RKS_ROOT`
- 当前发布的是 CLI 和本地 HTTP 服务，不是托管 SaaS
- 如果首次发布前包名有变化，需要同时更新 [pyproject.toml](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/pyproject.toml)、[README-PYPI.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/README-PYPI.md) 和这份文档
