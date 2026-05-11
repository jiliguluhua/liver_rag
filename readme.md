# Medical Agent: DICOM-to-Decision Support System

本项目是一个基于 **LangGraph** 和 **Hybrid RAG** 架构的医疗智能体系统，旨在实现从 DICOM 影像处理到临床决策支持的全链路自动化。

## quick start

1. **启动后端接口**: `uvicorn app.main:app --reload`
2. **启动前端演示**: `streamlit run streamlit_app.py`（前端待优化）

## 系统架构

系统由四个核心模块组成:

1. **影像推理层**：基于 `MONAI` 与 `nnU-Net` 实现 3D 病灶自动分割与特征量化。
2. **检索增强层 (RAG)**：采用 **FAISS + BM25** 双路召回，并利用 **Cross-Encoder** 进行重排序，确保医学指南检索的严谨性。
3. **逻辑调度层**：通过 **LangGraph** 维护对话状态机，支持 **Query Rewriting**（提问改写）优化复杂医学意图识别。
4. **高性能接口**：基于 **FastAPI** 异步框架，结合 **SSE** 协议实现亚秒级流式响应。

## 技术栈

- **LLM 编排**: LangGraph, LangChain
- **医疗 AI**: MONAI, nnU-Net, SimpleITK
- **检索/向量库**: FAISS, BM25, Cross-Encoder
- **后端工程**: Python (FastAPI), Redis, MySQL, SSE
- **前端展示**: Streamlit (快速构建交互式医学影像看板，待优化)

---

## 核心技术实现

### 1. 混合检索与重排序 (Hybrid Search)

针对医学垂直领域中“术语精确度”与“语义关联性”的双重需求，本项目设计了双路混合检索方案：

- **语义维度 (FAISS)**：捕捉用户提问与医学文献间的深层语义联系。
- **术语维度 (BM25)**：针对药品名、手术器械等专有名词进行字面硬匹配，弥补向量检索在细粒度术语上的偏差。
- **精排层 (Rerank)**：引入 Cross-Encoder 对双路召回结果进行重评分，降低 LLM 的生成幻觉。

### 2. 状态机调度与工程优化

- **Query Rewriting (查询改写)**：集成意图识别模块，当原始提问语义模糊或缺乏上下文时，Agent 会利用 LLM 结合历史对话自动生成多角度的优化查询语句（Multiple Queries），提升长尾问题的召回率。
- **多轮对话管理**：利用 **Redis** 存储会话上下文，并设置 **TTL (Time To Live)** 自动清理陈旧数据，保障系统内存安全。
- **异步流式交互**：后端采用 **FastAPI (async/await)** 异步驱动，配合 **SSE (Server-Sent Events)** 技术，将 Agent 的思考过程与结论实时推送到前端。

---

## 项目目录结构

```bash
├── app/                # FastAPI 路由与 Pydantic 模型定义
├── agents/             # LangGraph 状态机定义与 Prompt 模板
├── rag/                # FAISS、BM25 混合检索与 Cross-Encoder 重排逻辑
├── medical_ai/         # MONAI 预处理与 nnU-Net 影像分割接口
├── core/               # 数据库与缓存配置 (Redis/MySQL)
├── requirements.txt    # 项目环境依赖
└── README.md
```
