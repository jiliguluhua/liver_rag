# API 接口文档

## 接口目录

### 核心主流程接口

- `GET /`
- `GET /health`
- `POST /v1/collect`
- `POST /v1/collect/upload`
- `POST /v1/report`
- `GET /v1/consultations`
- `GET /v1/consultations/{consultation_id}`

### 异步能力接口

- `POST /v1/jobs`
- `POST /v1/jobs/upload`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/events`

### 兼容保留接口

- `POST /v1/consult`
- `POST /v1/consult/upload`
- `POST /v1/dispatch`
- `POST /v1/dispatch/upload`

## 认证方式

- 当配置了 `LIVER_SERVICE_API_KEY` 时，受保护接口需要在请求头中携带 `X-API-Key`
- 当未配置服务鉴权 key 时，可直接访问接口

支持的内容类型：

- `application/json`：标准文本请求接口
- `multipart/form-data`：上传类接口
- `text/event-stream`：SSE 任务事件流接口

## 当前推荐调用方式

系统当前推荐采用“两阶段”交互：

1. 先调用 `POST /v1/collect` 或 `POST /v1/collect/upload` 进入 intake 阶段
2. 服务端记录本轮输入，维护 `session_id` 对应的会话上下文，并返回追问建议
3. 用户可继续多轮补充信息
4. 当需要正式结果时，再调用正式报告入口

说明：

- `collect` 与 `collect/upload` 是同一 intake 阶段的并列入口，分别对应文本/路径输入与文件上传输入两种调用方式
- 当前 `can_generate_report` 不再作为硬门槛，而是用于前端提示与流程展示
- 系统当前推荐主流程已收敛为：`collect` / `collect/upload` -> `report`
- `jobs` / `jobs/upload` 保留为显式异步能力入口，适合展示后台任务、SSE 与事件分发能力
- `consult`、`consult/upload`、`dispatch`、`dispatch/upload` 当前属于兼容保留接口；若后续继续收口接口体系，这几组入口是优先可以弱化或移除的对象

## 元信息接口

### `GET /`

返回静态网页入口页面。

### `GET /health`

状态检查接口。

返回示例：

```json
{
  "status": "ok",
  "agent_ready": true,
  "default_image_path_configured": false
}
```

## Intake 与报告接口

### `POST /v1/collect`

进入多轮 intake 采集阶段。

该接口用于记录用户当前输入、维护会话上下文，并返回：

- intake 阶段的辅助回复
- 后续建议追问
- 当前收集到的上下文内容
- 当前会话编号 `session_id`

请求体：

```json
{
  "query": "患者近两周反复右上腹不适，希望先梳理还需要补充哪些信息",
  "image_path": "C:/data/example/image.nii.gz",
  "session_id": "optional-session-id",
  "reviewer_enabled": true
}
```

字段说明：

- `query`：必填，本轮用户输入
- `image_path`：可选，本地可访问的影像路径
- `session_id`：可选；若不传，服务端自动生成新的会话 ID
- `reviewer_enabled`：当前 intake 阶段不会实际触发 reviewer，但字段保留以兼容统一请求结构

响应字段：

- `session_id`
- `assistant_message`
- `follow_up_questions`
- `can_generate_report`
- `readiness_mode`
- `readiness_reasons`
- `context_turn_count`
- `latest_image_path`
- `collected_context`

说明：

- 服务端优先从 Redis 读取 `session_id` 对应的上下文
- 若 Redis miss，则可基于数据库中的 `intake_messages` 与 `consultations` 恢复最近几轮上下文
- 当前 intake 建议优先由 LLM 生成；若 LLM 不可用，则回退到 fallback 逻辑

返回示例：

```json
{
  "session_id": "2e2c2b58-7d7c-4f6c-9c34-9d73e8b1c001",
  "assistant_message": "我已经记录本轮 intake。你现在可以直接生成报告，也可以先补充更多信息。",
  "follow_up_questions": [
    "请补充主要症状、持续时间，以及是否近期加重。",
    "请说明已有检查结果、既往肝病史或治疗史。"
  ],
  "can_generate_report": true,
  "readiness_mode": "deepseek-chat",
  "readiness_reasons": [
    "建议补充更完整的病史与检查结果，以提高报告质量。"
  ],
  "context_turn_count": 2,
  "latest_image_path": "C:/data/example/image.nii.gz",
  "collected_context": {
    "session_summary": "Q: ... A: ...",
    "recent_turns": [
      {
        "query": "上一轮 intake",
        "report": "上一轮 assistant_message",
        "created_at": "2026-05-16T10:00:00",
        "image_path": "C:/data/example/image.nii.gz",
        "stage": "collect"
      }
    ],
    "latest_image_path": "C:/data/example/image.nii.gz"
  }
}
```

### `POST /v1/collect/upload`

上传 `.nii.gz` 文件并进入 intake 采集阶段。

该接口适用于需要先上传影像、再进行多轮 intake 的场景。

表单字段：

- `query`：必填
- `reviewer_enabled`：可选，默认 `true`
- `session_id`：可选；若不传，服务端自动生成新的会话 ID
- `image_file`：必填，必须为 `.nii.gz` 文件

说明：

- 服务端会先对上传文件计算 SHA256
- 若命中磁盘缓存，则复用已有缓存文件
- `latest_image_path` 会更新为缓存后的最终影像路径
- 响应结构与 `POST /v1/collect` 基本一致

### `POST /v1/report`

基于当前 `session_id` 的上下文生成正式报告。

这是当前推荐的正式报告生成入口。  
系统会在进入正式报告流程前进行轻量路由判断：

- 若不需要影像 perception，则同步执行并直接返回结果
- 若需要影像 perception，则更适合走异步任务路径

请求体：

```json
{
  "query": "请基于当前已收集信息生成正式报告，并给出下一步建议",
  "image_path": null,
  "session_id": "2e2c2b58-7d7c-4f6c-9c34-9d73e8b1c001",
  "reviewer_enabled": true
}
```

说明：

- 服务端优先读取 `session_id` 对应的 session context
- 若当前请求未显式提供 `image_path`，则可尝试复用 session context 中的 `latest_image_path`
- 当前代码中的正式报告核心逻辑统一复用同一套 `run -> graph -> persist` 流程
- 这是当前推荐的正式报告入口，应优先于 `consult` 使用
- 若后续进一步收口接口体系，`report` 应保留为唯一正式报告主入口

同步返回时，响应结构与 `POST /v1/consult` 一致，例如：

```json
{
  "report": "......",
  "preview_image_base64": null,
  "consultation_id": 12,
  "session_id": "2e2c2b58-7d7c-4f6c-9c34-9d73e8b1c001",
  "status": "completed",
  "intent": "clinical",
  "perception_status": "completed",
  "warnings": [],
  "errors": [],
  "evidence": [],
  "trace": []
}
```

## 兼容保留接口

说明：

- 本节接口当前仍可用，但不再作为推荐主入口
- 这些接口主要用于兼容旧调用方式或保留工程能力展示
- 若后续希望继续精简接口体系，建议优先保留 `collect`、`collect/upload`、`report`、`jobs`、`jobs/upload`，并逐步弱化本节接口

### `POST /v1/consult`

显式同步执行一次咨询请求。

请求体：

```json
{
  "query": "请分析当前肝脏病例并给出下一步建议",
  "image_path": "C:/path/to/scan_dir",
  "session_id": "optional-session-id",
  "reviewer_enabled": true
}
```

说明：

- `POST /v1/consult` 为兼容保留的单步咨询接口
- 该接口会直接执行正式报告流程，不经过独立的 intake 阶段
- 当前更推荐优先使用 `POST /v1/collect` + 正式报告入口的两阶段调用方式
- 若后续继续收口接口，`consult` 是优先可以被 `report` 替代的接口之一

返回字段：

- `report`
- `preview_image_base64`
- `consultation_id`
- `session_id`
- `status`
- `intent`
- `perception_status`
- `warnings`
- `errors`
- `evidence`
- `trace`

### `POST /v1/consult/upload`

通过上传 `.nii.gz` 文件显式同步执行一次咨询请求。

表单字段：

- `query`
- `reviewer_enabled`
- `session_id`
- `image_file`

说明：

- `POST /v1/consult/upload` 为兼容保留的单步上传咨询接口
- 当前若需要先采集信息、再显式生成报告，更推荐使用 `POST /v1/collect/upload`
- 返回结果中的 `warnings` 会附带 `cache hit / cache miss` 信息
- 若后续继续收口接口，`consult/upload` 是优先可以被 `collect/upload + report` 替代的接口之一

### `POST /v1/dispatch`

统一分流入口。

后端会根据 `dispatch_mode` 和共享 analyzer 的结果决定当前请求走同步执行还是异步任务模式。

查询参数：

- `dispatch_mode`：可选，取值为 `auto`、`sync`、`async`，默认 `auto`

请求体：

```json
{
  "query": "请结合知识库给出下一步辅助决策建议",
  "image_path": "C:/path/to/scan_dir",
  "session_id": "optional-session-id",
  "reviewer_enabled": true
}
```

响应字段：

- `mode`
- `decision`
- `result`
- `job`

说明：

- `dispatch` 当前仍可用，但更适合作为兼容保留的自动分流入口
- 当请求涉及 perception 时，通常更容易被分流到异步路径
- 后续若系统进一步收口接口，`dispatch` 是优先可以弱化的入口之一
- 若后续主流程完全收敛为 `collect + report + jobs`，`dispatch` 可以考虑整体下线

### `POST /v1/dispatch/upload`

通过上传 `.nii.gz` 文件进入统一分流入口。

表单字段：

- `query`
- `reviewer_enabled`
- `session_id`
- `dispatch_mode`
- `image_file`

说明：

- 行为与 `POST /v1/dispatch` 基本一致
- 服务端会先保存并复用上传缓存，再判断同步或异步
- 若后续主流程完全收敛为 `collect/upload + report/jobs`，`dispatch/upload` 可以考虑整体下线

## 异步任务接口

说明：

- 正式报告生成在工程实现上支持异步任务执行
- 当前更适合将 `jobs` 理解为显式异步能力入口，而不是多轮 intake 的主入口
- 当通过 `dispatch` 被判定为异步时，最终也会落到同一套 job 任务体系
- 这组接口建议保留，用于展示异步任务、任务持久化、SSE 与 Redis 事件分发能力

### `POST /v1/jobs`

显式提交一个异步咨询任务。

请求体：

```json
{
  "query": "请分析该病例",
  "image_path": "C:/path/to/scan_dir",
  "session_id": "optional-session-id",
  "reviewer_enabled": true
}
```

返回示例：

```json
{
  "job_id": "uuid",
  "session_id": "uuid",
  "status": "queued"
}
```

说明：

- 该接口适合调用方已经明确希望进入后台任务队列的场景
- 后续如果系统继续收口，`jobs` 仍然值得保留，用于展示异步任务、SSE 和事件分发能力

### `POST /v1/jobs/upload`

通过上传 `.nii.gz` 文件显式提交一个异步咨询任务。

表单字段：

- `query`
- `reviewer_enabled`
- `session_id`
- `image_file`

返回字段：

- `job_id`
- `session_id`
- `status`

### `GET /v1/jobs/{job_id}`

获取任务状态快照。

返回字段：

- `job_id`
- `session_id`
- `status`：`queued`、`running`、`completed` 或 `failed`
- `query`
- `image_path`
- `reviewer_enabled`
- `consultation_id`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`
- `result`：任务完成时返回完整结果

