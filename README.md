# Base Yield Lab

Open-source study project for learning DeFi automation on the Base network.

Base Yield Lab reads live on-chain data, compares USDC supply opportunities between Aave V3 and Compound III, applies deterministic safety checks, and can prepare or execute transactions depending on the configured mode.

It was built as a learning project. Anyone can fork it, run it, inspect it, and adapt it.

## What It Does

- Connects to Base mainnet through an RPC provider.
- Reads USDC balances from a configured wallet.
- Reads current supply rates from Aave V3 and Compound III.
- Estimates gas cost for a potential move.
- Tracks recent activity in a local JSON file.
- Applies a deterministic safety layer before any transaction.
- Supports paper trading mode for testing without broadcasting transactions.
- Includes a Streamlit dashboard for logs and basic runtime visibility.

## What It Is Not

- Not financial advice.
- Not a production trading system.
- Not audited.
- Not guaranteed to be profitable.
- Not safe to run with meaningful funds without reviewing the code and risks.

Use a dedicated wallet and start with paper trading.

## Architecture

```mermaid
flowchart LR
  RPC["Base RPC"]
  Listener["listener.py"]
  Engine["engine.py"]
  Firewall["firewall.py"]
  Executor["executor.py"]
  State[("bot_history.json")]
  Logs[("bot.log")]
  Dashboard["dashboard.py"]
  Protocols["Aave V3 / Compound III"]

  RPC --> Listener
  Protocols --> Listener
  Listener --> Engine
  Engine --> Firewall
  Firewall --> Executor
  Executor --> Protocols
  Firewall --> State
  Executor --> Logs
  Listener --> Logs
  Logs --> Dashboard
  State --> Dashboard
```

## Project Structure

| File | Purpose |
| --- | --- |
| `main.py` | Main loop. Orchestrates reading state, choosing an action, validating it, and executing it. |
| `listener.py` | Reads Base, Aave V3, Compound III, wallet balances, gas price, and derived state. |
| `engine.py` | Decision layer that receives the current state and returns an action. |
| `firewall.py` | Deterministic guardrail layer that validates every move before execution. |
| `executor.py` | Builds, signs, and optionally broadcasts transactions. |
| `state.py` | Dataclasses and local persistence for recent activity. |
| `config.py` | Environment variables, protocol addresses, ABIs, and thresholds. |
| `dashboard.py` | Streamlit dashboard for logs, APY history, and runtime state. |

## Safety Model

The project uses a simple but important rule: no transaction should be sent before passing deterministic checks.

The firewall validates:

- approved source and destination protocols;
- approved token;
- max transaction size;
- gas cost limit;
- gas price limit;
- cooldown between moves;
- estimated profitability after gas;
- sufficient source balance;
- known destination contract.

Paper trading should remain enabled until the operator understands every transaction the bot can build.

## Requirements

- Python 3.12+
- Base RPC URL
- Dedicated EVM wallet
- USDC and ETH on Base if running live transactions

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` before running.

```bash
PRIVATE_KEY=
PUBLIC_ADDRESS=
BASE_RPC_URL=
ANTHROPIC_API_KEY=
PAPER_TRADING=true
```

Keep `PAPER_TRADING=true` while studying or testing. Setting it to `false` allows the executor to broadcast real transactions.

## Run The Bot

```bash
python main.py
```

The bot writes runtime logs to:

- `bot.log`
- `bot_history.json`

Both files are ignored by git.

## Run The Dashboard

```bash
streamlit run dashboard.py
```

The dashboard reads local logs and history files. It does not need a separate database.

## Configuration

Most tunable values live in `config.py`:

- `MIN_APY_DIFF`
- `MIN_APY_ABSOLUTE`
- `MAX_GAS_COST_USD`
- `MAX_SINGLE_TX_USDC`
- `MAX_GAS_PRICE_GWEI`
- `POLL_INTERVAL_SECONDS`
- `MIN_TIME_BETWEEN_MOVES`

Protocol addresses and partial ABIs are also centralized there.

## Development Notes

This repository is intentionally small and educational. The code favors explicit modules and comments over framework abstractions.

Good next steps:

- add tests for the firewall;
- add testnet support;
- move protocol configs out of `config.py`;
- add a strategy interface;
- improve dashboard state parsing;
- add CI for linting and tests.

## Security Notes

- Never commit `.env`.
- Never reuse a wallet that holds meaningful funds.
- Review every contract address before live mode.
- Review every transaction path before live mode.
- Use paper trading first.
- Assume bugs can lose funds.

## License

MIT. See [LICENSE](LICENSE).
