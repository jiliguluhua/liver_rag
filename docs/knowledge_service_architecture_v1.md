# 面向肝胆外科学习场景的知识服务架构 v1

## 1. 文档定位

这份文档用于定义项目下一阶段的业务主线与系统架构，作为后续重构前的设计依据。

它不替代现有的后端实现说明，而是在现有系统之上提出新的上层业务组织方式，用来回答三个问题：

- 现有“病例回答/报告生成”能力如何保留
- 新的“知识推荐”能力如何接入
- 多轮对话、用户画像、学习总结如何在同一套系统中协同工作

当前建议将这份文档与既有文档并行维护：

- [backend_architecture.md](C:/Users/21204/Desktop/liver-rag/docs/backend_architecture.md:1)：描述现有后端与工作流实现
- [api_documentation.md](C:/Users/21204/Desktop/liver-rag/docs/api_documentation.md:1)：描述现有接口
- 本文档：描述新的业务架构主线与分阶段建设目标

## 2. 为什么需要新架构

现有系统的核心主线是：

```text
用户输入 -> intake / collect -> retrieval / perception -> report
```

这条链路适合“单次病例咨询、医学影像辅助分析、报告生成”场景，但如果系统目标升级为“面向肝胆外科学习场景的知识服务”，仅靠原主线会出现几个问题：

- 业务对象仍然以 `consultation/report` 为中心，不利于组织长期知识资产
- 推荐能力缺少独立位置，容易被当作回答后的附属功能
- 多轮对话可以保存短期上下文，但难以支撑跨会话学习画像
- 报告如果只是重复答案和推荐，就缺少独立价值

因此，新架构建议把系统重心从“报告生成”调整为“知识服务”，并在统一知识底座上同时支持：

- `Answer`：针对当前问题的回答
- `Recommend`：针对学习目标或场景的推荐
- `Learning Session Report`：对一段学习过程的阶段性总结

## 3. 新系统定位

建议统一这样描述产品线：

“系统以肝胆术式为主线，围绕指南证据、病例材料、解剖主题、疾病与病理基础以及图像/视频载体构建统一知识底座，根据用户问题和学习场景同时支持病例回答、知识推荐与学习阶段总结。”

## 4. 核心设计原则

### 4.1 `Answer` 和 `Recommend` 分成两条主线

建议前端显式提供两个入口：

- `Answer`
- `Recommend`

二者可以串联，但不应混成一套流程。

`Answer` 的特点：

- 问题驱动
- 主要依赖当前 query、病例上下文、术式识别、topic 识别和知识检索
- 通常不强依赖用户画像
- 更关注“当前这个问题怎么回答”

`Recommend` 的特点：

- 目标驱动或场景驱动
- 明显依赖用户画像、学习历史、当前术式、当前场景
- 更关注“接下来你更适合看什么”

因此建议：

- `Answer` 作为独立主线
- `Recommend` 作为独立主线
- `Answer` 完成后可触发 `Recommend Next`

### 4.2 `Report` 不再作为默认主线

如果 `Report` 只是把 `Answer` 和 `Recommend` 再复述一遍，那么它没有独立价值。

建议将 `Report` 收缩为“阶段性沉淀能力”，并明确保留一种主要类型：

- `Learning Session Report`

它的用途是对一段学习过程生成结构化总结，例如：

- 学习了哪个术式
- 覆盖了哪些知识主题
- 当前薄弱点是什么
- 下一步适合看什么材料

也就是说，`Report` 不再默认在每次问答后生成，而是在用户主动触发总结时使用。

### 4.3 会话记忆和用户画像分层

多轮对话记忆仍然有价值，但它和用户表不是一回事。

建议分两层维护：

- `Session Memory`
  - 负责当前会话的短期上下文
  - 支持多轮 `Answer`
  - 适合存最近问题、最近 topic、最近材料

- `User Profile`
  - 负责跨会话的长期学习状态
  - 支持 `Recommend`
  - 支持 `Learning Session Report`

结论是：如果系统要支持跨天学习、持续推荐和学习总结，就需要引入用户表。

## 5. 业务主线重构

### 5.1 原有主线

```text
Consultation
  -> Retrieve
  -> Perceive
  -> Report
```

### 5.2 新主线

```text
User / Session
  -> Scene Understanding
  -> Procedure / Topic Parsing
  -> Knowledge Retrieval
  -> Capability Output
      -> Answer
      -> Recommend
      -> Learning Session Report
```

