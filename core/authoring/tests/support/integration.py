"""Service-only helpers for collection HTTP and browser sheets."""
import json
import re
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.middleware.csrf import get_token
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from rest_framework.test import APIClient

from tests.public.PSMC_sessions.PSMC_sessions_reusable_test_demo import (
    STARTERS_URL, cleanup_live_sessions, demo_starter_payload_v1,
    register_PSMC_sessions_reusable_test_demo_app_v1, reset_demo_runtime_state_v1,
    session_ids_from_launches, starter_launch_url,
)

from django.test import override_settings

LOCAL_STATIC_STORAGES = {
    **settings.STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

UNTHROTTLED_STARTERS = {
    **settings.REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        **settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
        "starters": None,
    },
}


DEFAULT_BROWSER_TIMEOUT_MS = 15000


def format_hai_mount_error(pack_id, *, page_errors, failed_requests, bad_responses, page_response, url):
    hints = []
    static_404s = [r for r in bad_responses if "404" in r and ("/static/" in r or ".js" in r or ".css" in r)]
    static_aborts = [r for r in failed_requests if "/static/" in r or ".js" in r or ".css" in r]
    failed_static = list(dict.fromkeys(static_404s + static_aborts))
    if failed_static:
        hints.append(
            "DIAGNOSIS: STATIC ASSET 404 OR LOAD FAILURE DETECTED.\n"
            f"  Missing / failed asset(s): {failed_static}\n"
            "  Likely cause: Static assets are out of date on the configured storage backend (e.g. after renaming files or directories).\n"
            "  Action required: Run `rav run collectstatic_tkt` to collect/sync static assets to the configured storage backend."
        )
    if page_errors:
        hints.append(
            "DIAGNOSIS: BROWSER JAVASCRIPT EXCEPTION.\n"
            "  Console errors:\n    " + "\n    ".join(str(e) for e in page_errors)
        )
    server_errors = [r for r in bad_responses if any(r.startswith(code) or f" {code} " in r for code in ("500", "502", "503", "504"))]
    if server_errors or (getattr(page_response, "status", None) and page_response.status >= 500):
        hints.append(
            "DIAGNOSIS: SERVER 5xx ERROR.\n"
            f"  Server errors: {server_errors or getattr(page_response, 'status', None)}"
        )
    hint_block = ("\n\n" + "\n\n".join(hints) + "\n") if hints else ""
    return (
        f"HAI did not mount for {pack_id}.{hint_block}\n"
        f"Details:\n"
        f"  browser errors: {page_errors}\n"
        f"  failed requests: {failed_requests}\n"
        f"  bad responses: {bad_responses}\n"
        f"  page response status: {getattr(page_response, 'status', None)}\n"
        f"  URL: {url}"
    )


@override_settings(REST_FRAMEWORK=UNTHROTTLED_STARTERS)
class CreativeLiveServerCase(StaticLiveServerTestCase):
    databases = {"default", "economics", "storagics", "eps_log"}
    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        self.http = requests.Session()
        self.addCleanup(self.http.close)
        self.live_sessions = set()
        self.addCleanup(self.cleanup_runtime)
        register_PSMC_sessions_reusable_test_demo_app_v1()
        reset_demo_runtime_state_v1()
        owner = get_user_model().objects.create_user(username="creative-owner", password="test-password")
        client = APIClient()
        client.force_login(owner)
        session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
        if session_cookie is None:
            raise AssertionError("force_login did not create a Django session cookie")

        self.browser_session_cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": session_cookie.value,
            "url": self.live_server_url,
            # The Django live test server is HTTP, so its browser session cookie
            # must be usable on localhost even when deployed cookies are secure.
            "secure": False,
        }
        self.http.cookies.set(
            settings.SESSION_COOKIE_NAME,
            session_cookie.value,
        )
        csrf_request = HttpRequest()
        token = get_token(csrf_request)
        self.http.cookies.set(
            settings.CSRF_COOKIE_NAME,
            csrf_request.META["CSRF_COOKIE"],
        )
        self.http.headers["X-CSRFToken"] = token

    def cleanup_runtime(self):
        cleanup_live_sessions(*self.live_sessions)
        reset_demo_runtime_state_v1()

    def get_http(self, path):
        response = self.http.get(urljoin(self.live_server_url + "/", path), timeout=15)
        self.assertEqual(response.status_code, 200, response.text[:1000])
        return response

    def launch_pack(self, pack_id):
        from authoring_PSMC.template_thinkprogram_SM_app_packs import with_app_pack
        payload = demo_starter_payload_v1()
        payload["session_metadata"] = with_app_pack(payload["session_metadata"], app_pack=pack_id)
        return self.launch_payload(payload)

    def launch_tape(self, tape):
        from copy import deepcopy
        payload = demo_starter_payload_v1(manifest=tape["P"],
            initial_parameter_overrides=tape["C"], chainreaction_enabled=False, events_queue_length=128)
        public_ui = deepcopy(payload["session_metadata"].get("public_ui", {}))
        sm = deepcopy(tape["SM"])
        if "public_ui" in sm:
            if "polling" in public_ui and "polling" not in sm["public_ui"]:
                sm["public_ui"]["polling"] = public_ui["polling"]
            payload["session_metadata"] = sm
        else:
            payload["session_metadata"] = sm
            payload["session_metadata"]["public_ui"] = public_ui
        return self.launch_payload(payload)

    def launch_payload(self, payload):
        response = self.http.post(self.live_server_url + STARTERS_URL, json=payload, timeout=15)
        self.assertEqual(response.status_code, 201, response.text)
        response = self.http.post(self.live_server_url + starter_launch_url(response.json()["id"]),
                                  json={"public_view_role": "maker"}, timeout=15)
        self.assertEqual(response.status_code, 200, response.text)
        launch = response.json()
        self.live_sessions.update(session_ids_from_launches(launch))
        return launch

    def boot_hai_page(self, browser, page_path, *, pack_id, timeout_ms=DEFAULT_BROWSER_TIMEOUT_MS):
        page = browser.new_page()
        page.set_default_timeout(timeout_ms)
        page_errors = []
        failed_requests = []
        bad_responses = []
        page.on('pageerror', lambda error: page_errors.append(str(error)))
        page.on('requestfailed', lambda req: failed_requests.append(f'{req.url}: {req.failure}'))
        page.on('response', lambda resp: bad_responses.append(f'{resp.status} {resp.url}') if resp.status >= 400 else None)
        page_response = page.goto(self.live_server_url + page_path)
        try:
            page.locator('[data-thinkument-hai]').wait_for(timeout=timeout_ms)
        except Exception as exc:
            raise AssertionError(
                format_hai_mount_error(
                    pack_id,
                    page_errors=page_errors,
                    failed_requests=failed_requests,
                    bad_responses=bad_responses,
                    page_response=page_response,
                    url=page.url,
                )
            ) from exc
        return page



def boot_json(html, config_id):
    match = re.search(r'<script[^>]*id="' + re.escape(config_id) + r'"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise AssertionError(f"missing boot config {config_id!r}")
    return json.loads(match.group(1))
