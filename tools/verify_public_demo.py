#!/usr/bin/env python3
"""Docker-only health/parity and independent HTTP/HTTPS NAT evidence capture."""

import argparse
import http.client
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def fetch(url, host=None):
    headers = {"Accept": "application/json", "User-Agent": "curl/8.10.1"}
    if host:
        headers["Host"] = host
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=20
    ) as response:
        return json.load(response)


def main():
    if not Path("/.dockerenv").exists():
        raise SystemExit("Run this verifier inside Docker.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-id", required=True)
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]+", args.check_id):
        raise SystemExit("Invalid check-host request ID.")
    private = fetch(
        "http://host.docker.internal:18107/demo/v1/health", "localhost:18107"
    )
    edge_url = (
        "https://sfuai.ca:18087/demo/v1/health"
        if args.tls
        else "http://host.docker.internal:18087/demo/v1/health"
    )
    edge = fetch(edge_url, "sfuai.ca:18087")
    assert private["status"] == edge["status"] == "ok"
    assert private["provenance"] == edge["provenance"]
    expected = {
        "gpkg_sha256": "da44fc5683169c53efcc0b2080cea4419ff40833dad8fb47c8b76051ec656eac",
        "graph_sha256": "93c2ff2994e6e564adecae3506175f2c0047948e1d84e44045d2c70267071d46",
        "stats_sha256": "9a678cb044f6c76d3abf61bfa57a0e56fafb00efb0d181f5a7906492b23a6cfb",
    }
    for key, value in expected.items():
        assert edge["provenance"][key] == value, key
    try:
        fetch(edge_url, "bad.invalid")
    except (http.client.RemoteDisconnected, ConnectionResetError):
        rejected = True
    else:
        raise AssertionError("Unexpected response to invalid Host.")
    redirect = None
    if args.tls:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        request = urllib.request.Request(
            "http://host.docker.internal:18087/demo/v1/health?tls=1",
            headers={"Host": "sfuai.ca:18087"},
        )
        try:
            urllib.request.build_opener(NoRedirect()).open(request, timeout=20)
        except urllib.error.HTTPError as error:
            assert error.code == 307
            redirect = error.headers["Location"]
            assert redirect == "https://sfuai.ca:8017/demo/v1/health?tls=1"
        else:
            raise AssertionError("Plain HTTP must redirect to the HTTPS public origin.")
    outside = fetch(f"https://check-host.net/check-result/{args.check_id}")
    assert len(outside) >= 3, "Three independent nodes required."
    for node, rows in outside.items():
        assert rows and all(
            row[0] == 1 and str(row[3]) == "200" and row[4] == "173.180.31.84"
            for row in rows
        ), (node, rows)
    report = {
        "status": "passed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "public_url": f"{'https' if args.tls else 'http'}://sfuai.ca:8017/",
        "router_target": "192.168.1.80:18087",
        "private_health": private,
        "edge_health": edge,
        "invalid_host_rejected": rejected,
        "tls_certificate_verified": args.tls,
        "http_redirect": redirect,
        "outside_request_id": args.check_id,
        "outside_results": outside,
    }
    output = Path("/workspace/build/dt030-public" if args.tls else "/workspace/build/dt028-public")
    output.mkdir(parents=True, exist_ok=True)
    (output / "network-evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "public_url": report["public_url"]}))


if __name__ == "__main__":
    main()
