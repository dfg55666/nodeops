#!/usr/bin/env python3
"""
NodeOps CreateOS add-credits replay template.

Usage:
  python auth/nodeops/replay_add_credits.py --token "<X_AUTH_TOKEN>" --credits 1
  python auth/nodeops/replay_add_credits.py --token "<X_AUTH_TOKEN>" --credits 5 --sku-id "<SKU_ID>"
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

import requests


API_CREATEOS = "https://api-createos.nodeops.network/v1"
API_VIBECODER = "https://stage-vibe-coder-api.nodeops.xyz/api/v1"
DEFAULT_SKU_ID = "00000000-0000-0000-0000-000000000007"


def _request_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    *,
    params: Dict[str, Any] | None = None,
    body: Dict[str, Any] | None = None,
    timeout_s: int = 30,
) -> requests.Response:
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=body,
        timeout=timeout_s,
    )
    return response


def _print_step(name: str, resp: requests.Response) -> None:
    print(f"\n[{name}] status={resp.status_code}")
    text = resp.text.strip()
    if not text:
        print("(empty response body)")
        return
    try:
        parsed = resp.json()
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    except Exception:
        print(text[:1200])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="X-Auth-Token")
    parser.add_argument("--credits", type=int, default=1, help="Credits to add")
    parser.add_argument("--sku-id", default=DEFAULT_SKU_ID, help="Credit SKU ID")
    parser.add_argument(
        "--payment-method",
        default="checkout",
        help="paymentMethod query for credit-conversion-rate",
    )
    parser.add_argument(
        "--referral-url",
        default="https://nodeops.network",
        help="ReferralURL header for credits/openrouter",
    )
    args = parser.parse_args()

    common_headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Auth-Token": args.token.strip(),
    }

    post_headers = {
        **common_headers,
        "Content-Type": "application/json",
        "ReferralURL": args.referral_url.strip(),
    }

    # 1) Fetch SKU
    r1 = _request_json(
        "GET",
        f"{API_CREATEOS}/skus/credit",
        common_headers,
    )
    _print_step("skus/credit", r1)

    # 2) Fetch conversion rate shown by UI
    r2 = _request_json(
        "GET",
        f"{API_CREATEOS}/payments/credit-conversion-rate",
        common_headers,
        params={
            "skuId": args.sku_id.strip(),
            "creditMultiplier": 1,
            "amount": args.credits,
            "paymentMethod": args.payment_method.strip(),
        },
    )
    _print_step("payments/credit-conversion-rate", r2)

    # 3) Execute Add Credits action
    r3 = _request_json(
        "POST",
        f"{API_CREATEOS}/credits/openrouter",
        post_headers,
        body={"credits": args.credits},
    )
    _print_step("credits/openrouter", r3)

    # 4) Refresh usage after credit add
    r4 = _request_json(
        "GET",
        f"{API_VIBECODER}/usage",
        common_headers,
    )
    _print_step("usage", r4)


if __name__ == "__main__":
    main()
