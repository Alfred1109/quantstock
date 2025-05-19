# ADR-0003: Strategy Module Design

**Date:** 2024-08-02

**Status:** Accepted

## Context

The trading system needs to support various trading strategies. Each strategy might have its own unique logic for data processing, signal generation, and order execution parameters. A clear and extensible structure for the strategy module is essential for managing complexity and facilitating the addition of new strategies.

## Decision

We adopted the following design for the `src/strategy_module/`:

1.  **Abstract Base Class `BaseStrategy`:** An ABC (`BaseStrategy`) defines the common interface and core functionalities for all trading strategies. This includes:
    *   Initialization with configuration, data provider, and LLM client.
    *   Abstract methods like `on_data()`, `generate_signals()`, and `execute_signal()` that concrete strategies must implement.
    *   Common helper methods like `load_parameters()` for loading strategy-specific parameters and `update_position()` for internal position tracking (though final portfolio updates are handled by the `Portfolio` module via `OrderHandler` and `Broker`).
    *   Placeholders for `run_backtest()` and `run_live()`, which are typically orchestrated by a backtesting engine or a live trading engine rather than the strategy itself.
    *   Methods `set_portfolio_object()` and `set_risk_manager()` to allow the backtesting engine or main application to inject dependencies.

2.  **Concrete Strategy Implementations:** Specific strategies, like `PyramidLLMStrategy`, inherit from `BaseStrategy` and implement their unique logic. The `PyramidLLMStrategy` specifically integrates LLM-generated insights for pyramid trading decisions.

3.  **Utility Sub-package `strategy_module/utils/`:** Common functionalities related to strategies but not part of the core strategy flow itself were refactored into utility modules:
    *   `parser_utils.py`: For parsing LLM responses into structured data usable by strategies.
    *   `format_utils.py`: For formatting market data or other information into prompts suitable for LLM consumption.
    *   `trade_actions.py`: For helper functions related to determining trade quantities, stop-loss/take-profit levels, etc., based on strategy parameters or LLM suggestions.
    This separation keeps the main strategy classes cleaner and promotes reuse of these utility functions.

## Consequences

**Positive:**
*   **Standardization:** All strategies adhere to a common interface, making them interchangeable and easier to integrate with the backtesting/live trading engine.
*   **Extensibility:** New strategies can be added by creating new classes derived from `BaseStrategy`.
*   **Improved Cohesion & Reduced Coupling:** Utility functions are separated, making the strategy classes more focused on their core logic. Strategies are also decoupled from the specifics of LLM response parsing or data formatting for LLMs.
*   **Testability:** Individual strategy components (base class methods, specific strategy logic, utility functions) can be tested more easily in isolation.

**Negative:**
*   **Initial Setup Overhead:** Defining the base class and utility structure requires upfront design effort.
*   **Potential for Over-Generic Base Class:** If strategies become too diverse, the `BaseStrategy` interface might become bloated or too generic.

## Alternatives Considered

1.  **Monolithic Strategy Classes:** Implementing each strategy as a standalone class without a common base or shared utilities. Rejected due to lack of standardization, difficulty in integration, and code duplication.
2.  **Configuration-Driven Strategies:** A highly generic strategy engine driven purely by configuration. While flexible, this can become overly complex to configure and debug, and might not easily accommodate strategies with very unique, non-configurable logic. The chosen approach allows for code-defined logic with configurable parameters. 