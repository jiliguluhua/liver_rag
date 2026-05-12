# Liver RAG 后端架构

这份文档用于说明项目当前的后端架构设计，采用 `Markdown + Mermaid` 方式绘制，可直接在支持 Mermaid 的 Markdown 预览器中显示。

## 1. 系统总览

```mermaid
flowchart LR
    User[用户]
    Streamlit[Streamlit 演示前端]
    StaticUI[web/index.html 调试页]
    API[FastAPI 接口层]
    Auth[API Key 鉴权]
    Input[影像输入处理<br/>路径或 .nii.gz 上传]
    JobQueue[内存任务队列]
    Worker[后台 Worker]
    Agent[LiverSmartAgent]
    Graph[LangGraph 工作流]
    Retrieval[混合检索<br/>FAISS + BM25]
    Perception[医学感知模块<br/>MONAI / SwinUNETR]
    LLM[LLM 服务]
    DB[(SQLite 数据库)]

    User --> Streamlit
    User --> StaticUI
    User --> API
    Streamlit --> API
    StaticUI --> API
    API --> Auth
    API --> Input
    API --> DB
    API --> Agent
    API --> JobQueue
    Input --> Agent
    JobQueue --> Worker
    Worker --> Agent
    Agent --> Graph
    Graph --> Retrieval
    Graph --> Perception
    Graph --> LLM
    Worker --> DB
```

## 2. 请求模式

```mermaid
flowchart TD
    A[进入系统的请求] --> B{接口类型}
    B -->|POST /v1/consult| C[同步文本/路径咨询]
    B -->|POST /v1/consult/upload| D[同步上传咨询]
    B -->|POST /v1/jobs| E[异步任务提交]
    B -->|POST /v1/jobs/upload| F[异步上传任务提交]
    B -->|GET /v1/jobs/:job_id| G[查询任务状态]
    B -->|GET /v1/consultations| H[查询历史咨询记录]

    C --> I[直接执行 Agent]
    D --> J[保存上传文件并复用缓存]
    J --> I

    E --> K[将任务持久化为 queued]
    F --> L[保存上传内容并持久化任务]
    L --> M[将 job_id 放入队列]
    K --> M
    M --> N[后台 Worker 执行任务]

    G --> O[读取任务状态与结果快照]
    H --> P[读取历史 consultation 记录]
```

## 3. 同步咨询链路

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant Agent as LiverSmartAgent
    participant Graph as LangGraph
    participant DB as SQLite

    Client->>API: POST /v1/consult
    API->>API: 校验请求，解析 session_id / image_path
    API->>Agent: run(image_path, query, session_id, reviewer_enabled)
    Agent->>Graph: invoke(initial_state)
    Graph-->>Agent: 返回 final_state + preview_image + report
    Agent-->>API: 返回 report, preview_img, final_state
    API->>DB: 写入 consultation 记录
    DB-->>API: 返回 consultation_id
    API-->>Client: 返回 ConsultResponse
```

## 4. 异步任务链路

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant DB as SQLite
    participant Queue as InMemoryJobQueue
    participant Worker as 后台 Worker
    participant Agent as LiverSmartAgent

    Client->>API: POST /v1/jobs
    API->>DB: 插入 consultation_jobs(status=queued)
    API->>Queue: submit(job_id)
    API-->>Client: 202 Accepted + job_id

    Worker->>Queue: 获取下一个任务
    Queue-->>Worker: 返回 job_id
    Worker->>DB: 将任务状态改为 running
    Worker->>Agent: 执行咨询工作流
    Agent-->>Worker: 返回 report, preview, trace, evidence
    Worker->>DB: 写入 consultation 记录
    Worker->>DB: 更新 job 为 completed，并保存结果快照

    Client->>API: GET /v1/jobs/:job_id
    API->>DB: 查询 job 记录
    DB-->>API: 返回任务状态与结果
    API-->>Client: 返回 JobStatusResponse
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
    H --> I[执行同步咨询或创建异步任务]
    I --> J[删除临时会话目录]
```

## 6. Agent 工作流

```mermaid
flowchart TD
    Start([开始]) --> Analyzer[意图分析节点]

    Analyzer -->|unrelated| Reporter[报告生成节点]
    Analyzer -->|should_retrieve| Retriever[检索节点]
    Analyzer -->|perception only| Perceptor[感知节点]
    Analyzer -->|direct answer| Reporter

    Retriever -->|should_perceive| Perceptor
    Retriever -->|text only| Reporter

    Perceptor --> Reporter
    Reporter --> Reviewer{是否开启 Reviewer}
    Reviewer -->|是| ReviewNode[医学审核节点]
    Reviewer -->|否| End([结束])
    ReviewNode --> End
```

## 7. 持久化模型（仅展示核心字段）

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
