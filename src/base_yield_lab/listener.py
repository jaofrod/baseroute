"""
listener.py — On-chain reader for Base mainnet.

Each cycle reads:
- Aave V3 and Compound III APYs
- bot balances in each protocol
- idle wallet USDC and ETH balances
- current gas price
"""

import logging
import time

from web3 import Web3

from config import (
    BASE_RPC_URL,
    PUBLIC_ADDRESS,
    CHAIN_ID,
    USDC_ADDRESS,
    AAVE_POOL_ADDRESS,
    AAVE_DATA_PROVIDER_ADDRESS,
    COMPOUND_COMET_ADDRESS,
    USDC_ABI,
    AAVE_POOL_ABI,
    AAVE_DATA_PROVIDER_ABI,
    COMPOUND_COMET_ABI,
    RAY,
    SECONDS_PER_YEAR,
    USDC_DECIMALS,
    DEFAULT_GAS_LIMIT,
    ETH_PRICE_USD,
    MIN_APY_DIFF,
    MIN_APY_ABSOLUTE,
)
from state import (
    BotState,
    NetworkState,
    WalletState,
    ProtocolPosition,
    ComputedState,
    load_history,
)

logger = logging.getLogger(__name__)

w3 = Web3(
    Web3.HTTPProvider(
        BASE_RPC_URL,
        request_kwargs={"headers": {"Connection": "close"}},
    )
)

usdc_contract = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI
)
aave_pool = w3.eth.contract(
    address=Web3.to_checksum_address(AAVE_POOL_ADDRESS), abi=AAVE_POOL_ABI
)
aave_data_provider = w3.eth.contract(
    address=Web3.to_checksum_address(AAVE_DATA_PROVIDER_ADDRESS),
    abi=AAVE_DATA_PROVIDER_ABI,
)
compound_comet = w3.eth.contract(
    address=Web3.to_checksum_address(COMPOUND_COMET_ADDRESS),
    abi=COMPOUND_COMET_ABI,
)

wallet = Web3.to_checksum_address(PUBLIC_ADDRESS)
usdc_checksum = Web3.to_checksum_address(USDC_ADDRESS)


def get_aave_apy() -> float:
    """Read the current Aave V3 USDC APY."""
    reserve_data = aave_pool.functions.getReserveData(usdc_checksum).call()
    liquidity_rate = reserve_data[2]
    return (liquidity_rate / RAY) * 100


def get_compound_apy() -> float:
    """Read the current Compound III USDC APY."""
    utilization = compound_comet.functions.getUtilization().call()
    supply_rate = compound_comet.functions.getSupplyRate(utilization).call()
    rate_per_second = supply_rate / 1e18
    return ((1 + rate_per_second) ** SECONDS_PER_YEAR - 1) * 100


def get_aave_balance() -> float:
    """Read the bot's deposited USDC balance in Aave."""
    result = aave_data_provider.functions.getUserReserveData(
        usdc_checksum, wallet
    ).call()
    return result[0] / (10**USDC_DECIMALS)


def get_compound_balance() -> float:
    """Read the bot's deposited USDC balance in Compound III."""
    raw_balance = compound_comet.functions.balanceOf(wallet).call()
    return raw_balance / (10**USDC_DECIMALS)


def get_wallet_usdc_balance() -> float:
    """Read idle USDC currently sitting in the wallet."""
    raw_balance = usdc_contract.functions.balanceOf(wallet).call()
    return raw_balance / (10**USDC_DECIMALS)


def get_wallet_eth_balance() -> float:
    """Read ETH available in the wallet for gas."""
    raw_balance = w3.eth.get_balance(wallet)
    return w3.from_wei(raw_balance, "ether")


def get_gas_price_gwei() -> float:
    """Read the current Base gas price in gwei."""
    gas_price_wei = w3.eth.gas_price
    return float(w3.from_wei(gas_price_wei, "gwei"))


