from agents.state import AgentState
from core.initializer import logic_llm, report_llm
from rag.hybrid_searcher import hybrid_searcher
from perception.perception import MedicalPerception

# 4. 报告生成节点
def generate_report_node(state: AgentState):
    # 汇总所有 State 信息，交给 LLM 生成报告
    prompt = f"""
    参考指南: {state['context_docs']}
    影像指标: {state.get('perception_data', '不涉及')}
    用户问题: {state['query']}
    请生成一份严谨的医疗建议报告。
    """
    res = report_llm.invoke(prompt)
    return {"report": res.content}

# --- 节点 1: 意图分析 (分类器) ---
def intent_analyzer_node(state: AgentState):
    prompt = f"分析用户问题: {state['query']}\n分类为: 'clinical'(涉及诊断治疗)、'education'(一般医学科普)或'unrelated'(无关)。只回答分类词。"
    # 使用 0 温控的逻辑模型
    res = logic_llm.invoke(prompt)
    return {"intent": res.content.strip().lower()}

# --- 节点 2: 知识检索 ---
def retrieve_node(state: AgentState):
    # # 真实调用
    # query = state["query"]
    # docs = hybrid_searcher.search(query) 
    # return {"context_docs": docs}
    
    # 测试模拟检索逻辑
    return {"context_docs": ["指南: 肝癌结节>3cm建议考虑手术治疗..."]}

# --- 节点 3: 影像感知 ---
def perception_node(state: AgentState):
    # # 真实调用
    # result = MedicalPerception().run_inference(image_path=state.get("image_path"))
    # return {"perception_data": result}
    
    # 模拟调用 MONAI/nnU-Net
    return {"perception_data": "肿瘤直径约 4.5cm, 体积 22ml"}

# --- 节点 4: 报告生成 ---
def generate_report_node(state: AgentState):
    intent = state["intent"]
    if intent == "unrelated":
        return {"report": "抱歉，我只能生成医疗相关的报告。"}
    prompt = f"""
    基于意图：{intent}
    参考指南: {state['context_docs']}
    影像指标: {state.get('perception_data', '不涉及')}
    用户问题: {state['query']}
    请生成一份严谨的医疗建议报告。
    如果有审核反馈[{state.get('review_feedback','')}]，请进行修正。"
    """
    res = report_llm.invoke(prompt)
    return {"report": res.content}

# --- 节点 5: 医疗审核 (反思节点) ---
def medical_review_node(state: AgentState):
    # 这个节点专门检查 AI 是否胡说八道
    report = state["report"]
    prompt = f"你是审核专家。检查以下报告是否符合医学逻辑：{report}\n如果不符合，请指出具体错误。如果没问题，请回复'PASS'。"
    res = logic_llm.invoke(prompt)
    
    if "PASS" in res.content.upper():
        return {"is_medical_valid": True, "review_feedback": ""}
    else:
        return {"is_medical_valid": False, "review_feedback": res.content}