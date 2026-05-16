# Liver RAG

一个面向肝病场景的医疗决策支持系统，集成 LangGraph 工作流、RAG 检索与医学影像感知，并通过异步任务、SSE 实时事件、可切换的 Redis pub/sub 事件分发与文件缓存实现可追溯的后端执行与状态管理。

当前系统支持：

- 统一咨询入口，支持 `auto`、`sync`、`async` 三种提交模式
- 同步咨询接口
- 异步任务提交与状态查询
- `.nii.gz` 影像上传与缓存复用
- 检索与感知并行分支
- 报告生成与单轮医学审查
- 咨询记录持久化

## 文档导航

- API 接口说明见：[docs/api_documentation.md](C:/Users/21204/Desktop/liver-rag/docs/api_documentation.md:1)
- 后端架构说明见：[docs/backend_architecture.md](C:/Users/21204/Desktop/liver-rag/docs/backend_architecture.md:1)

## 项目结构

```text
liver-rag/
├─ api/          # FastAPI routes and Pydantic schemas
├─ agents/       # LangGraph workflow, routing, nodes, and state definitions
├─ core/         # Config, database, and shared infrastructure
├─ data/         # Runtime data, corpora, indexes, uploads, and evaluation assets
├─ docs/         # Architecture and engineering documents
├─ frontend/     # Streamlit frontend
├─ legacy/       # Archived experimental modules
├─ models/       # Local model weights and configs
├─ perception/   # Medical perception logic
├─ rag/          # Retrieval and preprocessing modules
├─ scripts/      # Manual utilities and demo runners
├─ services/     # Agent wrapper, queue, and event bus
├─ skills/       # Reserved placeholder for helper modules
├─ tests/        # Automated test suite
└─ web/          # Static web assets
```

## 核心流程

系统主流程由 [agents/graph.py](C:/Users/21204/Desktop/liver-rag/agents/graph.py:1) 编排：

1. `analyzer` 判断意图，并决定是否进入检索分支和感知分支
2. `retriever` 从知识库检索语料证据
3. `perceptor` 读取影像并执行感知，失败时自动降级
4. `reporter` 汇总证据与感知结果生成报告
5. `reviewer` 对生成结果做医学审查

API 层由 [api/main.py](C:/Users/21204/Desktop/liver-rag/api/main.py:1) 提供，对外暴露统一 `dispatch` 入口、同步接口、异步任务接口、上传接口、历史记录和 SSE 能力。

其中：

- 推荐优先使用 `/v1/dispatch` 与 `/v1/dispatch/upload`
- `dispatch` 的 `auto` 模式会复用共享 analyzer，根据 `intent`、`should_retrieve`、`should_perceive` 自动决定本次请求走同步还是异步
- graph 中的 analyzer 节点与 API dispatch 共用同一套路由判断逻辑，避免 API 层和工作流层规则分叉

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

本地手动运行一次 agent：

```bash
python main.py
```

手动运行 graph 工作流演示脚本：

```bash
python scripts/run_graph_demo.py
```

默认推荐入口：

- 前端默认通过 `dispatch` 入口提交请求
- 在前端可选择 `auto`、`sync`、`async` 三种提交模式
- `auto` 适合日常使用，后端会自动判断是否需要异步任务

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
- `LIVER_REDIS_URL`

当未配置 `LLM_API_KEY` 时，部分节点会进入 fallback 模式，仍可用于测试流程、接口和降级逻辑。

## 主要模块

- `api/`：FastAPI 路由、请求响应 schema、统一 dispatch、上传与 SSE 接口
- `agents/routing.py`：共享的请求路由分析逻辑，供 API dispatch 与 graph analyzer 共用
- `agents/nodes.py`：LangGraph 节点执行逻辑
- `agents/graph.py`：工作流编排结构
- `services/`：`LiverSmartAgent` 封装、任务队列、事件总线
- `rag/`：混合检索、文本清洗、文档预处理
- `perception/`：医学影像感知逻辑
- `core/`：配置、数据库、ORM 模型和初始化逻辑
- `tests/`：测试

## 当前状态

目前已经完成的后端能力：

- FastAPI 同步、异步与 dispatch 咨询接口
- LangGraph 多节点工作流编排
- 检索与感知分支的条件路由
- 共享 analyzer 驱动的同步/异步自动分流
- 节点级 trace、warning、error 输出
- 后台任务队列
- SSE 实时事件流
- 咨询与任务状态持久化
- 上传缓存与文件复用
- 已完成基础测试

## 测试

项目已经包含标准测试目录：

```text
tests/
├─ conftest.py
├─ unit/
└─ integration/
```

当前已覆盖的测试包括：

- `agents.nodes` 节点的 fallback、skip、placeholder、guardrail 和 reviewer disable 分支
- `agents.routing.analyze_intent_routing` 的 fallback 与输出解析
- `agents.graph` 路由分支测试
- `services.job_events.JobEventBus`
- `/health`
- `/v1/dispatch`
- `/v1/dispatch/upload`
- `/v1/consult`
- `/v1/jobs`
- `/v1/consult/upload`
- `/v1/jobs/upload`
- `/v1/jobs/{job_id}`
- `/v1/jobs/{job_id}/events`
- `/v1/consultations`
- `/v1/consultations/{consultation_id}`
- API Key 鉴权测试

运行测试：

```bash
pytest tests
```

测试记录见：[docs/test_logs.md](C:/Users/21204/Desktop/liver-rag/docs/test_logs.md:1)

## 待优化

- 引入多轮审查
- 引入更好的 RAG 算法
- 引入更好的 DICOM 分割模型

## 说明

- `legacy/` 用于暂存旧实现或实验性模块，不属于当前主链路
- `skills/` 当前仅作为预留目录，不承载主流程代码
