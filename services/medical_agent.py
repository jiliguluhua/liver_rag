import core.config as config
import llm_node
import perception.perception
import rag.hybrid_searcher


class LiverSmartAgent:
    def __init__(self, api_key, model_path=None, meta_path=None):
        model_path = model_path or config.PERCEPTION_MODEL_PATH
        meta_path = meta_path or config.PERCEPTION_META_PATH

        self.perception = perception.perception.MedicalPerception(model_path, meta_path)
        self.searcher = rag.hybrid_searcher.MedicalHybridSearcher()
        self.llm = llm_node.MedicalAgentLLM(api_key=api_key)

    def run(self, image_path, user_query):
        print(f"\nTask started: {user_query}")

        plan_prompt = (
            f"User question: '{user_query}'. "
            "Decide whether image-derived tumor measurements are needed to answer it. "
            "Reply with YES or NO only."
        )
        need_perception = self.llm.ask_simple_decision(plan_prompt)
        perception_data = "Image perception not used."
        preview_img = None

        if "YES" in need_perception.upper():
            print("Agent decided to run the perception module.")
            p_res = self.perception.get_tumor_volume(image_path)
            preview_img = p_res["preview_img"]
            perception_data = f"Tumor volume estimated from DICOM: {p_res['volume']:.2f} mL"
            print(f"Perception result: {perception_data}")
        else:
            print("Agent skipped image perception for this question.")

        print("Agent is retrieving supporting documents...")
        search_query = f"{user_query} {perception_data if 'YES' in need_perception.upper() else ''}"
        retrieved_docs = self.searcher.search(search_query, top_k=3)

        print("Agent is drafting the final report...")
        final_report = self.llm.generate_report(
            query=user_query,
            context_docs=retrieved_docs,
            perception_data=perception_data,
        )
        return final_report, preview_img

