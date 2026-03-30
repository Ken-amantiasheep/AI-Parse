# JSON Generator Regression Checklist

Use this checklist at the end of each refactor phase.

## 1) Automated Validation

- Run: `pytest tests/test_json_generator_smoke.py`
- Verify all tests pass with no import/runtime errors.
- If additional tests are added for the current phase, run them in the same command.

## 2) Manual Validation (one path per company is enough)

Validate each company flow once using your normal runtime path (GUI, CLI, or gateway).

- Intact_Auto
  - No traceback during generation.
  - Output JSON can be opened and parsed.
  - Date formats match Intact expected fields.
- CAA_Auto
  - No traceback during generation.
  - Output JSON can be opened and parsed.
  - CAA-specific fields still appear when expected.
- CAA_property
  - No traceback during generation.
  - Output JSON can be opened and parsed.
  - Property structure is intact (e.g., expected arrays/objects).
- Aviva (if enabled in your environment)
  - No traceback from the selected entrypoint.
  - Output path/behavior remains same as before.

## 3) Record Result

For each phase, record:

- Phase name:
- Date/time:
- Entrypoint used (GUI/CLI/gateway):
- Automated result:
- Manual result:
- Notes/risk observed:
