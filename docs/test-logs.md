# Test Logs

## 2026-05-13

Command:

```bash
pytest tests
```

Result:

- Passed

Current coverage:

- Unit: `agents.nodes` fallback, skip, placeholder, guardrail, and review-disable paths
- Unit: `services.job_events.JobEventBus`
- Unit: `agents.graph` routing branches
- Integration: `/health`, `/v1/consult`, `/v1/jobs`
- Integration: `/v1/consult/upload`, `/v1/jobs/upload`
- Integration: `/v1/jobs/{job_id}`
- Integration: `/v1/consultations`, `/v1/consultations/{consultation_id}`
- Integration: API key auth on protected endpoints

Notes:

- Test imports are stabilized through [`tests/conftest.py`](C:/Users/21204/Desktop/liver-rag/tests/conftest.py:1).
- Current tests avoid real LLM, FAISS, and perception model dependencies by using lightweight mocks and isolated test database setup.
