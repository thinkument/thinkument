# Thinkument Python SDK (`thinkument-sdk`)

Official Python client library for the **Thinkument** open cognitive state machine platform ($P \times SM \times C \times W$). Auto-generated from canonical OpenAPI 3.1 specification (`openapi.v1.json`).

## Installation

```bash
pip install thinkument-sdk
```

## Quickstart

### 1. Connect to Local Studio Daemon ($0.00 / Offline)
Start your local studio with `thinkument dev` on port 5052, then connect:
```python
from thinkument_sdk import ThinkClient

# Connects to http://localhost:5052 (zero network required)
client = ThinkClient.local(5052)
```

### 2. Connect to Sovereign Cloud
```python
client = ThinkClient.connect(api_key="tk_live_...", endpoint="https://api.thinkument.com")
```

## Core Workflows

### Launch a Cognitive Session
```python
session = client.sessions.create(
    app_pack="starter",
    title="Quarterly Cognitive Review"
)
print(f"Session Genesis: {session.session_id} -> {session.url}")
```

### Interactive Trident Dispatch
Drive widget state transitions by dispatching signals and user data:
```python
result = session.dispatch(
    signal="next",
    data={"analysis_focus": "macroeconomic_drift"},
    role="author"
)
print(f"Committed Step {result.step_index}: status={result.status}")
```

### Role-Modulated Data Access
Inspect live session state modulated by actor permissions:
```python
reader_view = session.as_role("reader").get_state()
print("Visible Step Data:", reader_view.visible_micros)
```

### Stream Theta & Epsilon Observability Logs
```python
# Channel "theta" for semantic widget output; "epsilon" for telemetry/latency
events = session.events(channel="theta", since_seq=0)
for ev in events:
    print(f"[{ev.seq}] {ev.channel}: {ev.data}")
```

### Deterministic Time-Travel Hydration
```python
# Rewind session to checkpoint sequence #2
restored_session = session.hydrate(checkpoint_seq=2)
```

## License
Apache-2.0
