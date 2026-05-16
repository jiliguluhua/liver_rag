# 存储和状态说明

这份文档主要是给自己和后续协作者看的，目的是把项目里“到底存了什么、为什么要这么存、哪些是持久化、哪些只是缓存或事件”讲清楚。

不追求特别正式，重点是讲清楚 `consultations`、`consultation_jobs`、Redis、SSE 和上下文缓存。

## 先说结论

可以先把现在的存储分成 4 类：

- 数据库里的业务记录
- Redis 里的缓存
- 事件总线里的实时消息
- 磁盘上的上传文件和缓存文件

- `consultations` 主要存“正式结果”（虽然consult接口打算下一步废掉，但是consultations还是要一直用的）
- `consultation_jobs` 主要存“异步任务过程和结果快照”
- Redis 主要做“加速”和“短期状态”
- `job_event_bus` / SSE 主要做“实时通知”

## 1. 数据库里（目前用的是SQLite）存了什么

数据库模型定义在 [core/models.py](C:/Users/21204/Desktop/liver-rag/core/models.py:12)。

### `intake_messages`

这是多轮问询阶段的记录表。

里面主要有：

- `session_id`
- `query`
- `assistant_message`
- `image_path`
- `created_at`

这个表记录的是 `collect / intake` 阶段发生了什么。  
可以把它理解成“用户和系统在正式出报告前，已经聊过什么、补充过什么信息”。

它不是最终报告表，也不是异步任务表。

### `consultations`

这是正式咨询结果表。

里面主要有：

- `id`
- `session_id`
- `query`
- `report`
- `image_path`
- `has_preview`
- `created_at`

这个表存的是“最终业务结果（即报告）”。  
如果用户已经拿到正式报告了，那么最核心的结果会落在这里。

### `consultation_jobs`

这是异步任务记录表。

里面主要有：

- `id(job_id)`
- `session_id`
- `query`
- `image_path`
- `status`
- `error_message`
- `report`
- `preview_image_base64`
- `intent`
- `perception_status`
- `warnings_json`
- `errors_json`
- `evidence_json`
- `trace_json`
- `consultation_id`
- `created_at`
- `started_at`
- `completed_at`

这个表不是重复存一份 `consultations`。  
它主要解决的是异步任务的生命周期问题，比如：

- 任务有没有提交成功
- 当前是 `queued` 还是 `running`
- 最后是 `completed` 还是 `failed`
- 如果失败，失败原因是什么
- 当时走了哪些节点
- 生成结果时附带了哪些 `warnings / errors / evidence / trace`

## 2. 为什么已经有 `consultations`，还要有 `consultation_jobs`

如果系统完全不关心任务过程，只关心最后有没有一份报告，那只保留 `consultations` 也不是不行。

但当前项目有异步链路，所以 `consultation_jobs` 还是有意义的。

因为异步任务和同步请求不一样：

- 请求先返回一个 `job_id`
- 后台 worker 过一会儿才真正处理
- 中途可能成功，也可能失败
- 前端会轮询状态或者订阅 SSE

这时候如果没有 `consultation_jobs`，会不太方便处理这些事情：

- 根据 `job_id` 查任务
- 记录任务的运行状态变化
- 保存失败原因
- 保存任务执行轨迹
- 区分“任务失败了”和“任务成功并产生了 consultation”

两个表解决的问题不一样：

- `consultations` 解决结果存档
- `consultation_jobs` 解决异步任务追踪

如果以后项目要简化，也可以考虑把 `consultation_jobs` 降级成短期状态表，甚至只保留几天；但在当前版本里，把它持久化下来是更稳妥的做法。

## 3. Redis 里存了什么

Redis 的代码在 [services/redis_store.py](C:/Users/21204/Desktop/liver-rag/services/redis_store.py:21)。

Redis 在这里不是主数据源，主要是缓存层和加速层。

### `job_status`

键名格式：

```text
liver:job_status:{job_id}
```

这份数据是任务状态快照。

它通常来自数据库里的 `consultation_jobs`，只是为了更快读取。  
比如查 `/v1/jobs/{job_id}` 时，会优先读 Redis，没命中再查数据库。

所以：

- Redis 里的 `job_status` 不是唯一来源
- 真正长期记录还是数据库里的 `consultation_jobs`

### `session_context`

键名格式：

```text
liver:session_context:{session_id}
```

