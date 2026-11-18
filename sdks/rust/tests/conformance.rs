use std::fs;
use std::path::Path;
use thinkument::{RelayPayload, ThinkClient};

#[tokio::test]
async fn test_golden_tape_conformance() {
    let client = ThinkClient::local(5052);
    let scenarios_dir = Path::new("../../conformance/scenarios");
    if !scenarios_dir.exists() {
        return;
    }

    for entry in fs::read_dir(scenarios_dir).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            let content = fs::read_to_string(&path).unwrap();
            let scenario: serde_json::Value = serde_json::from_str(&content).unwrap();
            let scenario_id = scenario["scenario_id"].as_str().unwrap();

            if scenario_id == "02_vendor_interception" || scenario_id == "03_stateless_relay" {
                let payload = RelayPayload {
                    operation: scenario["operation"].as_str().unwrap().to_string(),
                    args: Some(scenario["args"].clone()),
                    modality: scenario["modality"].as_str().map(|s| s.to_string()),
                };
                let res = client.execute_op(&payload).await;
                assert!(res.is_ok(), "Execute op failed for {}", scenario_id);
            }
        }
    }
}
