## 1. 系统总览

```mermaid
flowchart LR
    User[用户 / 调用方]
    Frontend[前端界面<br/>Streamlit / index.html]
    API[FastAPI 接口层]
    TaskSystem[任务系统<br/>队列 / Worker / SSE / Redis PubSub]
    Agent[Agent 工作流]
    Reasoning[检索与感知<br/>FAISS / BM25 / MONAI]
    LLM[LLM 服务]
    DB[(SQLite 数据库)]

    User --> Frontend
    User --> API
    Frontend --> API
    API --> DB
    API --> TaskSystem
    API --> Agent
    TaskSystem --> Agent
    TaskSystem --> Frontend
    Agent --> Reasoning
    Agent --> LLM
    Reasoning --> DB
    Agent --> DB
```

## 2. 请求模式

```mermaid
flowchart TD
    A[进入系统的请求] --> B{接口类型}
    B -->|POST /v1/dispatch| C[统一文本/路径咨询入口]
    B -->|POST /v1/dispatch/upload| D[统一上传咨询入口]
    B -->|POST /v1/consult| E[显式同步咨询]
    B -->|POST /v1/consult/upload| F[显式同步上传咨询]
    B -->|POST /v1/jobs| G[显式异步任务提交]
    B -->|POST /v1/jobs/upload| H[显式异步上传任务提交]
    B -->|GET /v1/jobs/:job_id| I[查询任务状态]
    B -->|GET /v1/jobs/:job_id/events| J[订阅任务事件流]
    B -->|GET /v1/consultations| K[查询历史咨询记录]

    C --> L[共享 analyzer 判断 sync / async]
    D --> M[保存上传文件并复用缓存]
    M --> L
    L -->|sync| N[直接执行 Agent]
    L -->|async| O[创建 queued 任务并放入队列]

    E --> N
    F --> P[保存上传文件并复用缓存]
    P --> N

    G --> Q[将任务持久化为 queued]
    H --> R[保存上传内容并持久化任务]
    Q --> S[放入队列]
    R --> S
    O --> S
    S --> T[后台 Worker 执行任务]

    I --> U[读取任务状态与结果快照]
    J --> V[实时接收 job 与节点事件]
    K --> W[读取 consultation 历史]

```

## 3. Dispatch 分流链路

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant Routing as Shared Analyzer

    Client->>API: POST /v1/dispatch
    API->>API: 校验请求，解析 session_id / image_path
    API->>Routing: analyze_intent_routing(query, image_path)
    Routing-->>API: 返回 intent + should_retrieve + should_perceive
    API->>API: 根据共享 analyzer 结果决定 sync / async
    API-->>Client: 返回 DispatchResponse(mode=sync|async, ...)
```

## 4. 同步咨询链路

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant Agent as LiverSmartAgent
    participant Graph as LangGraph
    participant DB as SQLite

    Client->>API: POST /v1/consult 或 dispatch(mode=sync)
    API->>API: 校验请求，解析 session_id / image_path
    API->>Agent: run(image_path, query, session_id, reviewer_enabled)
    Agent->>Graph: invoke(initial_state)
    Graph-->>Agent: 返回 report + preview + trace
    Agent-->>API: 返回咨询结果
    API->>DB: 写入 consultation 记录
    DB-->>API: 返回 consultation_id
    API-->>Client: 返回 ConsultResponse
```

## 5. 异步任务链路

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant DB as SQLite
    participant Queue as InMemoryJobQueue
    participant Worker as 后台 Worker
    participant Bus as JobEventBus
    participant Redis as Redis Pub/Sub
    participant SSE as SSE 接口
    participant Agent as LiverSmartAgent

    Client->>API: POST /v1/dispatch 或 POST /v1/jobs
    API->>API: 若走 dispatch，则先调用共享 analyzer 判断是否需要异步
    API->>DB: 插入 consultation_jobs(status=queued)
    API->>Queue: submit(job_id)
    API-->>Client: 返回 job_id 或 DispatchResponse(mode=async, job=...)


    Client->>SSE: GET /v1/jobs/:job_id/events
    SSE-->>Client: 建立事件流连接

    Worker->>Queue: 获取下一个任务
    Queue-->>Worker: 返回 job_id
    Worker->>DB: 更新 job 为 running
    Worker->>Bus: 发布 job_update
    Bus->>Redis: 发布任务事件（启用 Redis 时）
    Worker->>Agent: 执行咨询工作流
    Agent-->>Worker: 返回 report, preview, trace
    Worker->>DB: 写入 consultation 记录
    Worker->>DB: 更新 job 为 completed
    Worker->>Bus: 发布 job_completed
    Bus->>Redis: 发布完成事件（启用 Redis 时）
    Redis-->>SSE: 跨进程分发 job / node 事件
    SSE-->>Client: 实时更新任务状态
