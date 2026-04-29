"""
engine.py — Decision engine for the bot.

The engine sends the current bot state to Claude using tool calling and
expects a structured action in response.

Safe default:
If the API fails, no tool call is returned, or the payload is malformed,
the fallback is always `hold`.
"""

import json
import logging
from dataclasses import asdict

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    MIN_APY_DIFF,
    MIN_APY_ABSOLUTE,
    MAX_SINGLE_TX_USDC,
    MIN_TIME_BETWEEN_MOVES,
    MAX_GAS_COST_USD,
)
from state import BotState, LLMAction

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = f"""You are a DeFi agent managing a USDC position on Base.
Your goal is to maximize yield by moving capital between Aave V3 and
Compound III while minimizing gas costs and operational risk.

Rules:
- Only operate on USDC and approved protocols (Aave V3, Compound III)
- Only move capital if the APY difference is >= {MIN_APY_DIFF}%
- Always consider gas cost before deciding
- If both APYs are below {MIN_APY_ABSOLUTE}%, keep the current position
- Never move more than {MAX_SINGLE_TX_USDC} USDC per transaction
- Respect the minimum cooldown of {MIN_TIME_BETWEEN_MOVES}s between moves
- Maximum acceptable gas cost: ${MAX_GAS_COST_USD}
- If uncertain, choose "hold"
- If USDC is idle in the wallet, deposit it into the best-yielding protocol
- If you detect anomalies (zero APY, low ETH for gas), use "alert"

Analyze the provided data and use exactly one available tool."""

TOOLS = [
    {
        "name": "hold",
        "description": "Keep the current position unchanged for this cycle",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why no action should be taken",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "move_funds",
        "description": "Withdraw USDC from one protocol and deposit it into another",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_protocol": {
                    "type": "string",
                    "enum": ["aave_v3", "compound_iii", "wallet"],
                    "description": "Source of the funds",
                },
                "to_protocol": {
                    "type": "string",
                    "enum": ["aave_v3", "compound_iii"],
                    "description": "Destination protocol",
                },
                "amount_usdc": {
                    "type": "number",
                    "description": "Amount of USDC to move (-1 means move everything)",
                },
                "reason": {
                    "type": "string",
                    "description": "Why the move should happen",
                },
            },
            "required": ["from_protocol", "to_protocol", "amount_usdc", "reason"],
        },
    },
    {
        "name": "alert",
        "description": "Flag a condition that requires human attention",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"],
                    "description": "Alert severity",
                },
                "message": {
                    "type": "string",
                    "description": "Description of what was detected",
                },
            },
            "required": ["severity", "message"],
        },
    },
]


def _state_to_prompt(state: BotState) -> str:
    """Serialize BotState into readable JSON for the LLM."""
    data = asdict(state)
    return json.dumps(data, indent=2, default=str)


def _parse_response(response) -> LLMAction:
    """Extract the Claude tool call and convert it into LLMAction."""
    tool_block = None
    for block in response.content:
        if block.type == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        logger.warning("LLM did not return tool_use. Falling back to hold.")
        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text
                break
        return LLMAction(action="hold", reason=f"LLM without tool_use: {text[:200]}")

    tool_name = tool_block.name
    tool_input = tool_block.input

    if tool_name == "hold":
        return LLMAction(action="hold", reason=tool_input.get("reason", ""))

    if tool_name == "move_funds":
        return LLMAction(
            action="move_funds",
            from_protocol=tool_input.get("from_protocol", ""),
            to_protocol=tool_input.get("to_protocol", ""),
            amount_usdc=tool_input.get("amount_usdc", 0),
            reason=tool_input.get("reason", ""),
        )

    if tool_name == "alert":
        return LLMAction(
            action="alert",
            severity=tool_input.get("severity", "info"),
            message=tool_input.get("message", ""),
        )

    logger.warning("Unknown tool: %s. Falling back to hold.", tool_name)
    return LLMAction(action="hold", reason=f"Unknown tool: {tool_name}")


def get_decision(state: BotState) -> LLMAction:
    """Send state to Claude and return the chosen action."""
    logger.info("Querying Claude for a decision...")

    state_text = _state_to_prompt(state)
    user_message = f"Current bot state:\n\n{state_text}\n\nAnalyze and decide on the action."

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=[{"role": "user", "content": user_message}],
        )

        action = _parse_response(response)

        logger.info("LLM decision: %s", action.action)
        if action.action == "hold":
            logger.info("  Reason: %s", action.reason)
        elif action.action == "move_funds":
            logger.info(
                "  %s -> %s | %s USDC",
                action.from_protocol,
                action.to_protocol,
                action.amount_usdc,
            )
            logger.info("  Reason: %s", action.reason)
        elif action.action == "alert":
            logger.info("  [%s] %s", action.severity, action.message)

        return action

    except anthropic.APIError as e:
        logger.error("Claude API error: %s", e)
        return LLMAction(action="hold", reason=f"API error: {e}")
    except Exception as e:
        logger.error("Unexpected engine error: %s", e)
        return LLMAction(action="hold", reason=f"Unexpected error: {e}")
