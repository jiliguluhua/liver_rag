import os
import core.config as config
import perception.perception
import skills.document_processor
import rag.hybrid_searcher
import llm_node

class LiverSmartAgent:
    def __init__(self, api_key, model_path=None, meta_path=None):
        MODEL_PATH = config.PERCEPTION_MODEL_PATH
        META_PATH = config.PERCEPTION_META_PATH

        self.perception = perception.perception.MedicalPerception(MODEL_PATH, META_PATH)
        self.searcher = rag.hybrid_searcher.MedicalHybridSearcher()
        self.llm = llm_node.MedicalAgentLLM(api_key=api_key)

    def run(self, image_path, user_query):
        print(f"\n任务启动: {user_query}")
        
        # --- 第一步：意图识别 (Planning) ---
        plan_prompt = f"用户问：'{user_query}'。请判断：为了回答这个问题，我是否需要分析患者的影像学指标（如肿瘤大小、体积）？只需回答 'YES' 或 'NO'。"
        need_perception = self.llm.ask_simple_decision(plan_prompt)
        perception_data = "未调用影像分析技能"
        preview_img = None
        
        # --- 第二步：执行感知技能 (Action) ---
        if "YES" in need_perception.upper():
            print("Agent 思考：这是一个影像相关问题，正在启动视觉感知技能...")
            p_res = self.perception.get_tumor_volume(image_path)
            preview_img = p_res['preview_img']
            perception_data = f"根据dicom动脉期图像，肿瘤直径体积{p_res['volume']:.2f}mL"
            print(f" 感知结果: {perception_data}")
        else:
            print(" Agent 思考：这是通用知识问题，跳过影像分析。")

        # --- 第三步：执行检索技能 (Action) ---
        print("Agent 思考：正在查阅本地知识库以获取权威依据...")
        search_query = f"{user_query} {perception_data if 'YES' in need_perception.upper() else ''}"
        retrieved_docs = self.searcher.search(search_query, top_k=3)

        # --- 第四步：整合决策 (Final Answer) ---
        print("Agent 思考：正在整合所有线索生成诊断建议...")
        final_report = self.llm.generate_report(
            query=user_query,
            context_docs=retrieved_docs,
            perception_data=perception_data
        )
        return final_report, preview_img
  
if __name__ == "__main__":
    # --- 统一从 config 读取测试数据 ---
    MY_KEY = config.LLM_API_KEY
    TEST_DICOM_DIR = config.DEFAULT_DICOM_DIR or ""
    
    # 初始化时，直接传入 config 里的路径，保证接力棒传到位
    agent = LiverSmartAgent(
        api_key=MY_KEY, 
        model_path=config.PERCEPTION_MODEL_PATH, 
        meta_path=config.PERCEPTION_META_PATH
    )
    
    # 模拟用户提问
    user_query = "请根据该患者的影像指标，结合临床指南，给出诊断倾向和下一步治疗建议。"
    
    print("\n" + "🚀" * 10 + " 启动全链路会诊 " + "🚀" * 10)
    if not MY_KEY:
        raise SystemExit("请设置环境变量 LLM_API_KEY")
    if not TEST_DICOM_DIR:
        raise SystemExit("请设置环境变量 LIVER_DEFAULT_DICOM_DIR 或在代码中指定 TEST_DICOM_DIR")
    try:
        final_report, _preview = agent.run(TEST_DICOM_DIR, user_query)

        print("\n" + "🩺" * 10 + " 最终会诊报告 " + "🩺" * 10)
        print(final_report)
        print("\n" + "—" * 60)
        
    except Exception as e:
        print(f"运行失败！")
        raise e