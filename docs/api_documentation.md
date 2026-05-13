# API 接口文档

鉴权方式：

- 当配置了 `LIVER_SERVICE_API_KEY` 时，受保护接口需要在请求头中携带 `X-API-Key`
- 当未配置服务鉴权 key 时，可直接访问接口

支持的内容类型：

- `application/json`：标准咨询与任务提交接口
- `multipart/form-data`：上传类接口
- `text/event-stream`：SSE 任务事件流接口

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

### `POST /v1/consult`

同步执行一次咨询请求。

请求体：

```json
{
  "query": "请分析当前肝脏病例并给出下一步建议。",
  "image_path": "C:/path/to/scan_dir",
  "session_id": "optional-session-id",
  "reviewer_enabled": true
}
```

字段说明：

- `query`：必填，临床问题或医学教育类问题
- `image_path`：可选，本地图像路径或 DICOM 目录路径
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

通过上传 `.nii.gz` 文件同步执行一次咨询请求。

表单字段：

- `query`：必填
- `reviewer_enabled`：可选，默认 `true`
- `session_id`：可选
- `image_file`：必填，`.nii.gz` 文件

接口行为：

- 非 `.nii.gz` 文件会返回 `400`
- 上传文件会先写入会话级临时目录
- 当 SHA256 命中缓存时会复用已缓存文件
- 返回结果中的 `warnings` 会附加 cache hit / cache miss 信息

## 异步任务接口

### `POST /v1/jobs`

提交一个异步咨询任务。

请求体：

```json
{
  "query": "请分析该病例。",
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

通过上传 `.nii.gz` 文件提交一个异步咨询任务。

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

获取任务状态snapshot。

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
- 当任务状态发生变化时，会推送新的任务snapshot
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
