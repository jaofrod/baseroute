# Detailed Flow: Base Yield Lab

## Strategy Summary

The bot watches USDC supply rates on Aave V3 and Compound III on Base. When one protocol offers meaningfully better yield than the other, the bot can move capital toward the better venue.

The idea is simple:

- read live APYs
- compare the spread
- estimate gas cost
- validate the move
- execute only if the move is allowed and still makes economic sense

## Why Base

Base is a practical environment for this experiment because transaction costs are low and both Aave V3 and Compound III are available there.

Relevant properties:

- `chain_id = 8453`
- low transaction fees compared with Ethereum L1
- mature DeFi protocols for a small-scope learning project

## Contracts

The current implementation is centered on:

- native Base USDC
- Aave V3 pool and data provider
- Compound III USDC market

Contract addresses and partial ABIs live in [config.py](/home/jaochico/projects/web3-bot/src/base_yield_lab/config.py).

## Thresholds

The bot uses explicit thresholds rather than vague heuristics.

Important ones:

- minimum APY spread before moving
- minimum absolute destination APY
- maximum gas cost per operation
- maximum gas price
- maximum single transaction size
- minimum time between moves

These values are deliberately conservative because the project is educational and designed to prefer inaction over bad execution.

## Runtime Flow

### Listener

The listener reads:

- Aave APY
- Compound APY
- deposited balances in each protocol
- wallet USDC
- wallet ETH
- current gas price

It then computes:

- which protocol is currently better
- where capital is currently parked
- the APY spread
- estimated annual upside from moving
- estimated gas cost for a full move

### Engine

The engine receives the full state and returns one of three actions:

- `hold`
- `move_funds`
- `alert`

The prompt includes the real operating thresholds so the decision layer cannot invent looser limits.

### Firewall

The firewall is deterministic and blocks any move that fails validation.

It checks:

- approved protocols
- approved token
- max amount
- gas cost limit
- gas price limit
- cooldown
- profitability versus gas
- source balance sufficiency
- destination contract allowlist

### Executor

For a normal protocol-to-protocol move, the executor performs:

1. `withdraw`
2. `approve`
3. `supply`

If `PAPER_TRADING=true`, the executor still builds and signs the transactions but does not send them.

## Monitoring

The bot writes:

- runtime events to `bot.log`
- recent activity and counters to `bot_history.json`

The Streamlit dashboard reads those files directly and reconstructs APY history and recent runtime state from them.

## Operational Notes

- low capital keeps the downside bounded while learning
- paper trading should be the default
- the wallet should be dedicated to the bot
- every contract address should be reviewed before live mode

