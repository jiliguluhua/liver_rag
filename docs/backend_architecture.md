## 1. 系统总览

```mermaid
flowchart LR
    User[用户 / 调用方]
    Frontend[前端界面<br/>index.html / Streamlit]
    API[FastAPI 接口层]
    Session[Session Context<br/>Redis / SQLite]
    TaskSystem[任务系统<br/>队列 / Worker / SSE / Redis PubSub]
    Agent[Agent 工作流]
    Reasoning[检索与感知<br/>FAISS / BM25 / MONAI]
    LLM[LLM 服务]
    DB[(SQLite 数据库)]

    User --> Frontend
    User --> API
    Frontend --> API
    API --> Session
    API --> DB
    API --> TaskSystem
    API --> Agent
    TaskSystem --> Agent
    TaskSystem --> Frontend
    Session --> API
    Agent --> Reasoning
    Agent --> LLM
    Agent --> DB
```

## 2. 请求模式

```mermaid
flowchart TD
    A[进入系统的请求] --> B{接口类型}

    B -->|POST /v1/collect| C[文本 intake 采集]
    B -->|POST /v1/collect/upload| D[上传影像并进入 intake]
    B -->|POST /v1/report| E[显式生成正式报告]
    B -->|POST /v1/consult| F[兼容保留的单步咨询接口]
    B -->|POST /v1/jobs| G[异步任务提交]
    B -->|POST /v1/jobs/upload| H[异步上传任务提交]
    B -->|GET /v1/jobs/:job_id| I[查询任务状态]
    B -->|GET /v1/jobs/:job_id/events| J[订阅任务事件流]
    B -->|GET /v1/consultations| K[查询历史咨询记录]

    C --> L[写入 intake 上下文]
    D --> M[保存上传文件并复用缓存]
    M --> L

    E --> N[读取 session 上下文]
    N --> O[执行 LangGraph 正式报告流程]

    F --> O
    G --> P[将任务持久化为 queued]
    H --> Q[保存上传内容并持久化任务]
    P --> R[放入队列]
    Q --> R
    R --> S[后台 Worker 执行任务]

    I --> T[读取任务状态与结果快照]
    J --> U[实时接收 job 与节点事件]
    K --> V[读取 consultation 历史]
```

## 3. Intake 与报告链路

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant Redis as Redis Session Context
    participant DB as SQLite
    participant Agent as LiverSmartAgent
    participant Graph as LangGraph

    Client->>API: POST /v1/collect
    API->>Redis: 读取 session context
    alt Redis miss
        API->>DB: 从 intake_messages 与 consultations 恢复上下文
        DB-->>API: 返回历史轮次
        API->>Redis: 回填 session context
    end
    API->>DB: 写入 intake_messages
    API->>Redis: 更新 session context
    API-->>Client: 返回 assistant_message / follow_up_questions / collected_context

    Client->>API: POST /v1/report
    API->>Redis: 读取 session context
    API->>Agent: run(image_path, query, session_id, reviewer_enabled, user_context)
    Agent->>Graph: invoke(initial_state)
    Graph-->>Agent: 返回 report + preview + trace
    Agent-->>API: 返回正式报告结果
    API->>DB: 写入 consultations
    API->>Redis: 刷新 session context
    API-->>Client: 返回 ConsultResponse
```

当前实现要点：

- `collect` 阶段负责记录用户输入、维护会话上下文，并给出下一步追问建议
- `report` 阶段才真正进入 LangGraph 正式报告流程
- `can_generate_report` 当前不再作为硬门槛，而是允许用户随时显式生成报告
- 会话上下文优先读 Redis，Redis miss 时可由数据库恢复

## 4. 异步任务链路

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

    Client->>API: POST /v1/jobs 或 /v1/jobs/upload
    API->>DB: 插入 consultation_jobs(status=queued)
    API->>Queue: submit(job_id)
    API-->>Client: 202 Accepted + job_id

    Client->>SSE: GET /v1/jobs/:job_id/events
    SSE-->>Client: 建立事件流连接

    Worker->>Queue: 获取下一个任务
    Queue-->>Worker: 返回 job_id
    Worker->>DB: 更新 job 为 running
    Worker->>Bus: 发布 job_update
    Bus->>Redis: 发布任务事件（启用 Redis 时）

    Worker->>DB: 读取 session 上下文（必要时）
    Worker->>Agent: 执行正式报告流程
    Agent-->>Worker: 返回 report, preview, trace

    Worker->>DB: 写入 consultation 记录
    Worker->>DB: 更新 job 为 completed
    Worker->>Bus: 发布 job_completed
    Bus->>Redis: 发布完成事件（启用 Redis 时）

    Redis-->>SSE: 跨进程分发 job / node 事件
    SSE-->>Client: 实时更新任务状态
```

## 5. 上传与缓存链路

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
    H --> I[写入 session context 或用于正式报告生成]
    I --> J[删除临时会话目录]
```

说明：

- 影像文件本体仍然落磁盘，不直接存入 Redis
- Redis 主要保存 session context、任务状态快照、检索缓存与事件分发
- 上传缓存采用基于 SHA256 的磁盘去重复用

## 6. Agent 工作流

说明：当前 LangGraph 工作流主要用于“正式报告生成”阶段。  
`collect / intake` 阶段不直接进入完整 graph，而是先基于会话上下文整理已知信息、生成追问建议，并由用户显式触发报告生成。

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

这一阶段的关键点是：

- 先由 `analyzer` 判断是否需要检索、是否需要感知
- 只有当两者都需要时，`retriever` 和 `perceptor` 才并行执行
- 二者完成后再汇总进入 `reporter`

## 7. SSE 事件流模型

当前系统中的 Redis 主要承担两类职责：

- 任务事件分发：支持 JobEventBus 在部署场景下通过 Redis pub/sub 跨进程推送事件
- 会话上下文缓存：缓存基于 `session_id` 的 intake / report 最近轮次，减少重复数据库读取

其中，任务事件通过 SSE 推送到前端；会话上下文主要服务于 intake 与正式报告生成流程。

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
    I --> M[前端状态展示]
```

当前前端可实时看到的内容包括：

- job 总体状态
- 当前正在执行的节点
- 各节点状态变化
- trace 流式更新

## 8. 持久化模型（仅展示核心字段）

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

    INTAKE_MESSAGES {
        int id PK
        string session_id
        string query
        string assistant_message
        string image_path
        datetime created_at
    }

    CONSULTATION_JOBS ||--o| CONSULTATIONS : 产出
    INTAKE_MESSAGES }o--|| CONSULTATIONS : 同属会话上下文
```

## 9. 会话上下文恢复机制

当前会话上下文采用“Redis 缓存 + 数据库恢复”的方式：

- `collect` 阶段会将每轮 intake 写入 `intake_messages`，并同步更新 Redis session context
- `report` 阶段会读取同一 `session_id` 下的上下文，并将正式报告结果写入 `consultations`
- 当 Redis miss 或服务重启后，系统可基于 `intake_messages` 与 `consultations` 重建最近几轮上下文
- Redis 不再是 intake 历史的唯一来源，而是会话状态的加速层
