# Thinkument

> **The Sovereign Cognitive State Machine Platform.**  
> *Steve Jobsian Ergonomics • Local Studio • Zero-Host-Dependency Binary • Multi-Language SDKs*  
> **Official Distribution Repository:** [github.com/thinkument/thinkument](https://github.com/thinkument/thinkument)

[![License: FSL-1.1-Apache-2.0](https://img.shields.io/badge/License-FSL--1.1--Apache--2.0-blue.svg)](LICENSE)
[![npm version](https://img.shields.io/npm/v/@thinkument/cli.svg?color=cb3837)](https://www.npmjs.com/package/@thinkument/cli)
[![PyPI version](https://img.shields.io/pypi/v/thinkument-cli.svg?color=3775a9)](https://pypi.org/project/thinkument-cli/)
[![Homebrew Tap](https://img.shields.io/badge/Homebrew-thinkument%2Ftap-orange.svg)](https://github.com/thinkument/homebrew-tap)

---

## What is Thinkument?

Thinkument is an offline-first cognitive runtime and state-machine execution platform. It replaces tangled, unpredictable AI prompt chains with formal mathematical certainty: **$P \times SM \times C$**.

- **P (Program):** Directed sequence of steps populated by declarative widgets. When a step completes, downstream widgets mount, explode, and react.
- **SM (State Machine):** Role-modulated dispatch guards enforcing atomic trident commits. Multiple actors interact with the same run simultaneously without race conditions.
- **C (Context):** Theta and Epsilon stream channels providing total event isolation, real-time observability, and instant time-travel state hydration.

Whether you run it as an **offline local cognitive studio**, compile it into an **11 MB hermetic native executable**, or integrate it via our **typed SDKs (Python, TypeScript, Go, Rust)**, Thinkument delivers the power of complex cognitive systems with the effortless simplicity of a consumer product.

---

## 3-Second Quickstart Across Any Environment

Thinkument requires **zero external runtime dependencies** (no Python, no Node, no Docker required on the host system when using binary or npm distributions).

### Option 1: Using npm / npx (Node.js Developers)
Boot the local cognitive studio daemon on `http://localhost:5052` in $<150\text{ms}$:
```bash
npx thinkument dev
```

### Option 2: Using Homebrew (macOS & Linux)
Install the official hermetic native single binary via our sovereign tap:
```bash
brew tap thinkument/tap
brew install thinkument
thinkument dev
```

### Option 3: Universal Single-Line POSIX Installer (Shell / CI/CD)
```bash
curl -fsSL https://thinkument.com/install.sh | sh
thinkument --help
```

### Option 4: Using Python (PyPI)
```bash
pip install thinkument-cli
thinkument dev
```

---

## The 8-Act Interactive Masterclass Tour

Experience Thinkument's architectural paradigm through an interactive, live-executing Jupyter laboratory:

```bash
thinkument tour
```

This launches the interactive **8-Act SDK Masterclass Tour** (`notebooks/thinkument_sdk_tour.ipynb`), taking you hands-on through:
1. **Act I: The Local Cognitive Studio**: Starting the offline daemon and verifying system health.
2. **Act II: The Canonical Schema & OpenAPI Parity**: Discovering endpoints dynamically.
3. **Act III: Session Genesis & App-Pack Mounting**: Initializing reproducible cognitive environments.
4. **Act IV: The Dispatch Loop & Signal Triggers**: Driving widget state transitions.
5. **Act V: Role-Modulated Dispatching**: Multi-role safety guards and permission boundaries.
6. **Act VI: Epsilon Subapps**: Event streams, telemetry, and live analytics.
7. **Act VII: Deterministic Time-Travel Hydration**: Capturing and restoring complete execution states.
8. **Act VIII: Sovereign Offline Studio**: Zero-network cognitive execution.

---

## First-Class Client SDKs in 4 Languages

Thinkument ships with strictly typed, auto-generated SDKs derived from our canonical OpenAPI 3.1 specification.

````carousel
```python
# Python: pip install thinkument-cli
import thinkument

client = thinkument.Client(base_url="http://localhost:5052")
session = client.sessions.create(app_pack="starter")

# Dispatch signal to pending widgets
result = session.dispatch(
    signal="next",
    data={"input": "Analyze quarterly trajectory"}
)
print(f"Step {result.step_index}: {result.status}")
```
<!-- slide -->
```typescript
// TypeScript: npm install @thinkument/sdk
import { ThinkumentClient } from '@thinkument/sdk';

const client = new ThinkumentClient({ baseUrl: 'http://localhost:5052' });
const session = await client.sessions.create({ appPack: 'starter' });

// Dispatch signal with full TypeScript auto-completion
const result = await session.dispatch({
  signal: 'next',
  data: { input: 'Analyze quarterly trajectory' }
});
console.log(`Step ${result.stepIndex}: ${result.status}`);
```
<!-- slide -->
```go
// Go: go get github.com/thinkument/thinkument/sdks/go
package main

import (
    "context"
    "fmt"
    "github.com/thinkument/thinkument/sdks/go"
)

func main() {
    client := thinkument.NewClient("http://localhost:5052")
    session, _ := client.Sessions.Create(context.Background(), "starter")
    result, _ := session.Dispatch(context.Background(), "next", map[string]any{
        "input": "Analyze quarterly trajectory",
    })
    fmt.Printf("Step %d: %s\n", result.StepIndex, result.Status)
}
```
<!-- slide -->
```rust
// Rust: cargo add thinkument
use thinkument::Client;
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::new("http://localhost:5052")?;
    let session = client.sessions().create("starter").await?;
    let result = session.dispatch("next", json!({"input": "Analyze quarterly trajectory"})).await?;
    println!("Step {}: {}", result.step_index, result.status);
    Ok(())
}
```
````

---

## Repository Structure

```text
thinkument/
├── core/
│   ├── backend/        # P x SM x C state machine engine & run-from-here facade
│   ├── frontend/       # ThinkumentJS womb runtime & live DOM-scripted vial
│   ├── app/            # Local Flask studio runner (:5052) & ways-to-run
│   └── authoring/      # Declarative widget & program templates
├── cli/                # Native unified CLI (dev, validate, publish, balance)
├── sdks/               # Multi-language client libraries
│   ├── python/         # Official Python client SDK
│   ├── typescript/     # Official TypeScript client SDK
│   ├── go/             # Official Go client SDK
│   └── rust/           # Official Rust client SDK
├── spec/               # Canonical OpenAPI 3.1 contract (openapi.v1.json)
└── notebooks/          # Masterclass Tour (thinkument_sdk_tour.ipynb)
```

---

## Sovereign Dual Licensing

Thinkument is committed to remaining **100% open, sovereign, and free for developers forever**:

1. **Core Engine & CLI (`core/app/`, `cli/`):**  
   Licensed under the **Functional Source License (FSL-1.1-Apache-2.0)**.  
   - Free for developers, startups, researchers, and enterprises.  
   - Free for internal business and commercial production applications.  
   - Automatically converts to standard **Apache 2.0** two years after each release.  
   - Sole legal restriction: Prevents hyperscaler cloud providers from taking the engine and reselling it as a competing closed managed cloud service.

2. **Client SDKs, Contracts & Tooling (`sdks/`, `spec/`, `core/backend/`, `tooling/`):**  
   Licensed under the fully permissive **Apache License, Version 2.0**.

---

<p align="center">
  <sub>Engineered with precision by the Thinkument Team • <a href="https://thinkument.com">thinkument.com</a></sub>
</p>
