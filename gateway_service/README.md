# Gateway Service

## Purpose

Internal API gateway for AI Parse:

- Holds `ANTHROPIC_API_KEY` on server side only
- Accepts document text from client
- Calls Anthropic and returns normalized JSON

## Run locally

```bash
pip install -r gateway_service/requirements.txt
set ANTHROPIC_API_KEY=xxx
set INTERNAL_API_TOKEN=yyy
python -m uvicorn gateway_service.app:app --host 0.0.0.0 --port 8080
```

## Endpoints

- `GET /health`
- `POST /v1/generate-json`

## Request Header

- `X-Internal-Token` (required if `INTERNAL_API_TOKEN` is configured)