def build_state() -> BotState:
    """Build the full bot state from live on-chain reads."""
    logger.info("Reading on-chain data from Base...")

    aave_apy = get_aave_apy()
    compound_apy = get_compound_apy()
    aave_balance = get_aave_balance()
    compound_balance = get_compound_balance()
    wallet_usdc = get_wallet_usdc_balance()
    wallet_eth = get_wallet_eth_balance()
    gas_price = get_gas_price_gwei()
    block_number = w3.eth.block_number

    gas_price_wei = w3.eth.gas_price
    gas_cost_usd = (DEFAULT_GAS_LIMIT * gas_price_wei * 3) / 1e18 * ETH_PRICE_USD

    network = NetworkState(
        chain_id=CHAIN_ID,
        gas_price_gwei=gas_price,
        gas_cost_estimate_usd=gas_cost_usd,
        block_number=block_number,
    )

    wallet_state = WalletState(
        address=PUBLIC_ADDRESS,
        usdc_balance=wallet_usdc,
        eth_balance=float(wallet_eth),
    )

    aave_pos = ProtocolPosition(deposited_usdc=aave_balance, current_apy_pct=aave_apy)
    compound_pos = ProtocolPosition(
        deposited_usdc=compound_balance, current_apy_pct=compound_apy
    )

    total_capital = aave_balance + compound_balance + wallet_usdc

    if aave_balance > compound_balance:
        current_protocol = "aave_v3"
        current_apy = aave_apy
    elif compound_balance > aave_balance:
        current_protocol = "compound_iii"
        current_apy = compound_apy
    else:
        current_protocol = "none"
        current_apy = 0.0

    if aave_apy > compound_apy:
        best_protocol = "aave_v3"
        best_apy = aave_apy
    else:
        best_protocol = "compound_iii"
        best_apy = compound_apy

    apy_diff = abs(aave_apy - compound_apy)
    should_move = (
        apy_diff >= MIN_APY_DIFF
        and best_protocol != current_protocol
        and best_apy >= MIN_APY_ABSOLUTE
    )
    annual_gain = (apy_diff / 100) * total_capital

    computed = ComputedState(
        total_capital_usdc=total_capital,
        best_protocol=best_protocol,
        best_apy_pct=best_apy,
        current_protocol=current_protocol,
        current_apy_pct=current_apy,
        apy_diff_pct=apy_diff,
        should_consider_move=should_move,
        estimated_annual_gain_if_move=annual_gain,
        estimated_gas_cost_for_move=gas_cost_usd,
    )

    history = load_history()

    return BotState(
        timestamp=time.time(),
        network=network,
        wallet=wallet_state,
        aave=aave_pos,
        compound=compound_pos,
        computed=computed,
        history=history,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    if not w3.is_connected():
        print("ERROR: Could not connect to Base via RPC")
        print(f"URL: {BASE_RPC_URL[:50]}...")
        exit(1)

    print(f"Connected to Base. Chain ID: {w3.eth.chain_id}")
    print(f"Wallet: {PUBLIC_ADDRESS}")
    print()

    state = build_state()

    print("\n=== CURRENT STATE ===")
    print(f"Aave APY:         {state.aave.current_apy_pct:.4f}%")
    print(f"Compound APY:     {state.compound.current_apy_pct:.4f}%")
    print(f"Difference:       {state.computed.apy_diff_pct:.4f}%")
    print(f"Best protocol:    {state.computed.best_protocol}")
    print()
    print(f"Aave balance:     {state.aave.deposited_usdc:.6f} USDC")
    print(f"Compound balance: {state.compound.deposited_usdc:.6f} USDC")
    print(f"Wallet USDC:      {state.wallet.usdc_balance:.6f}")
    print(f"Wallet ETH:       {state.wallet.eth_balance:.6f}")
    print(f"Total capital:    {state.computed.total_capital_usdc:.6f} USDC")
    print()
    print(f"Gas price:        {state.network.gas_price_gwei:.6f} gwei")
    print(f"Gas cost:         ${state.network.gas_cost_estimate_usd:.6f}")
    print(f"Block:            {state.network.block_number}")
    print(f"Consider moving?  {state.computed.should_consider_move}")
