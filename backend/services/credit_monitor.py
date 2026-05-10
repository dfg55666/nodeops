"""
Credit monitor — checks if an account's credits are exhausted.
Uses multiple signals for reliable detection.
"""
import logging
from typing import Any
from backend.services import nodeops_client as noc
from backend.services import account_pool

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def check_credits(auth_token: str, account_id: str | None = None) -> dict:
    """Check credit status for an account.

    Returns:
        {
            "exhausted": bool,
            "credits_remaining": float | None,
            "usage": dict | None,
            "error": str | None,
        }
    """
    result = {
        "exhausted": False,
        "credits_remaining": None,
        "usage": None,
        "error": None,
    }

    # Signal 1: Usage API (control plane)
    try:
        usage_payload = await noc.get_usage(auth_token)
        usage = _as_dict(usage_payload)
        usage_data = _as_dict(usage.get("data")) if "data" in usage else usage
        result["usage"] = usage_payload
        remaining = (
            usage_data.get("creditsRemaining")
            or usage_data.get("remaining")
            or usage_data.get("credits")
            or usage_data.get("available")
        )
        remaining_num = _parse_number(remaining)
        if remaining_num is not None:
            result["credits_remaining"] = remaining_num
            if remaining_num <= 0:
                result["exhausted"] = True
                logger.info(f"Credits exhausted (usage API): remaining={remaining}")
    except Exception as e:
        logger.warning(f"Usage API check failed: {e}")

    # Signal 2: Credits API (may have intermittent 500s)
    if not result["exhausted"]:
        try:
            credits_payload = await noc.get_credits(auth_token)
            credits_data = _as_dict(credits_payload)
            credits_data = _as_dict(credits_data.get("data")) if "data" in credits_data else credits_data
            available = (
                credits_data.get("available")
                or credits_data.get("balance")
                or credits_data.get("credits")
                or credits_data.get("amount")
                or credits_data.get("remaining")
            )
            available_num = _parse_number(available)
            if available_num is not None:
                result["credits_remaining"] = available_num
                if available_num <= 0:
                    result["exhausted"] = True
                    logger.info(f"Credits exhausted (credits API): available={available}")
        except Exception as e:
            logger.warning(f"Credits API check failed: {e}")

    # Update cached credit balance
    if account_id and result["credits_remaining"] is not None:
        account_pool.update_credits(account_id, result["credits_remaining"])

    return result


def is_credit_error(error_response: dict | str) -> bool:
    """Check if an API error response indicates credit exhaustion.

    This is Signal 3 — called by the task engine when a send_message
    or other API call fails.
    """
    if isinstance(error_response, str):
        error_lower = error_response.lower()
        return any(kw in error_lower for kw in [
            "credit", "quota", "limit", "insufficient",
            "exceeded", "no remaining", "exhausted",
            "not enough", "user is suspended", "balance",
        ])

    if isinstance(error_response, dict):
        error_msg = str(error_response.get("error", "")).lower()
        error_code = str(error_response.get("code", "")).lower()
        return any(kw in error_msg or kw in error_code for kw in [
            "credit", "quota", "limit", "insufficient",
        ])

    return False
