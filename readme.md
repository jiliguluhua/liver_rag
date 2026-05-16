# Liver RAG

一个面向肝病场景的医疗决策支持系统，支持多轮 intake 信息采集、医学影像辅助分析与结构化报告生成。

后端基于 LangGraph、RAG 与医学影像感知构建，并结合异步任务、SSE 实时事件、Redis 与文件缓存实现可追溯的执行与状态管理。

当前系统支持：

- 多轮 intake 信息采集与显式“生成报告”两阶段交互
- 同步咨询接口
- 异步任务提交与状态查询
- `.nii.gz` 影像上传与缓存复用
- 基于 `session_id` 的会话上下文管理
- Redis 会话上下文缓存与 intake 历史恢复
- 检索与感知并行分支
- 报告生成与单轮医学审查（待改进）
- 咨询记录与 intake 记录持久化
- SSE 实时事件流

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

系统主流程由 [agents/graph.py](C:/Users/21204/Desktop/liver-rag/agents/graph.py:1) 编排，采用“两阶段”流程：

1. `collect / intake` 阶段：先记录用户本轮输入，结合会话上下文提炼已知信息，并生成后续追问建议
2. 用户可在任意时刻继续补充信息，也可显式点击“生成报告”
3. `report` 阶段：正式进入 LangGraph 工作流，执行意图分析、检索、感知、报告生成与审查
4. 异步任务模式下，后台 worker 处理任务，事件总线通过内存版或 Redis pub/sub 分发 job / node 事件
5. 会话上下文优先从 Redis 读取，Redis miss 时可由数据库中的 intake 记录与咨询记录恢复

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
- `LIVER_REDIS_SESSION_CONTEXT_TTL_SECONDS`
- `LIVER_SESSION_CONTEXT_MAX_TURNS`

当未配置 `LLM_API_KEY` 时，部分节点会进入 fallback 模式，仍可用于测试流程、接口和降级逻辑。

另外：

- `LIVER_REDIS_URL` 用于启用 Redis 能力，包括任务事件 pub/sub、job 状态缓存、检索缓存与会话上下文缓存
- `LIVER_SESSION_CONTEXT_MAX_TURNS` 用于控制单个 session 保留的最近上下文轮数
- `LIVER_REDIS_SESSION_CONTEXT_TTL_SECONDS` 用于控制 Redis 中 session context 的过期时间

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

目前已经完成的后端能力包括：

- FastAPI 同步与异步咨询接口
- 多轮 intake 与显式报告生成两阶段交互
- 基于 `session_id` 的会话串联
- LangGraph 多节点工作流编排
- 检索与感知分支的条件路由
- 节点级 trace、warning、error 输出
- 后台任务队列
- SSE 实时事件流
- Redis pub/sub 任务事件分发
- Redis 会话上下文缓存
- intake 记录、咨询记录与任务状态持久化
- 上传缓存与文件复用
- 基础自动化测试

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
