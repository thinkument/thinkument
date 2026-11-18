"""Thinkument Unified CLI — Steve Jobsian Ergonomics, Zero Bloat, Instant Startup (<10ms)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from thinkument.client import ThinkClient
from thinkument.daemon.interceptor import (
    create_ollama_interceptor,
    create_webhook_interceptor,
    default_mock_interceptor,
    load_interceptor_from_file,
)
from thinkument.sdk.catalogue import CatalogueNamespace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thinkument",
        description="Thinkument CLI & Developer SDK — Local Studio & Sovereign Cloud Client",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. dev
    dev_parser = subparsers.add_parser("dev", help="Start local development studio daemon")
    dev_parser.add_argument("program", nargs="?", help="Optional path to program JSON manifest to launch")
    dev_parser.add_argument("--port", type=int, default=5052, help="Port to bind daemon (default: 5052)")
    dev_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    dev_parser.add_argument("--mode", choices=["mock", "relay"], default="mock", help="Execution mode (default: mock)")
    dev_parser.add_argument("--mocks-file", help="Path to Python file exporting custom mock interceptor function")
    dev_parser.add_argument("--vendor-ollama", help="Ollama endpoint URL (e.g. http://localhost:11434)")
    dev_parser.add_argument("--vendor-proxy", help="Language-agnostic webhook proxy URL (e.g. http://localhost:8080/mock)")

    # 2. validate
    val_parser = subparsers.add_parser("validate", help="Validate widget or program JSON manifest offline (<1ms)")
    val_parser.add_argument("manifest", help="Path to JSON manifest to validate")

    # 3. publish
    pub_parser = subparsers.add_parser("publish", help="Publish validated widget manifest to Sovereign Cloud Catalogue")
    pub_parser.add_argument("manifest", help="Path to JSON widget manifest to publish")
    pub_parser.add_argument("--api-key", help="Thinkument API Key (or set THINKUMENT_API_KEY)")
    pub_parser.add_argument("--endpoint", default="https://api.thinkument.com", help="Cloud API endpoint")

    # 4. run
    run_parser = subparsers.add_parser("run", help="Execute headless program black-box run")
    run_parser.add_argument("program", help="Path to program JSON manifest")
    run_parser.add_argument("--context", "-c", help="Path to context/parameters JSON file")
    run_parser.add_argument("--timeout", type=int, default=60, help="Execution timeout in seconds")
    run_parser.add_argument("--cloud", action="store_true", help="Execute on Thinkument Sovereign Cloud")
    run_parser.add_argument("--api-key", help="Thinkument API Key (required if --cloud)")
    run_parser.add_argument("--endpoint", default="https://api.thinkument.com", help="Cloud API endpoint")

    # 5. balance
    bal_parser = subparsers.add_parser("balance", help="Inspect prepaid microcredits wallet balance")
    bal_parser.add_argument("--api-key", help="Thinkument API Key (or set THINKUMENT_API_KEY)")
    bal_parser.add_argument("--endpoint", default="https://api.thinkument.com", help="Cloud API endpoint")

    return parser


def cmd_dev(args: argparse.Namespace) -> int:
    from thinkument.daemon.runner import LocalSessionRunner
    from thinkument.daemon.server import create_daemon_app

    interceptor = default_mock_interceptor
    if args.mocks_file:
        interceptor = load_interceptor_from_file(args.mocks_file)
    elif args.vendor_ollama:
        interceptor = create_ollama_interceptor(endpoint=args.vendor_ollama)
    elif args.vendor_proxy:
        interceptor = create_webhook_interceptor(target_url=args.vendor_proxy)

    runner = LocalSessionRunner(default_interceptor=interceptor)
    app = create_daemon_app(
        runner=runner,
        mode=args.mode,
        mocks_file=args.mocks_file,
        vendor_ollama=args.vendor_ollama,
        vendor_proxy=args.vendor_proxy,
    )

    print(f"\n✨ Thinkument Local Studio running on http://{args.host}:{args.port}")
    print(f"   Mode: {args.mode.upper()} ($0.00, 100% offline)")
    if args.mocks_file:
        print(f"   Mock Handler: {args.mocks_file}")
    elif args.vendor_ollama:
        print(f"   Air-Gapped AI: Ollama at {args.vendor_ollama}")
    elif args.vendor_proxy:
        print(f"   Vendor Webhook: {args.vendor_proxy}")

    if args.program:
        if os.path.exists(args.program):
            with open(args.program, "r", encoding="utf-8") as f:
                prog_data = json.load(f)
            created = runner.create_session(
                P=prog_data.get("P") or prog_data,
                SM=prog_data.get("SM"),
                C=prog_data.get("C"),
                base_url=f"http://{args.host}:{args.port}",
            )
            print(f"\n🚀 Session Launched: {created['session_id']}")
            print(f"   Studio URL: {created['selected']['url']}")
        else:
            print(f"⚠️ Program file not found: {args.program}", file=sys.stderr)

    print("\n[Ctrl+C to stop]\n")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cat = CatalogueNamespace(base_url="http://localhost:5052")
    report = cat.validate(args.manifest)
    if report.valid:
        print(f"✅ Valid Thinkument {report.kind}: {args.manifest}")
        if report.title:
            print(f"   Title: {report.title}")
        return 0
    else:
        print(f"❌ Invalid manifest: {args.manifest}", file=sys.stderr)
        for err in report.errors:
            print(f"   - {err}", file=sys.stderr)
        return 1


def cmd_publish(args: argparse.Namespace) -> int:
    client = ThinkClient.connect(api_key=args.api_key, endpoint=args.endpoint)
    try:
        receipt = client.catalogue.publish_widget(args.manifest)
        print(f"🚀 Successfully published widget to Thinkument Catalogue!")
        print(json.dumps(receipt, indent=2))
        return 0
    except Exception as exc:
        print(f"❌ Publish failed: {exc}", file=sys.stderr)
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    with open(args.program, "r", encoding="utf-8") as f:
        prog_data = json.load(f)

    P = prog_data.get("P") or prog_data
    SM = prog_data.get("SM")
    C = prog_data.get("C") or {}

    if args.context:
        with open(args.context, "r", encoding="utf-8") as f:
            c_override = json.load(f)
        C.update(c_override)

    if args.cloud:
        client = ThinkClient.connect(api_key=args.api_key, endpoint=args.endpoint)
    else:
        # In-process sovereign run
        from thinkument.daemon.runner import LocalSessionRunner
        runner = LocalSessionRunner()
        res = runner.run_blackbox(P=P, C=C, SM=SM, timeout_seconds=args.timeout)
        print(json.dumps(res, indent=2))
        return 0

    job = client.blackbox.run(P=P, C=C, SM=SM, timeout_seconds=args.timeout)
    res = job.wait()
    print(json.dumps({
        "ok": res.ok,
        "status": res.status,
        "outputs": res.outputs,
        "canonical_context": res.canonical_context,
    }, indent=2))
    return 0 if res.ok else 1


def cmd_balance(args: argparse.Namespace) -> int:
    client = ThinkClient.connect(api_key=args.api_key, endpoint=args.endpoint)
    try:
        bal = client.economics.get_balance()
        print(f"💳 Available Balance: {bal.available_credits:,} {bal.currency}")
        return 0
    except Exception as exc:
        print(f"❌ Balance query failed: {exc}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "dev":
        return cmd_dev(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "publish":
        return cmd_publish(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "balance":
        return cmd_balance(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