```

## 6. 上传与缓存链路

```mermaid
flowchart TD
    A[上传 .nii.gz 请求] --> B[创建会话级临时目录]
    B --> C[流式写入 incoming.nii.gz]
    C --> D[计算文件 SHA256]
    D --> E{是否命中缓存}
    E -->|是| F[复用 upload_cache 下的 image.nii.gz]
    E -->|否| G[将文件移动到 upload_cache/hash/image.nii.gz]
    F --> H[得到最终 image_path]
    G --> H
    H --> I[进入 dispatch / consult / jobs 入口]
    I --> J[由共享 analyzer 决定同步或异步，或由显式接口直接执行]
    J --> K[删除临时会话目录]
```

## 7. Agent 工作流

```mermaid
flowchart TD
    Start([开始]) --> Analyzer[意图分析节点]

    Analyzer -->|无关问题| Reporter[报告生成节点]
    Analyzer -->|仅检索| Retriever[检索节点]
    Analyzer -->|仅感知| Perceptor[感知节点]
    Analyzer -->|两者都需要| Retriever
    Analyzer -->|两者都需要| Perceptor
    Analyzer -->|直接回答| Reporter

    Retriever --> Reporter
    Perceptor --> Reporter
    Reporter --> Reviewer{是否开启 Reviewer}
    Reviewer -->|是| ReviewNode[医学审核节点]
    Reviewer -->|否| End([结束])
    ReviewNode --> End
```

这一步的关键点是：

- 先由 analyzer 判断是否需要检索、是否需要感知
- API 的 dispatch auto 模式与 graph 中的 analyzer 共享同一套路由分析逻辑
- 只有当两者都需要时，retriever 和 perceptor 才并行执行
- 二者完成后再汇总进入 reporter

## 8. SSE 事件流模型

```mermaid
flowchart TD
    A[后台任务执行] --> B[发布 job_update]
    A --> C[发布 node_update]
    A --> D[发布 job_completed / job_failed]

    B --> E[JobEventBus]
    C --> E
    D --> E

    E --> F{事件总线实现}
    F -->|本地开发| G[InMemoryJobEventBus]
    F -->|部署启用 Redis| H[RedisJobEventBus / Redis PubSub]

    G --> I[SSE 任务事件接口]
    H --> I

    I --> J[前端 Job 面板]
    I --> K[前端 Stage Status]
    I --> L[前端 Trace 实时更新]
    I --> M[Streamlit 状态展示]

```

当前前端能实时看到的内容包括：

- job 总体状态
- 当前正在执行的节点
- 各节点状态面板
- trace 流式更新

当前任务事件流采用可切换的事件总线实现：

- 本地开发默认使用内存版 JobEventBus
- 配置 `LIVER_REDIS_URL` 后可切换为基于 Redis pub/sub 的事件分发
- SSE 接口统一消费事件并推送到前端，因此前端侧无需区分底层实现
- 该设计主要用于跨进程的 job / node 事件推送，不影响现有文件缓存与任务队列实现

## 9. 持久化模型（仅展示核心字段）

```mermaid
erDiagram
    CONSULTATIONS {
        int id PK
        string session_id
        string query
        string report
        datetime created_at
    }

    CONSULTATION_JOBS {
        string id PK
        string session_id
        string query
        string status
        int consultation_id
        datetime created_at
        datetime completed_at
    }

    CONSULTATION_JOBS ||--o| CONSULTATIONS : 产出
```
