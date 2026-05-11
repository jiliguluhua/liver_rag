from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import *

def create_medical_graph():
    workflow = StateGraph(AgentState)

    # 添加所有节点
    workflow.add_node("analyzer", intent_analyzer_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("perceptor", perception_node)
    workflow.add_node("reporter", generate_report_node)
    workflow.add_node("reviewer", medical_review_node)

    # 1. 起点：意图分析
    workflow.set_entry_point("analyzer")

    # 2. 意图路由 (分流逻辑)
    def route_by_intent(state: AgentState):
        if state["intent"] == "clinical":
            return ["retriever", "perceptor"] # 并行触发检索和影像
        elif state["intent"] == "education":
            return "retriever"               # 只需科普检索
        else:
            return "reporter"                # 无关问题直接去回复

    workflow.add_conditional_edges(
        "analyzer",
        route_by_intent,
        {
            "retriever": "retriever",
            "perceptor": "perceptor",
            "reporter": "reporter"
        }
    )

    # 3. 汇聚：检索和影像完成后，都汇聚到报告生成
    workflow.add_edge("retriever", "reporter")
    workflow.add_edge("perceptor", "reporter")

    # 4. 审核循环 (反思逻辑)
    workflow.add_edge("reporter", "reviewer")

    def route_after_review(state: AgentState):
        if state["is_medical_valid"]:
            return "end"
        else:
            return "retry"

    workflow.add_conditional_edges(
        "reviewer",
        route_after_review,
        {
            "end": END,
            "retry": "reporter" # 审核不通过，回到生成节点重写
        }
    )

    return workflow.compile()

medical_app = create_medical_graph()