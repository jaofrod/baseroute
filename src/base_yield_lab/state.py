"""
state.py — Data structures and local bot persistence.

Dataclasses are used instead of loose dicts so attribute mistakes fail
immediately instead of degrading silently at runtime.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict


@dataclass
class NetworkState:
    """Snapshot of Base network conditions."""

    chain_id: int = 0
    gas_price_gwei: float = 0.0
    gas_cost_estimate_usd: float = 0.0
    block_number: int = 0


@dataclass
class WalletState:
    """Current bot wallet balances."""

    address: str = ""
    usdc_balance: float = 0.0
    eth_balance: float = 0.0


@dataclass
class ProtocolPosition:
    """Bot position inside a protocol."""

    deposited_usdc: float = 0.0
    current_apy_pct: float = 0.0


@dataclass
class ComputedState:
    """Values derived from raw chain reads."""

    total_capital_usdc: float = 0.0
    best_protocol: str = ""
    best_apy_pct: float = 0.0
    current_protocol: str = ""
    current_apy_pct: float = 0.0
    apy_diff_pct: float = 0.0
    should_consider_move: bool = False
    estimated_annual_gain_if_move: float = 0.0
    estimated_gas_cost_for_move: float = 0.0


@dataclass
class HistoryState:
    """Recent action history used for cooldown and error tracking."""

    last_move_timestamp: float = 0.0
    last_move_action: str = ""
    total_moves_24h: int = 0
    total_gas_spent_24h_usd: float = 0.0
    consecutive_errors: int = 0


@dataclass
class BotState:
    """Full bot state at a given point in time."""

    timestamp: float = 0.0
    network: NetworkState = field(default_factory=NetworkState)
    wallet: WalletState = field(default_factory=WalletState)
    aave: ProtocolPosition = field(default_factory=ProtocolPosition)
    compound: ProtocolPosition = field(default_factory=ProtocolPosition)
    computed: ComputedState = field(default_factory=ComputedState)
    history: HistoryState = field(default_factory=HistoryState)


@dataclass
class LLMAction:
    """Decision returned by the LLM."""

    action: str = "hold"
    from_protocol: str = ""
    to_protocol: str = ""
    amount_usdc: float = 0.0
    reason: str = ""
    severity: str = ""
    message: str = ""


@dataclass
class FirewallResult:
    """Result of deterministic firewall validation."""

    passed: bool = True
    checks: dict = field(default_factory=dict)
    failed_reasons: list = field(default_factory=list)


HISTORY_FILE = "bot_history.json"


def load_history() -> HistoryState:
    """Load history from disk. Return an empty state if missing."""
    if not os.path.exists(HISTORY_FILE):
        return HistoryState()
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        return HistoryState(
            last_move_timestamp=data.get("last_move_timestamp", 0.0),
            last_move_action=data.get("last_move_action", ""),
            total_moves_24h=data.get("total_moves_24h", 0),
            total_gas_spent_24h_usd=data.get("total_gas_spent_24h_usd", 0.0),
            consecutive_errors=data.get("consecutive_errors", 0),
        )
    except (json.JSONDecodeError, KeyError):
        return HistoryState()


def save_history(history: HistoryState) -> None:
    """Persist history to disk."""
    with open(HISTORY_FILE, "w") as f:
        json.dump(asdict(history), f, indent=2)


def record_move(history: HistoryState, action: str, gas_cost_usd: float) -> HistoryState:
    """Record a successful move."""
    now = time.time()

    if now - history.last_move_timestamp > 86400:
        moves_24h = 1
        gas_24h = gas_cost_usd
    else:
        moves_24h = history.total_moves_24h + 1
        gas_24h = history.total_gas_spent_24h_usd + gas_cost_usd

    updated = HistoryState(
        last_move_timestamp=now,
        last_move_action=action,
        total_moves_24h=moves_24h,
        total_gas_spent_24h_usd=gas_24h,
        consecutive_errors=0,
    )
    save_history(updated)
    return updated


def record_error(history: HistoryState) -> HistoryState:
    """Record a consecutive error."""
    updated = HistoryState(
        last_move_timestamp=history.last_move_timestamp,
        last_move_action=history.last_move_action,
        total_moves_24h=history.total_moves_24h,
        total_gas_spent_24h_usd=history.total_gas_spent_24h_usd,
        consecutive_errors=history.consecutive_errors + 1,
    )
    save_history(updated)
    return updated


def clear_errors(history: HistoryState) -> HistoryState:
    """Reset the consecutive error counter."""
    updated = HistoryState(
        last_move_timestamp=history.last_move_timestamp,
        last_move_action=history.last_move_action,
        total_moves_24h=history.total_moves_24h,
        total_gas_spent_24h_usd=history.total_gas_spent_24h_usd,
        consecutive_errors=0,
    )
    save_history(updated)
    return updated
