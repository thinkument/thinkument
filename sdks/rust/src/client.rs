use std::collections::HashMap;
use crate::types::*;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Client;

#[derive(Clone, Debug)]
pub struct ThinkClient {
    base_url: String,
    http: Client,
    headers: HeaderMap,
}

impl ThinkClient {
    pub fn local(port: u16) -> Self {
        Self::new(format!("http://127.0.0.1:{}", port), None)
    }

    pub fn connect(api_key: String, base_url: Option<String>) -> Self {
        let url = base_url.unwrap_or_else(|| "https://api.thinkument.com".to_string());
        Self::new(url, Some(api_key))
    }

    fn new(base_url: String, api_key: Option<String>) -> Self {
        let mut headers = HeaderMap::new();
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        if let Some(key) = api_key {
            let auth = format!("Bearer {}", key);
            if let Ok(val) = HeaderValue::from_str(&auth) {
                headers.insert(AUTHORIZATION, val);
            }
        }
        Self {
            base_url,
            http: Client::new(),
            headers,
        }
    }

    pub async fn health(&self) -> Result<HealthzResponse, reqwest::Error> {
        let url = format!("{}/healthz/", self.base_url);
        self.http.get(url).headers(self.headers.clone()).send().await?.json().await
    }

    pub async fn execute_op(&self, payload: &RelayPayload) -> Result<RelayResponse, reqwest::Error> {
        let url = format!("{}/api/v1/ops/execute/", self.base_url);
        self.http.post(url).headers(self.headers.clone()).json(payload).send().await?.json().await
    }

    pub async fn create_session(&self, payload: &SessionCreatePayload) -> Result<SessionCreateResponse, reqwest::Error> {
        let url = format!("{}/api/v1/sessions/", self.base_url);
        self.http.post(url).headers(self.headers.clone()).json(payload).send().await?.json().await
    }

    pub async fn dispatch(&self, session_id: &str, payload: &DispatchPayload) -> Result<DispatchResponse, reqwest::Error> {
        let url = format!("{}/api/v1/sessions/{}/dispatch/", self.base_url, session_id);
        self.http.post(url).headers(self.headers.clone()).json(payload).send().await?.json().await
    }

    pub async fn publish_module(&self, payload: &ModulePublishPayload) -> Result<ModuleRecord, reqwest::Error> {
        let url = format!("{}/api/v1/modules/", self.base_url);
        self.http.post(url).headers(self.headers.clone()).json(payload).send().await?.json().await
    }

    pub async fn get_module(&self, module_id: &str) -> Result<ModuleRecord, reqwest::Error> {
        let url = format!("{}/api/v1/modules/{}/", self.base_url, module_id);
        self.http.get(url).headers(self.headers.clone()).send().await?.json().await
    }

    pub async fn list_modules(&self, search: Option<&str>) -> Result<Vec<ModuleSummary>, reqwest::Error> {
        let mut url = format!("{}/api/v1/modules/", self.base_url);
        if let Some(q) = search {
            url.push_str(&format!("?search={}", q));
        }
        self.http.get(url).headers(self.headers.clone()).send().await?.json().await
    }

    pub async fn retire_module(&self, module_id: &str, version: &str, reason: Option<&str>) -> Result<RetireReceipt, reqwest::Error> {
        let url = format!("{}/api/v1/modules/{}/versions/{}/retire/", self.base_url, module_id, version);
        let mut body = HashMap::new();
        body.insert("reason", reason.unwrap_or("retired via sdk"));
        self.http.post(url).headers(self.headers.clone()).json(&body).send().await?.json().await
    }

    pub async fn list_runs(&self, limit: Option<usize>) -> Result<Vec<RunAnalytics>, reqwest::Error> {
        let url = format!("{}/api/v1/analytics/runs/?limit={}", self.base_url, limit.unwrap_or(25));
        self.http.get(url).headers(self.headers.clone()).send().await?.json().await
    }

    pub async fn upload_storage(&self, payload: &StorageUploadRequest) -> Result<StorageDescriptor, reqwest::Error> {
        let url = format!("{}/api/v1/storage/upload/", self.base_url);
        self.http.post(url).headers(self.headers.clone()).json(payload).send().await?.json().await
    }
}
