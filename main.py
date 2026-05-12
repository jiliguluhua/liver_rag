import core.config as config
from services.medical_agent import LiverSmartAgent


if __name__ == "__main__":
    my_key = config.LLM_API_KEY
    test_dicom_dir = config.DEFAULT_DICOM_DIR or ""

    agent = LiverSmartAgent(
        api_key=my_key,
        model_path=config.PERCEPTION_MODEL_PATH,
        meta_path=config.PERCEPTION_META_PATH,
    )

    user_query = "Please analyze the current liver case and suggest the next clinical step."

    print("\n" + "=" * 10 + " Start end-to-end run " + "=" * 10)
    try:
        final_report, _preview, final_state = agent.run(test_dicom_dir, user_query)
        print("\n" + "=" * 10 + " Final report " + "=" * 10)
        print(final_report)
        print("\n" + "=" * 10 + " Workflow summary " + "=" * 10)
        print(
            {
                "intent": final_state.get("intent"),
                "status": final_state.get("workflow_status"),
                "perception_status": final_state.get("perception_status"),
                "warning_count": len(final_state.get("warnings", [])),
                "error_count": len(final_state.get("errors", [])),
            }
        )
        print("\n" + "-" * 60)
    except Exception as exc:
        print("Run failed:")
        raise exc
