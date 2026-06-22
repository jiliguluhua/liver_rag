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

Command:

```bash
pytest tests/integration/test_api.py -k "collect or report or persists_turns"
```

Result:

- Pending local verification after aligning `/v1/report` with sync/async routing.

Notes:

- This command is the recommended regression check for the current intake + report flow.
- Focus cases include collect response behavior, cached session image reuse, async report job creation, and intake turn persistence.

## 2026-05-16 Report Dispatch Update

Command:

```bash
pytest tests/unit/test_routing.py tests/integration/test_api.py
```

Result:

- Added test coverage for report-route sync/async routing and shared analyzer behavior.
- Execution was validated in the local user environment after the code update.

Current added coverage:

- Unit: `agents.routing.analyze_intent_routing` fallback behavior without `LLM_API_KEY`
- Unit: `agents.routing.analyze_intent_routing` parsing of analyzer LLM output
- Integration: `/v1/report` auto mode returning synchronous results
- Integration: `/v1/report` auto mode creating asynchronous jobs when perception is required
- Integration: `/v1/report` forced `sync` override
- Integration: `/v1/report/upload` auto mode with uploaded `.nii.gz`

Notes:

- Report routing and graph analyzer now share the same routing logic via [`agents/routing.py`](C:/Users/21204/Desktop/liver-rag/agents/routing.py:1).
- The new tests are intended to lock sync/async report behavior to the shared analyzer output rather than API-only keyword heuristics.

## 2026-06-23 Profile Java Cutover

Command:

```bash
cd C:\Users\21204\Desktop\liver-rag\java-backend
mvn -Dmaven.repo.local=%TEMP%\m2repo clean spring-boot:run
```

Result:

- Passed: Java `knowledge-service` started successfully on port `8081`

Command:

```bash
cd C:\Users\21204\Desktop\liver-rag
uvicorn api.main:app --reload
```

Result:

- Passed: Python FastAPI service started successfully on port `8000`

Command:

```bash
POST http://127.0.0.1:8000/v1/collect
POST http://127.0.0.1:8000/v1/profile/analyze
```

Result:

- Passed: `/v1/profile/analyze` returned a profile assembled through the Java profile service

Current added coverage:

- Java: `POST /api/v1/profile/analyze`
- Java: SQLite-backed session history loading from `intake_messages` and `consultations`
- Python: `/v1/profile/analyze` now prefers Java and falls back to local Python profile analysis only when Java is unavailable
- Integration: Python -> Java profile handoff using the same `session_id`

Notes:

- The Java response was verified from the Python Swagger page at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
- Successful Java-path verification used the returned English summary format, for example: `user-42 recently focused on ...`, which matches the Java summary template rather than the Python fallback summary.
- During bring-up, the Java service required three local fixes: excluding Spring `DataSourceAutoConfiguration`, forcing a clean rebuild to discard stale compiled classes, and using a clean Maven local repository path while dependencies were first downloaded.
