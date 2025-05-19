# Pyramid LLM Strategy Logic (`pyramid_llm_logic.md`)

**Date:** 2024-08-02

## 1. Overview

The `PyramidLLMStrategy` is a trading strategy that implements the core principles of pyramid trading (adding to winning positions) while leveraging Large Language Models (LLMs) to enhance decision-making at various stages. The goal is to combine a systematic trading approach with qualitative insights derived from LLM analysis of market data.

This document outlines the core logic of the strategy, its interaction with the LLM, and how it manages trades.

## 2. Core Strategy: Pyramid Trading

Pyramid trading involves:
1.  **Initial Entry:** Entering a position when a favorable trend is identified.
2.  **Scaling In:** Adding to the existing position if the trend continues and the trade moves in a favorable direction. This is done at predefined levels or based on certain criteria.
3.  **Profit Taking & Stop Loss:** Exiting the entire position (or parts of it) if profit targets are met, the trend reverses, or a stop-loss level is hit.

The `PyramidLLMStrategy` manages the number of "pyramid levels" (how many times it can add to a position) based on configuration.

## 3. LLM Integration Points

The strategy utilizes an LLM (via `BaseLLMClient` implementations like `DeepSeekClient` or `SimulatedLLMClient`) at several key decision points. For each point, specific prompts are generated (using `PyramidTradingPrompts`), market data is formatted (using `format_utils`), the LLM response is obtained, and then parsed (using `parser_utils`).

### 3.1. Market Trend Analysis

*   **Objective:** Determine the current market trend for the target symbol (e.g., Up, Down, Sideways) and the confidence in this assessment.
*   **LLM Prompt:** A prompt is sent to the LLM asking for a market trend analysis based on recent historical data (e.g., OHLCV for the past `trend_lookback_days`).
*   **LLM Response (Expected):** A structured JSON response indicating the trend, confidence level, strength, and potentially a brief analysis or suggestion.
    ```json
    {
      "trend": "上升趋势" | "下降趋势" | "震荡趋势",
      "strength": "(e.g., 1-10 or descriptive like 强/中/弱)",
      "confidence": "(e.g., 0.0-1.0)",
      "analysis": "Brief textual analysis...",
      "suggestion": "(e.g., 考虑逢低做多, 保持观望)"
    }
    ```
*   **Strategy Action:** If the LLM indicates a strong, confident trend aligning with the strategy's desired direction (e.g., uptrend for long positions), the strategy proceeds to consider entry or position management.

### 3.2. Initial Entry Decision

*   **Objective:** If no position exists and the trend is favorable, ask the LLM to suggest an entry point.
*   **LLM Prompt:** A prompt is sent with current market data and the identified trend, asking for an entry decision, potential price range, stop-loss, take-profit levels, and initial position size suggestion (as a ratio or qualitative advice).
*   **LLM Response (Expected):**
    ```json
    {
      "entry_decision": "是" | "否",
      "reasoning": "...",
      "price_range": [min_price, max_price],
      "confidence": "(e.g., 0.0-1.0)",
      "stop_loss": "price_level",
      "take_profit": "price_level",
      "initial_position_ratio": "(e.g., 0.05 for 5% of allowed capital/risk)"
    }
    ```
