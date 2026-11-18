package thinkument_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/thinkument/thinkument-go"
)

func TestGoldenTapeConformance(t *testing.T) {
	client := thinkument.NewLocalClient(5052)
	scenariosDir := filepath.Join("..", "..", "conformance", "scenarios")
	files, err := filepath.Glob(filepath.Join(scenariosDir, "*.json"))
	if err != nil || len(files) == 0 {
		t.Skip("Conformance scenarios not found")
	}

	for _, file := range files {
		data, err := os.ReadFile(file)
		if err != nil {
			t.Fatal(err)
		}
		var scenario map[string]any
		json.Unmarshal(data, &scenario)
		scenarioID := scenario["scenario_id"].(string)

		t.Run(scenarioID, func(t *testing.T) {
			if scenarioID == "02_vendor_interception" || scenarioID == "03_stateless_relay" {
				op := scenario["operation"].(string)
				mod := scenario["modality"].(string)
				args, _ := scenario["args"].(map[string]any)

				res, err := client.ExecuteOp(thinkument.RelayPayload{
					Operation: op,
					Modality:  mod,
					Args:      args,
				})
				if err != nil {
					t.Fatalf("ExecuteOp failed: %v", err)
				}
				if scenarioID == "02_vendor_interception" {
					if !strings.Contains(res.Text, "Mock") {
						t.Errorf("Expected response text to contain 'Mock', got '%s'", res.Text)
					}
				}
			}
		})
	}
}
