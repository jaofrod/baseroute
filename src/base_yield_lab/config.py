"""
config.py — Centralized bot configuration.

This module contains environment variables, contract addresses, partial
ABIs, and operating thresholds.
"""

import os
from dotenv import load_dotenv

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
PUBLIC_ADDRESS = os.getenv("PUBLIC_ADDRESS", "")
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

CHAIN_ID = 8453

# Native Base USDC (Circle-issued, 6 decimals)
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Aave V3 on Base
AAVE_POOL_ADDRESS = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
AAVE_DATA_PROVIDER_ADDRESS = "0x0F43731EB8d45A581f4a36DD74F5f358bc90C73A"
AAVE_AUSDC_ADDRESS = "0x4e65fE4DbA92790696d040ac24Aa414708F5c0AB"

# Compound III (Comet) on Base, USDC market
COMPOUND_COMET_ADDRESS = "0xb125E6687d4313864e53df431d5425969c15Eb2F"

# Contract allowlist checked by the firewall
KNOWN_CONTRACTS = {
    USDC_ADDRESS,
    AAVE_POOL_ADDRESS,
    AAVE_DATA_PROVIDER_ADDRESS,
    AAVE_AUSDC_ADDRESS,
    COMPOUND_COMET_ADDRESS,
}

# Partial ABIs: only the functions used by the bot are included.
USDC_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]

AAVE_POOL_ABI = [
    {
        "name": "supply",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "onBehalfOf", "type": "address"},
            {"name": "referralCode", "type": "uint16"},
        ],
        "outputs": [],
    },
    {
        "name": "withdraw",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "to", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "configuration", "type": "uint256"},
                    {"name": "liquidityIndex", "type": "uint128"},
                    {"name": "currentLiquidityRate", "type": "uint128"},
                    {"name": "variableBorrowIndex", "type": "uint128"},
                    {"name": "currentVariableBorrowRate", "type": "uint128"},
                    {"name": "currentStableBorrowRate", "type": "uint128"},
                    {"name": "lastUpdateTimestamp", "type": "uint40"},
                    {"name": "id", "type": "uint16"},
                    {"name": "aTokenAddress", "type": "address"},
                    {"name": "stableDebtTokenAddress", "type": "address"},
                    {"name": "variableDebtTokenAddress", "type": "address"},
                    {"name": "interestRateStrategyAddress", "type": "address"},
                    {"name": "accruedToTreasury", "type": "uint128"},
                    {"name": "unbacked", "type": "uint128"},
                    {"name": "isolationModeTotalDebt", "type": "uint128"},
                ],
            }
        ],
    },
]

AAVE_DATA_PROVIDER_ABI = [
    {
        "name": "getUserReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "user", "type": "address"},
        ],
        "outputs": [
            {"name": "currentATokenBalance", "type": "uint256"},
            {"name": "currentStableDebt", "type": "uint256"},
            {"name": "currentVariableDebt", "type": "uint256"},
            {"name": "principalStableDebt", "type": "uint256"},
            {"name": "scaledVariableDebt", "type": "uint256"},
            {"name": "stableBorrowRate", "type": "uint256"},
            {"name": "liquidityRate", "type": "uint256"},
            {"name": "stableRateLastUpdated", "type": "uint40"},
            {"name": "usageAsCollateralEnabled", "type": "bool"},
        ],
    }
]

COMPOUND_COMET_ABI = [
    {
        "name": "supply",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "withdraw",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getUtilization",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getSupplyRate",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "utilization", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint64"}],
    },
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

INITIAL_CAPITAL_USDC = 50
MIN_POSITION_SIZE = 5

MIN_APY_DIFF = 1.5
MIN_APY_ABSOLUTE = 0.5

MAX_GAS_COST_USD = 0.10
MIN_PROFIT_AFTER_GAS = 0.01

MAX_SINGLE_TX_USDC = 50
APPROVED_PROTOCOLS = ["aave_v3", "compound_iii"]
APPROVED_TOKENS = ["USDC"]
MAX_GAS_PRICE_GWEI = 0.5

POLL_INTERVAL_SECONDS = 300
MIN_TIME_BETWEEN_MOVES = 3600
COOLDOWN_AFTER_ERROR = 600

RAY = 10**27
SECONDS_PER_YEAR = 31_536_000
USDC_DECIMALS = 6

DEFAULT_GAS_LIMIT = 300_000
ETH_PRICE_USD = 2500.0
