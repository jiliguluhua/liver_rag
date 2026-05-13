# Liver RAG

一个面向肝病的医疗决策支持系统，集成 LangGraph 工作流、RAG 检索与医学影像感知，并通过异步任务、SSE 实时事件和文件缓存实现高性能、可追溯的后端执行与状态管理。

当前系统支持：

- 同步咨询接口
- 异步任务提交与状态查询
- `.nii.gz` 影像上传与缓存复用
- 检索与感知并行分支
- 报告生成与单轮医学审查（待改进）
- 咨询记录持久化

## 项目结构

```text
liver-rag/
├─ api/          # FastAPI routes and Pydantic schemas
├─ agents/       # LangGraph workflow, nodes, and state definitions
├─ core/         # Config, database, and shared infrastructure
├─ data/         # Runtime data, corpora, uploads, and evaluation assets
├─ docs/         # Architecture and engineering documents
├─ data/         # Runtime data, corpora, indexes, uploads, and DB artifacts
├─ frontend/     # Streamlit frontend
├─ legacy/       # Archived experimental modules
├─ models/       # Local model weights and configs
├─ perception/   # Medical perception logic
├─ rag/          # Retrieval and preprocessing modules
├─ scripts/      # Manual utilities and demo runners
├─ services/     # Agent wrapper, queue, and event bus
├─ skills/       # Reserved placeholder for helper modules
├─ tests/        # Automated test skeleton
└─ web/          # Static web assets
```

## 核心流程

系统主流程由 [`agents/graph.py`](C:/Users/21204/Desktop/liver-rag/agents/graph.py:1) 编排：

1. `analyzer` 判断意图，并决定是否进入检索分支和感知分支
2. `retriever` 从知识库检索语料证据
3. `perceptor` 读取影像并执行感知，失败时自动降级
4. `reporter` 汇总证据与感知结果生成报告
5. `reviewer` 对生成结果做医学审查

API 层由 [`api/main.py`](C:/Users/21204/Desktop/liver-rag/api/main.py:1) 提供，对外暴露同步、异步、上传、历史记录和 SSE 能力。

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt
```

启动后端 API：

```bash
uvicorn api.main:app --reload
```

启动 Streamlit 前端：

```bash
streamlit run app.py
```

本地手动跑一次 agent：

```bash
python main.py
```

手动运行graph工作流演示脚本：

```bash
python scripts/run_graph_demo.py
```

## 环境变量

主要配置位于 [core/config.py](C:/Users/21204/Desktop/liver-rag/core/config.py:1) 和 `.env`。

常用变量包括：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `LIVER_SERVICE_API_KEY`
- `LIVER_DEFAULT_DICOM_DIR`
- `LIVER_BACKEND_API_URL`
- `LIVER_UPLOAD_CACHE_TTL_HOURS`

当未配置 `LLM_API_KEY` 时，部分节点会进入 fallback 模式，仍可用于测试流程、接口和降级逻辑。

## 主要模块

- `api/`：FastAPI 路由、请求响应 schema、上传与 SSE 接口
- `agents/`：LangGraph 节点、状态定义、路由逻辑
- `services/`：`LiverSmartAgent` 封装、任务队列、事件总线
- `rag/`：混合检索、文本清洗、文档预处理
- `perception/`：医学影像感知逻辑
- `core/`：配置、数据库、ORM 模型和初始化逻辑

## 当前状态

目前已经完成的后端能力：

- FastAPI 同步与异步咨询接口
- LangGraph 多节点工作流编排
- 检索与感知分支的条件路由
- 节点级 trace、warning、error 输出
- 后台任务队列
- SSE 实时事件流
- 咨询与任务状态持久化
- 上传缓存与文件复用

## 测试

项目已经预留标准测试目录：

```text
tests/
├─ conftest.py
├─ unit/
└─ integration/
```

将会优先补这几类测试：

- `agents` 节点单元测试
- `graph` 路由与降级测试
- `api` 接口集成测试
- `jobs` 异步状态流转测试
- `SSE` 事件流测试

当前 README 先写入测试规划，测试用例后续补齐。

## 待优化

- 引入多轮审查
- 引入更好的rag算法
- 引入更好的dicom分割模型

## 说明

- `legacy/` 用于暂存旧实现或实验性模块，不属于当前主链路
- `skills/` 当前仅作为预留目录，不承载主流程代码
- 后端设计说明见 [`docs/backend-architecture.md`](C:/Users/21204/Desktop/liver-rag/docs/backend-architecture.md:1)