这里的关键变化不是放弃原有病例能力，而是把它重新放到统一知识服务架构中。

## 6. 统一知识底座

### 6.1 主实体

建议新的核心实体统一为：

- `Procedure`
- `KnowledgeTopic`
- `Material`
- `User`
- `UserProfile`
- `LearningSession`

### 6.2 知识组织方式

建议采用：

```text
Procedure
  -> Knowledge Topic
      -> Material
```

以 `cholecystectomy` 为例：

```text
cholecystectomy
  -> anatomy
  -> pathology_background
  -> operative_steps
  -> risk_points
  -> complications
  -> bailout_strategy
```

### 6.3 Material 最简分类方案

为了避免把“来源类型”“知识主题”“模态类型”混在一起，第一版建议只用 3 个基础字段描述 `Material`：

- `source_type`：材料来源类型
- `topic`：知识主题
- `modality`：材料模态

建议的第一版取值如下。

`source_type`

- `guideline`
- `review`
- `case`
- `reference`

`topic`

- `anatomy`
- `disease_background`
- `operative_steps`
- `risk_points`
- `complications`
- `bailout_strategy`

`modality`

- `text`
- `image`
- `video`

这三个字段分别解决三个问题：

- `source_type`：这条材料从哪来
- `topic`：这条材料讲什么
- `modality`：这条材料是什么形式

这样就可以避免把 `case/guideline/review` 和 `anatomy/image` 放在同一层硬并列。

例如：

- 一篇 Calot triangle 综述：`source_type=review`，`topic=anatomy`，`modality=text`
- 一张胆道变异示意图：`source_type=reference`，`topic=anatomy`，`modality=image`
- 一篇胆管损伤病例复盘：`source_type=case`，`topic=complications`，`modality=text`

这里并不是放弃原来的病例、指南、解剖或图像材料，而是把它们统一挂接到 `Procedure -> Topic -> Material` 之下，再用这 3 个字段说明它们的属性。

## 7. 三条能力线

### 7.1 Answer Line

定位：回答当前问题。

输入：

- 当前 query
- 当前 session 上下文
- 可选病例上下文

处理过程：

- 识别当前术式
- 识别相关 topic
- 检索相关材料
- 基于证据生成回答

输出：

- `answer`
- `evidence`
- `related_topics`
- 可选 `next_recommend_trigger`

特点：

- 以问题为中心
- 弱依赖用户画像

### 7.2 Recommend Line

定位：给出下一步学习材料建议。

输入：

- 用户主动提出的学习目标
- 当前 scene
- 用户画像
- 当前 session 或刚刚完成的 `Answer`

处理过程：

- 识别学习场景
- 锚定术式
- 召回候选材料
- 按 scene 与 profile 重排
- 输出推荐理由

输出：

- `recommended_materials`
- `recommend_reason`
- `topic_grouping`
- `next_step`

特点：

- 以学习目标和用户状态为中心
- 强依赖用户画像

### 7.3 Learning Session Report Line

定位：对一段学习过程做阶段性沉淀。

输入：

- 用户
- 学习 session
- 一段时间内的问答记录
- 一段时间内的推荐记录
- 已查看材料记录

输出：

- `covered_topics`
- `weak_topics`
- `recommended_next_topics`
- `recommended_next_materials`
- `summary`

特点：

- 不是每次都触发
- 只在用户主动总结时生成

## 8. 推荐的模块边界

建议拆成以下模块：

### 8.1 `interaction-service`

职责：

- 接收前端请求
- 管理 session
- 维护短期会话上下文
- 区分 `Answer` 与 `Recommend`

### 8.2 `profile-service`

职责：

- 维护用户表和用户画像
- 维护长期学习偏好
- 维护学习进度、关注术式、材料偏好

### 8.3 `knowledge-service`

职责：

- 管理 `Procedure -> Topic -> Material`
- 提供 topic 关系与材料过滤
- 作为统一知识底座

### 8.4 `retrieval-service`

职责：

- 统一检索知识材料
- 支持按术式、`source_type`、`topic`、`modality` 过滤
- 支持图文混合材料召回

### 8.5 `recommendation-service`

职责：

- 负责候选材料重排
- 按用户画像和 scene 组织推荐
- 输出推荐解释

