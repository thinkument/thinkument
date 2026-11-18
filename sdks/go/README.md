# Thinkument Go SDK (`github.com/thinkument/thinkument-go`)

Official Go client library for the **Thinkument** cognitive state machine platform ($P \times SM \times C \times W$). Auto-generated from canonical OpenAPI 3.1 specification (`openapi.v1.json`).

## Installation

```bash
go get github.com/thinkument/thinkument-go
```

## Quickstart

```go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/thinkument/thinkument-go"
)

func main() {
	ctx := context.Background()

	// Connect to local cognitive studio daemon (:5052)
	client := thinkument.NewClient("http://localhost:5052")

	// Or connect to Sovereign Cloud:
	// client := thinkument.NewClientWithAuth("https://api.thinkument.com", "tk_live_...")

	// 1. Create a cognitive session
	session, err := client.CreateSession(ctx, thinkument.SessionCreatePayload{
		P: map[string]any{"kind": "starter_program"},
		Title: "Executive Analysis Session",
	})
	if err != nil {
		log.Fatalf("Failed to create session: %v", err)
	}
	fmt.Printf("Session ID: %s, URL: %s\n", session.SessionID, session.URL)

	// 2. Interactive Trident Dispatch
	dispatchRes, err := client.Dispatch(ctx, session.SessionID, thinkument.DispatchPayload{
		Action: "signal",
		UserSignal: map[string]any{"trigger": "next"},
		UserFill: map[string]any{"analysis": "macro_trends"},
	})
	if err != nil {
		log.Fatalf("Dispatch failed: %v", err)
	}
	fmt.Printf("Committed Trident: status=%s\n", dispatchRes.Status)
}
```

## License
Apache-2.0
