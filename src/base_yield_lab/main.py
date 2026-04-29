"""
main.py — Main bot loop.

Cycle flow:
1. Listener reads on-chain data -> BotState
2. Engine requests a decision -> LLMAction
3. If hold/alert: log and stop the cycle
4. If move_funds: firewall validates -> FirewallResult
5. If validation passes: executor runs the move
6. Update local history
7. Sleep until the next cycle
"""

import logging
import sys
import time

from config import (
    POLL_INTERVAL_SECONDS,
    COOLDOWN_AFTER_ERROR,
    PAPER_TRADING,
    PUBLIC_ADDRESS,
    BASE_RPC_URL,
)
from state import (
    load_history,
    record_move,
    record_error,
    clear_errors,
)
from listener import build_state
from engine import get_decision
from firewall import validate_action
from executor import execute_action

logger = logging.getLogger("bot")


def setup_logging():
    """Configure logging for console and file output."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    file_handler = logging.FileHandler("bot.log")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def run_cycle() -> None:
    """Run a full bot cycle. Useful on its own during testing."""
    logger.info("=" * 60)
    logger.info("START OF CYCLE")
    logger.info("=" * 60)

    state = build_state()

    logger.info(
        "Aave: %.4f%% APY, %.2f USDC | Compound: %.4f%% APY, %.2f USDC",
        state.aave.current_apy_pct,
        state.aave.deposited_usdc,
        state.compound.current_apy_pct,
        state.compound.deposited_usdc,
    )
    logger.info(
        "Wallet: %.2f USDC, %.6f ETH | Gas: %.4f gwei ($%.4f)",
        state.wallet.usdc_balance,
        state.wallet.eth_balance,
        state.network.gas_price_gwei,
        state.network.gas_cost_estimate_usd,
    )

    action = get_decision(state)

    if action.action == "hold":
        logger.info("DECISION: HOLD - %s", action.reason)
        return

    if action.action == "alert":
        logger.warning("ALERT [%s]: %s", action.severity, action.message)
        return

    logger.info(
        "DECISION: MOVE - %s -> %s | %s USDC | %s",
        action.from_protocol,
        action.to_protocol,
        action.amount_usdc,
        action.reason,
    )

    if action.amount_usdc == -1:
        if action.from_protocol == "aave_v3":
            action.amount_usdc = state.aave.deposited_usdc
        elif action.from_protocol == "compound_iii":
            action.amount_usdc = state.compound.deposited_usdc
        elif action.from_protocol == "wallet":
            action.amount_usdc = state.wallet.usdc_balance
        logger.info("Resolved amount: %.2f USDC", action.amount_usdc)

    firewall_result = validate_action(action, state)
    if not firewall_result.passed:
        logger.warning("FIREWALL BLOCKED: %s", firewall_result.failed_reasons)
        return

    result = execute_action(action)

    if result["status"] in ("success", "paper"):
        logger.info("EXECUTION: %s", result["status"].upper())
        gas_cost = state.network.gas_cost_estimate_usd
        history = load_history()
        record_move(history, f"{action.from_protocol}->{action.to_protocol}", gas_cost)
    else:
        logger.error("EXECUTION FAILED: %s", result)
        history = load_history()
        record_error(history)

    logger.info("END OF CYCLE")


def main():
    """Run run_cycle() forever with the configured polling interval."""
    setup_logging()

    mode = "PAPER TRADING" if PAPER_TRADING else "LIVE TRADING"
    logger.info("Bot starting in mode: %s", mode)
    logger.info("Wallet: %s", PUBLIC_ADDRESS)
    logger.info("RPC: %s...", BASE_RPC_URL[:50])
    logger.info("Polling interval: %ss", POLL_INTERVAL_SECONDS)
    logger.info("")

    history = load_history()
    if history.consecutive_errors > 0:
        logger.warning(
            "Loaded history with %s consecutive errors",
            history.consecutive_errors,
        )
    clear_errors(history)

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (Ctrl+C)")
            break
        except Exception as e:
            logger.error("CYCLE ERROR: %s", e, exc_info=True)
            history = load_history()
            history = record_error(history)

            if history.consecutive_errors >= 3:
                logger.error(
                    "3+ consecutive errors. Cooling down for %ss",
                    COOLDOWN_AFTER_ERROR,
                )
                time.sleep(COOLDOWN_AFTER_ERROR)
            else:
                time.sleep(30)
            continue

        logger.info("Next cycle in %ss...", POLL_INTERVAL_SECONDS)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