### 8.6 `answer-service`

职责：

- 负责基于知识材料回答用户问题
- 输出结构化答案与证据

### 8.7 `report-service`

职责：

- 负责生成 `Learning Session Report`
- 负责学习阶段总结，而不是重复问答

### 8.8 `video-service`

职责：

- 当前仅预留接口和数据结构

## 9. 交互设计建议

建议前端先显式做成两个按钮：

- `Answer`
- `Recommend`

推荐交互方式：

### 9.1 `Answer`

- 用户输入具体问题
- 系统返回答案
- 页面给出“继续推荐”入口

### 9.2 `Recommend`

- 用户直接输入学习需求
- 系统返回材料推荐

### 9.3 `Learning Session Report`

- 用户主动点击“总结本次学习”
- 系统生成阶段总结

这样可以避免系统在每次请求时都自动猜测过多逻辑，也更符合用户心智。

## 10. 最小可行数据对象

为了支持新架构，建议后续引入以下长期数据对象：

- `User`
- `UserProfile`
- `LearningSession`
- `LearningRecord`
- `Procedure`
- `KnowledgeTopic`
- `Material`
- `RecommendationLog`

这里特别说明：

- `Session Memory` 继续用于短期上下文
- `UserProfile` 用于长期个性化
- `LearningSession` 用于总结和阶段报告
- `Material` 第一版只强制要求维护 `source_type`、`topic`、`modality` 三个基础字段，其他字段后续逐步补齐

## 11. 分阶段建设建议

为了降低改造风险，建议分成两个阶段推进。

### 11.0 Java / Python 边界

为了避免技术栈职责重叠，当前建议的边界如下。
稳定业务系统放 Java，快速迭代的 AI 推理流程放 Python。

适合优先放在 Java 的部分：

- 用户体系：`User`、`UserProfile`
- 知识材料管理：`Procedure`、`KnowledgeTopic`、`Material`
- 推荐编排：`Recommend` 接口、推荐日志、后续重排服务
- (当然如果以后推荐里 LLM 成分很重，也可以让 Java 编排主流程，再调用 Python 做一小段 AI rerank。)
- 学习会话管理：`LearningSession`、学习记录、学习总结入口
- 面向前端的稳定业务接口

适合继续保留在 Python 的部分：

- LangGraph 工作流
- 医学问答主链路 `Answer`
- 医学影像感知
- 当前已存在的 RAG 与检索实验逻辑
- 需要频繁试验和快速调整的推理流程

因此，第一阶段的明确分工建议是：

- Java 负责“业务壳”和长期数据
- Python 负责“问答内核”和感知工作流

等到后续 `Recommend` 逻辑稳定后，再决定是否继续保留 Python 版本推荐链路，或完全迁到 Java。

### 11.1 第一阶段：先把主线收稳

这一阶段的目标不是做全，而是把新的业务骨架立住。

第一阶段建议完成：

- 明确产品主线为 `Answer + Recommend + Learning Session Report`
- 明确 `Procedure -> Topic -> Material` 作为核心数据模型
- 定下 `Material` 的最简三层分类：`source_type + topic + modality`
- 前端显式区分 `Answer` 和 `Recommend`
- `Answer` 先做问题驱动链路
- `Recommend` 先做基础场景推荐链路
- 引入最小用户表与用户画像表
- 引入 `LearningSession` 概念
- 保留原 `report` 能力，但从默认主链路中退出

这一阶段完成后，系统会从“单次咨询系统”升级为“有明确知识主线的学习支持系统”。

### 11.2 第二阶段：再做个性化和总结能力

第二阶段建议完成：

- 推荐结果接入长期用户画像
- 维护用户已看材料、偏好材料和关注术式
- 维护 learning session 内的学习轨迹
- 生成 `Learning Session Report`
- 逐步把图片材料纳入推荐和展示主链路
- 逐步扩展 `video` 模态在手术视频场景中的应用

这一阶段完成后，系统才真正具备“持续学习推荐”的味道。

## 12. 当前结论

现阶段最值得定下来的结论有四个：

- 系统主线从“报告生成”升级为“知识服务”
- `Answer` 和 `Recommend` 分成两条主线
- `Report` 只保留为阶段性学习总结能力
- 如果要做长期推荐和学习总结，就需要正式引入用户表

后期改进路线：知识点卡片（前端展示）、知识图谱、docker部署。
