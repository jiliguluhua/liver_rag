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
- Integration: `/v1/jobs/{job_id}/events`
- Integration: `/v1/consultations`, `/v1/consultations/{consultation_id}`
- Integration: API key auth on protected endpoints

Notes:

- Test imports are stabilized through [`tests/conftest.py`](C:/Users/21204/Desktop/liver-rag/tests/conftest.py:1).
- Current tests avoid real LLM, FAISS, and perception model dependencies by using lightweight mocks and isolated test database setup.

## 2026-05-16

Command:

```bash
pytest tests/integration/test_api.py -k "job_events_stream or get_job_status or submit_job"
```

Result:

- Passed: `2 passed, 12 deselected, 15 warnings in 8.47s`

Notes:

- `deselected` means 12 tests were intentionally not run because the `-k` filter only selected matching cases; this is not an error.
- Warnings included `pkg_resources` / `Setuptools<81` related output and did not fail the test run.

Command:

```bash
pytest tests/integration/test_api.py -k "collect_endpoint or report_endpoint or persists_turns"
```

Result:

- Passed: `3 passed, 19 deselected, 15 warnings in 8.25s`

Notes:

- This run covered the new intake / report flow and session-context persistence behavior.
- `deselected` means the remaining tests in `test_api.py` were intentionally filtered out and not executed.

## 2026-05-16 Dispatch Update

Command:

```bash
pytest tests/unit/test_routing.py tests/integration/test_api.py
```

Result:

- Added test coverage for dispatch routing and shared analyzer behavior.
- Execution was validated in the local user environment after the code update.

Current added coverage:

- Unit: `agents.routing.analyze_intent_routing` fallback behavior without `LLM_API_KEY`
- Unit: `agents.routing.analyze_intent_routing` parsing of analyzer LLM output
- Integration: `/v1/dispatch` auto mode returning synchronous results
- Integration: `/v1/dispatch` auto mode creating asynchronous jobs when perception is required
- Integration: `/v1/dispatch` forced `sync` override
- Integration: `/v1/dispatch/upload` auto mode with uploaded `.nii.gz`

Notes:

- Dispatch and graph analyzer now share the same routing logic via [`agents/routing.py`](C:/Users/21204/Desktop/liver-rag/agents/routing.py:1).
- The new tests are intended to lock sync/async dispatch behavior to the shared analyzer output rather than API-only keyword heuristics.
