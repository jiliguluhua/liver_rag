from langgraph.graph import END, StateGraph

from .nodes import (
    generate_report_node,
    intent_analyzer_node,
    medical_review_node,
    perception_node,
    retrieve_node,
)
from .state import AgentState


def create_medical_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("analyzer", intent_analyzer_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("perceptor", perception_node)
    workflow.add_node("reporter", generate_report_node)
    workflow.add_node("reviewer", medical_review_node)

    workflow.set_entry_point("analyzer")

    def route_after_analyzer(state: AgentState):
        if state.get("intent") == "unrelated":
            return "reporter"
        should_retrieve = state.get("should_retrieve", True)
        should_perceive = state.get("should_perceive", False)
        if should_retrieve and should_perceive:
            return ["retriever", "perceptor"]
        if should_retrieve:
            return "retriever"
        if should_perceive:
            return "perceptor"
        return "reporter"

    workflow.add_conditional_edges(
        "analyzer",
        route_after_analyzer,
        {
            "retriever": "retriever",
            "perceptor": "perceptor",
            "reporter": "reporter",
        },
    )

    workflow.add_edge("retriever", "reporter")
    workflow.add_edge("perceptor", "reporter")

    def route_after_reporter(state: AgentState):
        if state.get("reviewer_enabled", True) and state.get("intent") != "unrelated":
            return "reviewer"
        return "end"

    workflow.add_conditional_edges(
        "reporter",
        route_after_reporter,
        {
            "reviewer": "reviewer",
            "end": END,
        },
    )

    workflow.add_edge("reviewer", END)

    return workflow.compile()


medical_app = create_medical_graph()