*   **Strategy Action:** If `entry_decision` is "是" and confidence meets `entry_confirmation_threshold`:
    *   A BUY (or SELL for short strategies) signal is generated.
    *   Trade quantity is determined using `trade_actions.determine_trade_quantity()` based on the `position_sizing_method` (e.g., `fixed_amount`, `percent_risk` using LLM's suggested ratio) and risk manager input.
    *   Stop-loss and take-profit prices from the LLM are included in the signal.

### 3.3. Position Management (Scaling In / Adding to Position)

*   **Objective:** If an existing position is profitable and the trend remains favorable, ask the LLM if it's appropriate to add to the position (pyramid).
*   **LLM Prompt:** A prompt is sent with current market data, existing position details (entry price, current P&L, pyramid level), and the ongoing trend analysis. It asks if adding to the position is advisable, the suggested percentage to add, and updated stop-loss/take-profit for the overall position.
*   **LLM Response (Expected):**
    ```json
    {
      "action": "add" | "hold" | "reduce" | "exit",
      "reasoning": "...",
      "percentage_to_add_ratio": "(e.g., 0.05, if action is 'add')",
      "confidence": "(e.g., 0.0-1.0)",
      "updated_stop_loss": "price_level",
      "updated_target_price": "price_level"
    }
    ```
*   **Strategy Action:** If `action` is "add", confidence meets `position_increase_threshold`, and `pyramid_level` < `max_pyramid_levels`:
    *   A BUY (or SELL) signal is generated to increase the position.
    *   Quantity is determined based on `percentage_to_add_ratio` and sizing method.
    *   The position's pyramid level is incremented.
    *   Stop-loss/take-profit might be adjusted.

### 3.4. Exit Decision (Profit Taking / Stop Loss / Trend Reversal)

*   **Objective:** Determine if the existing position should be closed.
*   **Triggers:**
    1.  **LLM-Advised Exit:** During position management (3.3), if the LLM suggests "exit".
    2.  **Trend Reversal:** If market trend analysis (3.1) shows a significant reversal against the position.
    3.  **Predefined Stop-Loss/Take-Profit:** If market price hits the SL/TP levels defined at entry or during position adjustments. (This is typically handled by the `OrderHandler` or `Portfolio` module based on SL/TP orders set with the broker, but the strategy can also generate explicit exit signals if LLM advises it before these levels are hit by price action alone).
*   **LLM Prompt (for active decision):** Similar to position management, asking for advice on the current position.
*   **Strategy Action:** A SELL (or COVER) signal for the entire quantity ('all') is generated.

## 4. Strategy Parameters (`config/strategy_params/<strategy_name>.yaml`)

The `PyramidLLMStrategy` is configured through a YAML file, including:
*   `symbol`: The target trading instrument.
*   `max_pyramid_levels`: Maximum number of times to add to a position.
*   `position_sizing_method`: e.g., `fixed_amount`, `percent_risk`, `fixed_quantity`.
*   `fixed_trade_amount`: Monetary amount for `fixed_amount` sizing.
*   `risk_per_trade_pct`: Percentage of capital to risk for `percent_risk` sizing.
*   `trend_lookback_days`: Number of days of historical data for LLM trend analysis.
*   `entry_confirmation_threshold`: Minimum LLM confidence for an initial entry signal.
*   `position_increase_threshold`: Minimum LLM confidence to add to an existing position.
*   `profit_target_percentage`, `stop_loss_percentage`: Default SL/TP percentages if not overridden by LLM (can also be used by LLM as baseline).

## 5. Workflow within `generate_signals()`

1.  **Get Latest Market Data:** Fetch data for `symbol` using `data_provider`.
2.  **LLM Trend Analysis:** (Section 3.1)
    *   Format data, send prompt, parse response.
3.  **Check Existing Position:** Retrieve current position details for `symbol` from `self.positions` (updated by `BaseStrategy.update_position()` which is called after fills) or `self.portfolio.get_position()`.
4.  **Decision Logic based on Trend and Position:**
    *   **No Position & Favorable Trend:** Perform Initial Entry Decision (Section 3.2).
        *   If LLM suggests entry and criteria met, generate an entry signal (e.g., BUY).
    *   **Existing Position & Favorable Trend:** Perform Position Management (Section 3.3).
        *   If LLM suggests adding and criteria met, generate a signal to increase position.
        *   If LLM suggests holding, do nothing.
        *   If LLM suggests exiting, generate an exit signal (e.g., SELL 'all').
    *   **Existing Position & Unfavorable Trend (or LLM suggests exit):**
        *   Generate an exit signal (e.g., SELL 'all').
5.  **Signal Construction:** Signals are dictionaries containing `symbol`, `action` (BUY, SELL, SHORT, COVER), `quantity`, `price` (limit price if applicable), `type` (ENTER, EXIT, ADD), `stop_loss_price`, `take_profit_price`, `signal_id`, `timestamp`.
6.  Return list of generated signals.

## 6. Signal Execution (`execute_signal()`)

*   The `execute_signal()` method in `PyramidLLMStrategy` takes a signal generated by `generate_signals()` and an `order_handler` instance.
*   It passes the signal to `order_handler.process_signal()`.
*   The `order_handler` then interacts with the `RiskManager` and `Broker`.
*   If the order is successfully processed and filled by the broker, a `fill_event` is returned.
*   The `PyramidLLMStrategy` then calls `self.update_position(fill_event)` (from `BaseStrategy`) to update its internal tracking of the position, including `pyramid_level` if applicable.

## 7. Limitations and Future Enhancements

*   **Prompt Robustness:** Effectiveness is highly dependent on the quality and robustness of LLM prompts and the LLM's ability to understand financial context.
*   **Parsing Reliability:** Relies on LLM providing structured (JSON) responses. Errors in LLM output format can break parsing.
*   **Cost & Latency:** Frequent calls to external LLM APIs can incur costs and add latency.
*   **Backtesting LLM Behavior:** Accurately backtesting strategies that rely on dynamic LLM responses can be challenging. `SimulatedLLMClient` helps, but perfect simulation of a live LLM's nuances is difficult.
*   **Future:** Consider local LLMs, more sophisticated prompt chaining, or fine-tuning models for specific financial tasks. 