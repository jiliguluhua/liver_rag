# Java Knowledge Service

这个模块承接稳定业务主链路里的推荐与画像能力：

- `UserProfile`
- `LearningSession`
- `Recommend`
- `RecommendationLog`
- `RecommendationFeedback`

当前提供的是最小 Spring Boot 骨架和内存版闭环实现，便于后续继续替换为真实持久化与物料召回。

接口：

- `POST /api/v1/recommend`
- `POST /api/v1/recommend/feedback`

建议下一步继续补：

- JPA 实体和数据库迁移
- 从 `materials` 表或独立知识库召回候选
- 调用 Python RAG / rerank 子服务
- `LearningSession` 持久化与会话上下文对接
