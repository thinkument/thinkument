# Thinkument Rust SDK (`thinkument`)

Official Rust client library for the **Thinkument** cognitive state machine platform ($P \times SM \times C \times W$). Auto-generated from canonical OpenAPI 3.1 specification (`openapi.v1.json`).

## Installation

Add to your `Cargo.toml`:
```toml
[dependencies]
thinkument = "0.1.0"
tokio = { version = "1.0", features = ["full"] }
serde_json = "1.0"
```

## Quickstart

```rust
use thinkument::{Client, SessionCreatePayload, DispatchPayload};
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Connect to local cognitive studio daemon (:5052)
    let client = Client::new("http://localhost:5052")?;

    // Or connect to Sovereign Cloud:
    // let client = Client::with_api_key("https://api.thinkument.com", "tk_live_...")?;

    // 1. Create a cognitive session
    let payload = SessionCreatePayload {
        P: json!({"kind": "starter_program"}),
        SM: None,
        C: None,
        slug: None,
        title: Some("Rust Native Engine".into()),
        roles: Some(vec!["author".into()]),
        public_view_role: None,
    };
    let session = client.create_session(&payload).await?;
    println!("Session Created: {} at {}", session.session_id, session.url);

    // 2. Interactive Trident Dispatch
    let dispatch = DispatchPayload {
        action: "signal".into(),
        user_fill: Some(json!({"intent": "deep_dive"})),
        user_signal: Some(json!({"signal": "next"})),
        cursor: None,
        role: Some("author".into()),
        identity_id: None,
    };
    let res = client.dispatch(&session.session_id, &dispatch).await?;
    println!("Trident Committed: status={}", res.status);

    Ok(())
}
```

## License
Apache-2.0
