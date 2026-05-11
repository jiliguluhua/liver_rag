import openai
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers import AutoTokenizer
import core.config as config

class MedicalAgentLLM:
    # def __init__(self):
    #   # self.model = AutoGPTQForCausalLM.from_quantized(
    #   #     config.LLM_LOCAL_MODEL_PATH,
    #   #     device="cuda:0",
    #   #     use_safetensors=True,
    #   #     trust_remote_code=True
    #   # )
    #   # self.model = AutoModelForCausalLM.from_pretrained(
    #   #   config.LLM_LOCAL_MODEL_PATH,
    #   #   device_map="auto",
    #   #   trust_remote_code=True
    #   # ).eval()
    #   # self.tokenizer = AutoTokenizer.from_pretrained(config.LLM_LOCAL_MODEL_PATH, trust_remote_code=True)
    #   # 模型从deepseek url api加载
    #     self.model = AutoModelForCausalLM.from_pretrained(
    #         config.LLM_LOCAL_MODEL_PATH,
    #         device_map="cuda:0 ",
    #         trust_remote_code=True
    #     ).eval()
    #     self.tokenizer = AutoTokenizer.from_pretrained(config.LLM_LOCAL_MODEL_PATH, trust_remote_code=True)
    #     print("本地 LLM 模型加载完成。")
    def __init__(self, api_key=config.LLM_API_KEY):
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=config.LLM_BASE_URL,
        )
        self.model_name = config.LLM_MODEL_NAME
        
    def ask_simple_decision(self, decision_prompt: str) -> str:
        """
        专门用于 Agent 内部逻辑决策的方法。
        强制 LLM 做出判断，返回 YES 或 NO。
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "你是一个逻辑严密的决策助手。请直接回答 YES 或 NO，不要包含任何标点符号、解释或多余文字。"
                    },
                    {"role": "user", "content": decision_prompt},
                ],
                # 决策需要极高的确定性，所以 temperature 设为 0
                temperature=0.0, 
                max_tokens=5
            )
            decision = response.choices[0].message.content.strip().upper()
            
            # 简单的防御性代码：防止模型吐出长句子
            if "YES" in decision:
                return "YES"
            return "NO"
            
        except Exception as e:
            print(f"⚠️ 决策节点异常: {e}")
            # 默认返回 YES 是一种保底策略：宁可多算（感知），不可漏掉信息
            return "YES"
        
    def generate_report(self, query, context_docs, perception_data=None):
        """
        query: 用户的问题
        context_docs: HybridSearcher 搜回来的文档列表
        perception_data: 感知层算出的结果 (如 19.57mL)
        """
        # 1. 拼接背景知识
        context_text = "\n".join([
            f"资料[{i+1}]: {doc.page_content[:1000]}" 
            for i, doc in enumerate(context_docs)
        ])             
        # 2. 构造 Prompt (这是 Agent 的灵魂)
        system_prompt = """你是一名资深的肝癌诊疗专家助手。
        请结合提供的【医学影像指标】和【权威指南参考资料】，为医生提供一份客观、准确的诊断建议。
        要求：
        1. 必须优先参考指南资料中的治疗准则。
        2. 如果指南中对特定体积或直径有明确分界，请严格比对。
        3. 报告需包含：影像表现总结、参考指南依据、治疗建议。
        4. 语言要专业，禁止胡编乱造。如果资料不足，请如实说明。"""

        user_content = f"""
        【用户咨询】：{query}
        【医学影像指标】：{perception_data if perception_data else "暂无"}
        【权威指南参考资料】：
        {context_text}
        
        请生成诊断建议报告：
        """
        prompt = system_prompt + "\n" + user_content
        
        # 3. 调用本地大模型
        try:
            # 2. 调用 API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一个严谨的医疗辅助诊断AI助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3, # 医疗场景建议低随机性
                max_tokens=1024
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"API 调用失败: {str(e)}"