这里存的是多轮会话上下文，主要包括：

- `session_summary`
- `recent_turns`
- `latest_image_path`

这个上下文不是全量聊天历史，而是最近几轮的摘要和关键信息。  
默认只保留最近 `SESSION_CONTEXT_MAX_TURNS` 轮，当前配置默认是 `3`。

也就是说，Redis 里的会话上下文更像：

- 方便下次快速接着聊
- 减少每次都回数据库拼接上下文
- 给 `report` 阶段复用最近图像路径和最近对话内容

### `search_results`

键名格式：

```text
liver:search:{digest}
```

这里缓存的是 RAG 检索结果。

相同 query 和相同 `top_k` 的情况下，可以直接复用上次检索结果，减少：

- FAISS 向量检索
- BM25 检索
- 结果融合

## 4. Redis 上下文和数据库上下文是什么关系

本项目中 Redis 不是会话历史的唯一来源。

实际逻辑是：

1. 先按 `session_id` 读 Redis 里的 `session_context`
2. 如果命中，就直接用
3. 如果没命中，就从数据库恢复
4. 恢复来源是 `intake_messages + consultations`
5. 恢复完再写回 Redis

- Redis 存的是“最近几轮上下文缓存”
- 数据库存的是“可恢复的历史记录”

数据库负责兜底，Redis 负责提速

## 5. 最终结果到底存在哪里

同步和异步路径略有不同。

### 同步情况下

正式报告生成后，结果会写入 `consultations`。  
接口也会直接把结果返回给调用方。

所以同步路径下，`consultations` 是最关键的结果落点。

### 异步情况下

任务先进入 `consultation_jobs`：

- 先是 `queued`
- 然后 `running`
- 最后 `completed` 或 `failed`

任务完成后，会把结果写进 `consultation_jobs`，包括：

- `report`
- `preview_image_base64`
- `warnings`
- `errors`
- `evidence`
- `trace`

同时，正式报告本身也会写入 `consultations`，并把 `consultation_id` 回填到 job 记录里。

即：

- `consultation_jobs`：任务视角的结果
- `consultations`：业务视角的正式结果

## 6. `job_event_bus` 和 Redis

`job_event_bus` 的职责是发事件，不是存业务数据。

它会有两种实现：

- 本地内存版
- Redis Pub/Sub 版

如果启用了 Redis，就会用 Redis Pub/Sub 转发这些事件：

- `job_update`
- `node_update`
- `job_completed`
- `job_failed`

这些事件主要给 SSE 接口和前端实时展示用。

重点是：

- 事件总线负责“通知”
- Redis KV 负责“缓存”
- 数据库负责“持久化”

## 7. 上传文件和磁盘缓存

除了数据库和 Redis，这个项目还有文件层的数据。

上传 `.nii.gz` 时，大概会这样处理：

1. 先写到 session 临时目录
2. 计算文件 SHA256
3. 看磁盘缓存里有没有相同内容
4. 有就复用
5. 没有就移动到缓存目录
6. 请求结束后清理临时目录

所以图像本体不是存在 Redis 里，也不是存在数据库里，而是落在磁盘目录里。（nii太大了）

这里也能看出当前系统是分层存储的：

- 大文件放磁盘
- 业务记录放数据库
- 热状态放 Redis

## 8. 一次典型请求里，数据怎么流

### `collect / intake`

主要会发生这些事：

- 写入 `intake_messages`
- 更新 Redis 里的 `session_context`
- 必要时复用历史 `latest_image_path`（session表的一个字段）

### `report`

主要会发生这些事：

- 读取 `session_context`
- 必要时从数据库恢复最近上下文
- 生成正式报告
- 写入 `consultations`
- 刷新 Redis 里的上下文缓存

### `jobs`

主要会发生这些事：

- 插入 `consultation_jobs`
- 更新 Redis `job_status`（其实jobstatus也是从consultations_jobs里转录出来的）
- 发布任务事件
- 后台 worker 执行
- 完成后写回 `consultation_jobs`
- 成功时也写入 `consultations`

## 9. 总结

- `intake_messages`：多轮对话记忆
- `consultations`：正式报告列表
- `consultation_jobs`：异步任务是怎么跑的、结果怎样
- `session_context`：Redis 里的最近几轮上下文
- `job_status`：Redis 里的任务状态缓存
- `job_event_bus / PubSub / SSE`：实时通知......
