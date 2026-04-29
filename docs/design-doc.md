# Design Doc: Base Yield Lab

## Overview

Base Yield Lab is a Python backend bot for studying DeFi automation on Base.

The system has three main parts:

- `listener`: reads on-chain data through an RPC provider
- `engine`: evaluates the current state and chooses an action
- `executor`: builds, signs, and optionally broadcasts transactions

The core loop is simple:

1. Read protocol and wallet state from Base.
2. Build a structured state object.
3. Ask the decision engine for an action.
4. Validate the proposed action with deterministic rules.
5. If validation passes, execute the move.

## Stack

- Python 3.11+
- `web3.py` for EVM reads and writes
- Alchemy or another Base RPC provider
- Streamlit for the local dashboard
- Anthropic tool calling for structured decisions

## Risk Controls

The design assumes that financial automation needs hard guardrails.

Main controls:

- private key stays outside source control and outside the prompt layer
- deterministic validation happens before every transaction
- paper trading mode tests the full transaction-building flow without broadcasting
- gas cost and cooldown thresholds reduce noisy or wasteful moves
- contract allowlists prevent unexpected destinations

## Failure Modes

Important failure cases:

- private key leakage
- malformed or unsafe decisions
- RPC rate limits or temporary provider outages
- stuck or reverted transactions
- low ETH balance for gas

The operating principle is conservative fallback. If something is unclear or broken, the system should prefer `hold`.

## Implementation Phases

The project evolved in phases:

1. Read-only on-chain state collection.
2. Paper trading with real market data.
3. Testnet or sandbox validation.
4. Small-capital mainnet operation.

## Open Source Position

This repository is open source because it is primarily a study project. The goal is to make the architecture, transaction flow, and safety model legible to anyone who wants to learn from it or reuse parts of it.