### `GET /v1/jobs/{job_id}/events`

订阅任务的 SSE 事件流。

返回类型：

```text
text/event-stream
```

可能出现的事件：

- `job_update`
- `node_update`
- `job_completed`
- `job_failed`
- `error`

说明：

- 当任务仍在运行时，会持续发送 keep-alive 注释
- 当任务状态发生变化时，会推送新的任务 snapshot
- 当任务不存在时，会返回 `error` 事件

## 历史记录接口

### `GET /v1/consultations`

查询咨询历史列表。

查询参数：

- `session_id`：可选，按会话过滤
- `limit`：可选，默认 `50`，范围 `1-200`

返回项字段：

- `id`
- `session_id`
- `query`
- `report_preview`
- `image_path`
- `has_preview`
- `created_at`

### `GET /v1/consultations/{consultation_id}`

获取单条咨询记录详情。

返回示例：

```json
{
  "id": 1,
  "session_id": "uuid",
  "query": "clinical question",
  "report": "generated answer",
  "image_path": "C:/path/to/image",
  "has_preview": false,
  "created_at": "2026-05-13T18:30:00"
}
```

## 会话上下文说明

系统通过 `session_id` 串联多轮 intake 与正式报告生成：

- `collect` 阶段会写入 `intake_messages`
- `report` 阶段会写入 `consultations`
- Redis 用于缓存最近几轮 session context
- 当 Redis miss 时，系统可基于数据库中的 `intake_messages` 与 `consultations` 恢复上下文

因此，若希望多轮交互保持连续，客户端应持续复用同一个 `session_id`。

## 常见错误

### `401 Unauthorized`

当启用了服务鉴权且 `X-API-Key` 缺失或错误时返回。

### `404 Not Found`

以下情况会返回：

- 任务不存在
- 咨询记录不存在

### `400 Bad Request`

当上传接口接收到非 `.nii.gz` 文件时返回。
