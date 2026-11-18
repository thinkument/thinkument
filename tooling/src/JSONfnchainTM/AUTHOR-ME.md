# JSONfnchainTM Authoring Guide: From Public Envelopes to Internal Vocabularies

Status: Universal quickstart and reference guide for JSON function chain authoring.

---

## Part 1: The Public JSONic Widget Author Quickstart

### 1.1 The Single-Envelope Doctrine
As a public widget author, you write **only one JSON document**. You never configure Celery queues, manage thread locks, or write background polling loops. The runtime handles all concurrency, economics, and persistence behind the scenes.

```json
{
  "kind": "json_widget_v1",
  "name": "enterprise.marketing.campaign_generator",
  "title": "Campaign Generator",
  "declaration": {
    "inputs": {
      "brief": { "title": "str", "target_audience": "str" }
    },
    "outputs": {
      "campaign": { "tagline": "str", "ad_copy": "str" }
    }
  },
  "signals": {
    "mount": {
      "steps": [
        {
          "id": "generate_copy",
          "fn": "vendor.llm.chat_completion",
          "args": {
            "prompt": {
              "$concat": [
                "Write ad copy for ", "$mouth.brief.title",
                " targeting ", "$mouth.brief.target_audience"
              ]
            }
          }
        }
      ],
      "outputs": {
        "campaign": {
          "tagline": "Special Launch",
          "ad_copy": "$steps.generate_copy.text"
        }
      },
      "done": true
    }
  }
}
```

### 1.2 Accessing Lexical Scope
Within any JSON step expression, you have access to clean lexical namespaces via `$`:
- `$mouth.<port>.<field>`: Input data passed into the widget via wires from previous steps.
- `$steps.<step_id>.<field>`: Return values of previous steps in the current transition flow.
- `$prior_outputs.<port>.<field>`: Previously accepted outputs from earlier explosions of this widget.
- `$config.<key>`: Static widget configuration arguments.
- `$signal.<field>`: Payload metadata delivered with the current signal trigger.

### 1.3 Waiting on Asynchronous Upstream Wires
If an upstream widget emitted an asynchronous promise, your widget's input port still declares clean semantic data (`inputs={'brief': BriefSchema}`).
In your flow, simply pass the wire to `asyncwork.await_result`:
```json
{
  "id": "resolved_brief",
  "fn": "asyncwork.await_result",
  "args": {
    "promise": "$mouth.brief",
    "timeout_seconds": 45.0
  }
}
```
*Note: If the upstream was already synchronous, `asyncwork.await_result` passes it through immediately!*

---

## Part 2: The Two Approved Catalogues

### 2.1 Custom Python Ops Catalogue
| Function Name | Inputs | Output | Description |
| :--- | :--- | :--- | :--- |
| `text.template` | `{"template": Str, "vars": Map(Str)}` | `{"text": Str}` | String template interpolation |
| `text.concat` | `{"parts": List(Str), "sep": Str}` | `{"text": Str}` | Joins a list of strings with a separator |
| `math.add` | `{"a": Float, "b": Float}` | `{"result": Float}` | Adds two numbers |
| `math.multiply` | `{"a": Float, "b": Float}` | `{"result": Float}` | Multiplies two numbers |
| `data.extract` | `{"source": Map(Str), "key": Str}` | `{"value": Str?}` | Safely retrieves a map key |
| `asyncwork.await_result` | `{"promise": Dict({"ref": Str}), "timeout_seconds": Float?}` | `{"result": Map, "outcome": Str}` | Bounded wait on an asynchronous task handle |

### 2.2 Vendor Hub Ops Catalogue
| Function Name | Inputs | Output | Description |
| :--- | :--- | :--- | :--- |
| `vendor.llm.chat_completion` | `{"prompt": Str, "model": Str?, "temperature": Float?}` | `{"text": Str, "usage": Dict}` | LLM generation with Layer A economic quotas |
| `vendor.embeddings.generate` | `{"text": Str, "model": Str?}` | `{"vector": List(Float), "dimensions": Int}` | Generates vector embeddings |
| `vendor.media.image_generation`| `{"prompt": Str, "size": Str, "count": Int}` | `{"asset": Dict({"url": Str, ...})}` | Image creation with direct Storagics upload |

---

## Part 3: The Internal Developer Guide (Adding Function Sources)

### 3.1 Adding a New In-House Python Function
1. Create or open a module under `thinkument/framework/think-app-authoring/src/authoring_funneling/b_typed_JSON_widget_declaration/in_house_vocab/`.
2. Define the callable with signature `def fn(args: dict, ctx: FlowAttemptContext) -> dict`.
3. Register the function in `vocab_hub.py`:
   ```python
   vocab.register(
       name="text.reverse",
       inputs=Dict({"text": Str}),
       output=Dict({"result": Str}),
       fn=lambda a, c: {"result": a["text"][::-1]},
       version="1"
   )
   ```

### 3.2 Adding a New Vendor Hub Adapter
1. Ensure the operation is configured in `GatewayOperations` within `vendor-hub`.
2. In `interceptor.py`, define a `VendorBinding` using `create_gateway_vendor_binding`:
   ```python
   binding = create_gateway_vendor_binding(
       ops,
       operation_id="openai.chat_completions",
       request=lambda a: {"prompt": a["prompt"], "model": a.get("model")},
       project=lambda r: {"text": r.content, "usage": r.usage}
   )
   ```
3. Wire the binding into `THINKUMENT_GLOBAL_VOCAB` in `vocab_hub.py`.
