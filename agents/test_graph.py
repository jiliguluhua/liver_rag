# agents/test_graph.py
from agents.graph import medical_app

def run_test():
    # 1. 模拟输入数据
    # 测试场景 A：临床咨询（应该触发 RAG + 影像）
    test_input = {
        "query": "患者发现肝部结节，大小约 4cm，请结合指南给个建议。",
        "image_path": "./data/test_images/liver_scan.nii.gz", # 确保路径真实存在
        "context_docs": [],
        "perception_data": ""
    }

    print("--- 启动 LangGraph 医疗诊断流程 ---")
    
    # 2. 使用 stream 模式运行（最推荐，能看到每步的节点变化）
    try:
        for output in medical_app.stream(test_input):
            # output 是一个字典，key 是当前运行的节点名
            for node_name, state_update in output.items():
                print(f"\n[节点执行完成]: {node_name}")
                # 打印该节点更新了哪些状态
                for key, value in state_update.items():
                    print(f"  - 更新字段 {key}: {str(value)[:100]}...") 
                    
    except Exception as e:
        print(f"\n❌ 流程运行异常: {e}")

if __name__ == "__main__":
    run_test()