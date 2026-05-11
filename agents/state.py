from typing import  List, Optional, TypedDict

class AgentState(TypedDict):
    # 基础输入
    query: str
    image_path: Optional[str]
    
    # 任务分流结果
    intent: str                # "clinical" (诊疗), "education" (科普), "unrelated" (无关)
    
    # 执行结果数据
    context_docs: List[str]    # RAG 搜到的资料
    perception_data: str       # 影像计算指标
    
    # 自我审核与输出
    report: str                # 报告初稿/终稿
    review_feedback: str       # 审核节点的反馈建议
    is_medical_valid: bool     # 报告是否通过审核