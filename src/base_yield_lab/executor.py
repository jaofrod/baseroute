"""
executor.py — Transaction execution layer.

Moves between protocols use three transactions:
1. Withdraw from the source protocol
2. Approve the destination protocol to spend wallet USDC
3. Supply into the destination protocol
"""

import logging

from web3 import Web3

from config import (
    BASE_RPC_URL,
    PRIVATE_KEY,
    PUBLIC_ADDRESS,
    CHAIN_ID,
    PAPER_TRADING,
    USDC_ADDRESS,
    AAVE_POOL_ADDRESS,
    COMPOUND_COMET_ADDRESS,
    USDC_ABI,
    AAVE_POOL_ABI,
    COMPOUND_COMET_ABI,
    USDC_DECIMALS,
    DEFAULT_GAS_LIMIT,
)
from state import LLMAction

logger = logging.getLogger(__name__)

w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
wallet = Web3.to_checksum_address(PUBLIC_ADDRESS)

usdc_contract = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI
)
aave_pool = w3.eth.contract(
    address=Web3.to_checksum_address(AAVE_POOL_ADDRESS), abi=AAVE_POOL_ABI
)
compound_comet = w3.eth.contract(
    address=Web3.to_checksum_address(COMPOUND_COMET_ADDRESS), abi=COMPOUND_COMET_ABI
)


def _usdc_to_raw(amount_float: float) -> int:
    """Convert float USDC to raw on-chain units."""
    return int(amount_float * (10**USDC_DECIMALS))


def _build_and_send_tx(contract_call, description: str) -> dict:
    """Build, sign, and optionally broadcast a transaction."""
    nonce = w3.eth.get_transaction_count(wallet)
    gas_price = w3.eth.gas_price
    max_priority_fee = w3.eth.max_priority_fee

    tx = contract_call.build_transaction(
        {
            "chainId": CHAIN_ID,
            "from": wallet,
            "nonce": nonce,
            "gas": DEFAULT_GAS_LIMIT,
            "maxFeePerGas": gas_price + max_priority_fee,
            "maxPriorityFeePerGas": max_priority_fee,
        }
    )

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)

    if PAPER_TRADING:
        logger.info("[PAPER] %s - transaction built and signed (not sent)", description)
        logger.info(
            "[PAPER]   nonce=%s, gas=%s, gasPrice=%s",
            nonce,
            DEFAULT_GAS_LIMIT,
            gas_price,
        )
        return {
            "status": "paper",
            "description": description,
            "nonce": nonce,
            "tx_hash": "0x_paper_" + description.replace(" ", "_")[:20],
        }

    logger.info("Sending transaction: %s...", description)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = w3.to_hex(tx_hash)
    logger.info("Transaction sent: %s", tx_hash_hex)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] == 1:
        logger.info(
            "Transaction confirmed: %s (block %s)",
            tx_hash_hex,
            receipt["blockNumber"],
        )
        return {
            "status": "success",
            "description": description,
            "tx_hash": tx_hash_hex,
            "block": receipt["blockNumber"],
            "gas_used": receipt["gasUsed"],
        }

    logger.error("Transaction reverted: %s", tx_hash_hex)
    return {
        "status": "reverted",
        "description": description,
        "tx_hash": tx_hash_hex,
    }


def _withdraw_from_aave(amount_raw: int) -> dict:
    """Withdraw USDC from Aave V3."""
    usdc = Web3.to_checksum_address(USDC_ADDRESS)
    call = aave_pool.functions.withdraw(usdc, amount_raw, wallet)
    return _build_and_send_tx(call, f"withdraw {amount_raw} USDC from Aave")


def _withdraw_from_compound(amount_raw: int) -> dict:
    """Withdraw USDC from Compound III."""
    usdc = Web3.to_checksum_address(USDC_ADDRESS)
    call = compound_comet.functions.withdraw(usdc, amount_raw)
    return _build_and_send_tx(call, f"withdraw {amount_raw} USDC from Compound")


def _approve_usdc(spender_address: str, amount_raw: int) -> dict:
    """Approve a contract to spend wallet USDC."""
    spender = Web3.to_checksum_address(spender_address)
    call = usdc_contract.functions.approve(spender, amount_raw)
    return _build_and_send_tx(
        call, f"approve {amount_raw} USDC for {spender_address[:10]}..."
    )


def _supply_to_aave(amount_raw: int) -> dict:
    """Deposit USDC into Aave V3."""
    usdc = Web3.to_checksum_address(USDC_ADDRESS)
    call = aave_pool.functions.supply(usdc, amount_raw, wallet, 0)
    return _build_and_send_tx(call, f"supply {amount_raw} USDC to Aave")


def _supply_to_compound(amount_raw: int) -> dict:
    """Deposit USDC into Compound III."""
    usdc = Web3.to_checksum_address(USDC_ADDRESS)
    call = compound_comet.functions.supply(usdc, amount_raw)
    return _build_and_send_tx(call, f"supply {amount_raw} USDC to Compound")


def execute_action(action: LLMAction) -> dict:
    """Execute a fund movement action."""
    if action.action != "move_funds":
        return {"status": "skipped", "reason": f"action is {action.action}, not move_funds"}

    amount = action.amount_usdc
    if amount <= 0:
        return {
            "status": "error",
            "reason": "amount must be > 0 (resolve -1 before calling executor)",
        }

    amount_raw = _usdc_to_raw(amount)
    results = []

    mode = "PAPER" if PAPER_TRADING else "LIVE"
    logger.info(
        "[%s] Executing: %s -> %s | %s USDC",
        mode,
        action.from_protocol,
        action.to_protocol,
        amount,
    )

    if action.from_protocol == "aave_v3":
        result = _withdraw_from_aave(amount_raw)
        results.append(result)
        if result["status"] == "reverted":
            return {"status": "error", "step": "withdraw", "results": results}

    elif action.from_protocol == "compound_iii":
        result = _withdraw_from_compound(amount_raw)
        results.append(result)
        if result["status"] == "reverted":
            return {"status": "error", "step": "withdraw", "results": results}

    elif action.from_protocol == "wallet":
        logger.info("USDC is already in the wallet, skipping withdraw")
    else:
        return {"status": "error", "reason": f"unknown from_protocol: {action.from_protocol}"}

    if action.to_protocol == "aave_v3":
        spender = AAVE_POOL_ADDRESS
    elif action.to_protocol == "compound_iii":
        spender = COMPOUND_COMET_ADDRESS
    else:
        return {"status": "error", "reason": f"unknown to_protocol: {action.to_protocol}"}

    result = _approve_usdc(spender, amount_raw)
    results.append(result)
    if result["status"] == "reverted":
        return {"status": "error", "step": "approve", "results": results}

    if action.to_protocol == "aave_v3":
        result = _supply_to_aave(amount_raw)
    else:
        result = _supply_to_compound(amount_raw)

    results.append(result)
    if result["status"] == "reverted":
        return {"status": "error", "step": "supply", "results": results}

    logger.info("[%s] Move completed: %s transactions executed", mode, len(results))
    return {"status": "success", "results": results}
