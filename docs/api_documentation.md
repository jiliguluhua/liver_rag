# API 接口文档

鉴权方式：

- 当配置了 `LIVER_SERVICE_API_KEY` 时，受保护接口需要在请求头中携带 `X-API-Key`
- 当未配置服务鉴权 key 时，可直接访问接口

支持的内容类型：

- `application/json`：标准咨询与任务提交接口
- `multipart/form-data`：上传类接口
- `text/event-stream`：SSE 任务事件流接口

推荐调用方式：

- 推荐优先使用统一 dispatch 入口：
  - `POST /v1/dispatch`
  - `POST /v1/dispatch/upload`
- `dispatch` 支持 `auto`、`sync`、`async` 三种模式：
  - `auto`：由后端共享 analyzer 自动决定同步或异步执行
  - `sync`：强制同步执行
  - `async`：强制异步执行
- `POST /v1/consult`、`POST /v1/jobs` 及其 upload 版本仍然保留，用于显式控制执行方式。

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

## 咨询接口

### `POST /v1/dispatch`

统一咨询入口。后端会根据 `dispatch_mode` 和共享 analyzer 的结果决定当前请求走同步执行还是异步任务模式。

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

字段说明：

- `query`：必填，临床问题、教育类问题或辅助决策问题
- `image_path`：可选，本地影像路径或 DICOM/NIfTI 路径
- `session_id`：可选，会话标识
- `reviewer_enabled`：是否启用 reviewer 节点

返回字段：

- `mode`：本次最终采用的执行模式，`sync` 或 `async`
- `decision`：共享 analyzer 的判断结果
  - `mode`
  - `reason`
  - `intent_hint`
  - `should_retrieve`
  - `should_perceive`
- `result`：当 `mode=sync` 时返回完整咨询结果
- `job`：当 `mode=async` 时返回异步任务信息

同步返回示例：

```json
{
  "mode": "sync",
  "decision": {
    "mode": "sync",
    "reason": "Auto dispatch selected sync because shared analyzer did not require image perception.",
    "should_retrieve": true,
    "should_perceive": false,
    "intent_hint": "education"
  },
  "result": {
    "report": "generated answer",
    "preview_image_base64": null,
    "consultation_id": 1,
    "session_id": "uuid",
    "status": "completed",
    "intent": "education",
    "perception_status": "skipped",
    "warnings": [],
    "errors": [],
    "evidence": [],
    "trace": []
  },
  "job": null
}
```

异步返回示例：

```json
{
  "mode": "async",
  "decision": {
    "mode": "async",
    "reason": "Auto dispatch selected async because shared analyzer requested image perception.",
    "should_retrieve": true,
    "should_perceive": true,
    "intent_hint": "clinical"
  },
  "result": null,
  "job": {
    "job_id": "uuid",
    "session_id": "uuid",
    "status": "queued"
  }
}
```

### `POST /v1/dispatch/upload`

通过上传 `.nii.gz` 文件进入统一咨询入口。后端会先保存并复用上传缓存，再根据 `dispatch_mode` 和共享 analyzer 的结果决定走同步还是异步。

表单字段：

- `query`：必填
- `reviewer_enabled`：可选，默认 `true`
- `session_id`：可选
- `dispatch_mode`：可选，取值为 `auto`、`sync`、`async`，默认 `auto`
- `image_file`：必填，`.nii.gz` 文件

接口行为：

- 非 `.nii.gz` 文件会返回 `400`
- 上传文件会先写入会话级临时目录
- 当 SHA256 命中缓存时会复用已缓存文件
- 返回结果中的 `decision` 表示本次 dispatch 判断
- 若为同步执行，返回 `result`
- 若为异步执行，返回 `job`

### `POST /v1/consult`

显式同步执行一次咨询请求。适用于调用方已经明确希望直接返回结果的场景。

请求体：

```json
{
  "query": "请分析当前肝脏病例并给出下一步建议",
  "image_path": "C:/path/to/scan_dir",
  "session_id": "optional-session-id",
  "reviewer_enabled": true
}
```

字段说明：

- `query`：必填，临床问题或教育类问题
- `image_path`：可选，本地影像路径或 DICOM 目录路径
- `session_id`：可选，会话标识
- `reviewer_enabled`：是否启用报告审查节点

返回字段：

- `report`：生成的报告文本
- `preview_image_base64`：可选的预览图
- `consultation_id`：持久化后的咨询记录 ID
- `session_id`：当前会话 ID
- `status`：工作流状态
- `intent`：识别出的意图类型
- `perception_status`：感知分支状态
- `warnings`：降级、回退或提示信息
- `errors`：流程中的错误信息
- `evidence`：检索得到的语料库证据列表
- `trace`：节点执行轨迹

### `POST /v1/consult/upload`

通过上传 `.nii.gz` 文件显式同步执行一次咨询请求。

表单字段：

- `query`：必填
- `reviewer_enabled`：可选，默认 `true`
- `session_id`：可选
- `image_file`：必填，`.nii.gz` 文件

接口行为：

- 非 `.nii.gz` 文件会返回 `400`
- 上传文件会先写入会话级临时目录
- 当 SHA256 命中缓存时会复用已缓存文件
- 返回结果中的 `warnings` 会附带 cache hit / cache miss 信息

## 异步任务接口

说明：

- 当通过 `dispatch` 入口被判定为异步时，最终也会落到同一套 job 任务体系
- 因此 `/v1/jobs/{job_id}` 和 `/v1/jobs/{job_id}/events` 同样适用于 `dispatch(mode=async)` 返回的任务

### `POST /v1/jobs`

显式提交一个异步咨询任务。适用于调用方已经明确希望进入后台任务队列的场景。

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

## 常见错误

### `401 Unauthorized`

当启用了服务鉴权且 `X-API-Key` 缺失或错误时返回。

### `404 Not Found`

以下情况会返回：

- 任务不存在
- 咨询记录不存在

### `400 Bad Request`

当上传接口接收到非 `.nii.gz` 文件时返回。
