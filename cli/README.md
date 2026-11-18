# Thinkument CLI & SDK (`thinkument`)

The official command-line interface and developer SDK for the **Thinkument** open coordination framework ($P \times SM \times C \times W$).

## Features
- **Rung 1: 100% Free Offline Studio**: Start local in-memory studio on `http://localhost:5052` with `thinkument dev`.
- **Universal Mocking Seam**: Deterministic schema-valid mocks, local custom Python callables (`--mocks-file`), local air-gapped AI bridge (`--vendor-ollama`), or webhook proxy (`--vendor-proxy`).
- **Rung 2: Stateless Cloud Relay**: Single API key completions with prepaid wallet escrow via `POST /api/v1/ops/execute/`.
- **Rung 3: Sovereign Cloud Operations**: Live hosted multi-user sessions, iframe embeds, headless black-box runs, and parallel C-matrix batch sweeps.
- **Single-Envelope JSON Validation**: Validate widget and program manifests in $<1\text{ms}$ with `thinkument validate`.

## Quickstart

```bash
# Start local studio
thinkument dev my_program.json

# Validate schemas
thinkument validate my_widget.json

# Headless black-box run
thinkument run my_program.json --context my_context.json
```

## Python SDK

```python
from thinkument import ThinkClient

# Local mode (Rung 1)
client = ThinkClient.local(port=5052)
session = client.live.create(P=my_program, SM=my_session_metadata, C={"key": "val"})
print(session.selected.url)

# Cloud mode (Rung 3)
cloud = ThinkClient.connect(api_key="tk_live_...")
live_run = cloud.live.create(P=my_program, SM=my_session_metadata, C={"key": "val"})
print(live_run.selected.url)
```
