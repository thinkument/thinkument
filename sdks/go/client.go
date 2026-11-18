package thinkument

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type Client struct {
	BaseURL    string
	APIKey     string
	HTTPClient *http.Client
}

func NewLocalClient(port int) *Client {
	if port <= 0 {
		port = 5052
	}
	return &Client{
		BaseURL:    fmt.Sprintf("http://127.0.0.1:%d", port),
		HTTPClient: &http.Client{Timeout: 10 * time.Second},
	}
}

func NewClient(apiKey, baseURL string) *Client {
	if baseURL == "" {
		baseURL = "https://api.thinkument.com"
	}
	return &Client{
		BaseURL:    baseURL,
		APIKey:     apiKey,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *Client) Health() (*HealthzResponse, error) {
	req, _ := http.NewRequest("GET", c.BaseURL+"/healthz/", nil)
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res HealthzResponse
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

func (c *Client) ExecuteOp(payload RelayPayload) (*RelayResponse, error) {
	body, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", c.BaseURL+"/api/v1/ops/execute/", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res RelayResponse
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

func (c *Client) CreateLiveSession(payload SessionCreatePayload) (*SessionCreateResponse, error) {
	body, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", c.BaseURL+"/api/v1/sessions/", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res SessionCreateResponse
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

func (c *Client) Dispatch(sessionID string, payload DispatchPayload) (*DispatchResponse, error) {
	body, _ := json.Marshal(payload)
	url := fmt.Sprintf("%s/api/v1/sessions/%s/dispatch/", c.BaseURL, sessionID)
	req, _ := http.NewRequest("POST", url, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res DispatchResponse
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

func (c *Client) PublishModule(payload ModulePublishPayload) (*ModuleRecord, error) {
	body, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", c.BaseURL+"/api/v1/modules/", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res ModuleRecord
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

func (c *Client) GetModule(moduleID string) (*ModuleRecord, error) {
	req, _ := http.NewRequest("GET", fmt.Sprintf("%s/api/v1/modules/%s/", c.BaseURL, moduleID), nil)
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res ModuleRecord
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

func (c *Client) ListModules(search string) ([]ModuleSummary, error) {
	url := c.BaseURL + "/api/v1/modules/"
	if search != "" {
		url += "?search=" + search
	}
	req, _ := http.NewRequest("GET", url, nil)
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res []ModuleSummary
	json.NewDecoder(resp.Body).Decode(&res)
	return res, nil
}

func (c *Client) RetireModule(moduleID, version, reason string) (*RetireReceipt, error) {
	body, _ := json.Marshal(map[string]string{"reason": reason})
	url := fmt.Sprintf("%s/api/v1/modules/%s/versions/%s/retire/", c.BaseURL, moduleID, version)
	req, _ := http.NewRequest("POST", url, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res RetireReceipt
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}

func (c *Client) ListRuns(limit int) ([]RunAnalytics, error) {
	url := fmt.Sprintf("%s/api/v1/analytics/runs/?limit=%d", c.BaseURL, limit)
	req, _ := http.NewRequest("GET", url, nil)
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res []RunAnalytics
	json.NewDecoder(resp.Body).Decode(&res)
	return res, nil
}

func (c *Client) UploadStorage(payload StorageUploadRequest) (*StorageDescriptor, error) {
	body, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", c.BaseURL+"/api/v1/storage/upload/", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var res StorageDescriptor
	json.NewDecoder(resp.Body).Decode(&res)
	return &res, nil
}
