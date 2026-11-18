# Thinkument Python SDK

Generated directly from canonical OpenAPI 3.1 specification (`openapi.v1.json`).

## Installation

```bash
pip install thinkument-sdk
```

## Quickstart

```python
from thinkument_sdk import ThinkClient

# Connect to local offline daemon ($0.00)
client = ThinkClient.local(5052)

# Or connect to Sovereign Cloud
client = ThinkClient.connect(api_key="tk_live_...")
```
