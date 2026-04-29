"""
firewall.py — Deterministic validation before execution.

The firewall is the last line of defense before any transaction is signed.
All checks run every time so logs show the full validation picture.
"""

import logging
import time

from config import (
    APPROVED_PROTOCOLS,
    APPROVED_TOKENS,
    MAX_SINGLE_TX_USDC,
    MAX_GAS_COST_USD,
    MAX_GAS_PRICE_GWEI,
    MIN_TIME_BETWEEN_MOVES,
    KNOWN_CONTRACTS,
    AAVE_POOL_ADDRESS,
    COMPOUND_COMET_ADDRESS,
)
from state import BotState, LLMAction, FirewallResult

logger = logging.getLogger(__name__)


def _get_target_contract(protocol: str) -> str:
    """Map protocol name to target contract address."""
    mapping = {
        "aave_v3": AAVE_POOL_ADDRESS,
        "compound_iii": COMPOUND_COMET_ADDRESS,
    }
    return mapping.get(protocol, "")


def _get_source_balance(action: LLMAction, state: BotState) -> float:
    """Return the available balance for the source location."""
    if action.from_protocol == "aave_v3":
        return state.aave.deposited_usdc
    if action.from_protocol == "compound_iii":
        return state.compound.deposited_usdc
    if action.from_protocol == "wallet":
        return state.wallet.usdc_balance
    return 0.0


def _estimate_annual_gain(action: LLMAction, state: BotState) -> float:
    """Estimate annual USD gain from the proposed move."""
    if action.to_protocol == "aave_v3":
        to_apy = state.aave.current_apy_pct
    elif action.to_protocol == "compound_iii":
        to_apy = state.compound.current_apy_pct
    else:
        return 0.0

    if action.from_protocol == "aave_v3":
        from_apy = state.aave.current_apy_pct
    elif action.from_protocol == "compound_iii":
        from_apy = state.compound.current_apy_pct
    else:
        from_apy = 0.0

    amount = action.amount_usdc
    if amount <= 0:
        amount = _get_source_balance(action, state)

    apy_diff = to_apy - from_apy
    return (apy_diff / 100) * amount


def validate_action(action: LLMAction, state: BotState) -> FirewallResult:
    """Validate an LLM action against deterministic rules."""
    if action.action in ("hold", "alert"):
        return FirewallResult(
            passed=True,
            checks={"action_type": True},
            failed_reasons=[],
        )

    amount = action.amount_usdc
    if amount == -1:
        amount = _get_source_balance(action, state)

    from_approved = (
        action.from_protocol in APPROVED_PROTOCOLS or action.from_protocol == "wallet"
    )
    to_approved = action.to_protocol in APPROVED_PROTOCOLS
    protocol_approved = from_approved and to_approved

    token_approved = "USDC" in APPROVED_TOKENS
    amount_within_limit = amount <= MAX_SINGLE_TX_USDC
    gas_acceptable = state.network.gas_cost_estimate_usd <= MAX_GAS_COST_USD
    gas_price_ok = state.network.gas_price_gwei <= MAX_GAS_PRICE_GWEI

    time_since_last = time.time() - state.history.last_move_timestamp
    cooldown_ok = time_since_last >= MIN_TIME_BETWEEN_MOVES

    annual_gain = _estimate_annual_gain(action, state)
    gas_cost = state.network.gas_cost_estimate_usd
    profitable = annual_gain > gas_cost

    source_balance = _get_source_balance(action, state)
    sufficient_balance = amount <= source_balance

    target_contract = _get_target_contract(action.to_protocol)
    contract_verified = target_contract in KNOWN_CONTRACTS

    checks = {
        "protocol_approved": protocol_approved,
        "token_approved": token_approved,
        "amount_within_limit": amount_within_limit,
        "gas_acceptable": gas_acceptable,
        "gas_price_ok": gas_price_ok,
        "cooldown_ok": cooldown_ok,
        "profitable": profitable,
        "sufficient_balance": sufficient_balance,
        "contract_verified": contract_verified,
    }

    failed = [name for name, passed in checks.items() if not passed]
    result = FirewallResult(
        passed=len(failed) == 0,
        checks=checks,
        failed_reasons=failed,
    )

    if result.passed:
        logger.info("FIREWALL: PASSED - all 9 checks OK")
    else:
        logger.warning("FIREWALL: BLOCKED - failed checks: %s", failed)
        for name in failed:
            if name == "protocol_approved":
                logger.warning(
                    "  - Unapproved protocol: from=%s to=%s",
                    action.from_protocol,
                    action.to_protocol,
                )
            elif name == "amount_within_limit":
                logger.warning(
                    "  - Amount %.2f USDC exceeds limit of %.2f",
                    amount,
                    MAX_SINGLE_TX_USDC,
                )
            elif name == "gas_acceptable":
                logger.warning(
                    "  - Gas cost $%.4f exceeds limit of $%.4f",
                    gas_cost,
                    MAX_GAS_COST_USD,
                )
            elif name == "gas_price_ok":
                logger.warning(
                    "  - Gas price %.4f gwei exceeds %.4f",
                    state.network.gas_price_gwei,
                    MAX_GAS_PRICE_GWEI,
                )
            elif name == "cooldown_ok":
                remaining = MIN_TIME_BETWEEN_MOVES - time_since_last
                logger.warning("  - Cooldown active: %.0fs remaining", remaining)
            elif name == "profitable":
                logger.warning(
                    "  - Not profitable: annual gain $%.4f <= gas $%.4f",
                    annual_gain,
                    gas_cost,
                )
            elif name == "sufficient_balance":
                logger.warning(
                    "  - Insufficient balance: %.2f < %.2f USDC",
                    source_balance,
                    amount,
                )
            elif name == "contract_verified":
                logger.warning("  - Unverified contract: %s", target_contract)

    return result
