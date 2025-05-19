# ADR-0004: Simulated Providers for Testing

**Date:** 2024-08-02

**Status:** Accepted

## Context

Effective testing of the quantitative trading system, particularly unit and integration tests, requires isolation from external dependencies such as live data feeds and LLM APIs. Relying on live services for testing is slow, costly, non-deterministic, and can lead to flaky tests. 

## Decision

We decided to create simulated versions of key external service providers:

1.  **`SimulatedDataProvider` (`src/data_module/providers/simulated_data_provider.py`):**
    *   Implements the `BaseDataProvider` interface.
    *   Generates deterministic (e.g., pseudo-random but seedable if needed, or pre-defined) OHLCV market data for specified symbols and date ranges.
    *   Can be configured to return specific data patterns or scenarios for targeted testing.
    *   Allows testing of data handling, feature engineering, and strategy logic that consumes market data without hitting actual data APIs.

2.  **`SimulatedLLMClient` (`src/llm_module/clients/simulated_llm_client.py`):**
    *   Implements the `BaseLLMClient` interface.
    *   Returns predefined JSON responses based on keywords in the input prompt, or a default simulated response.
    *   Allows testing of LLM integration points, prompt engineering, response parsing, and strategy logic that depends on LLM outputs without making actual LLM API calls.
    *   Provides methods for simulating text generation, streaming, and embeddings.

These simulated providers are used extensively in unit tests (e.g., testing strategies, portfolio calculations based on simulated market movements) and integration tests (e.g., testing the backtesting engine flow with simulated data and LLM interactions).

## Consequences

**Positive:**
*   **Test Determinism & Reliability:** Tests become deterministic and reliable, as they do not depend on fluctuating live data or LLM responses.
*   **Speed:** Tests run significantly faster without network latency from external API calls.
*   **Cost Savings:** Avoids costs associated with data subscriptions and LLM API usage during testing.
*   **Offline Development:** Enables development and testing even when offline or without access to live services.
*   **Focused Testing:** Allows for crafting specific data or LLM response scenarios to test edge cases or particular behaviors in modules.
*   **Simplified CI/CD:** Continuous integration pipelines can run tests without needing credentials or access to external services.

**Negative:**
*   **Maintenance of Simulators:** The simulated providers need to be maintained and updated if the interfaces of the base providers (`BaseDataProvider`, `BaseLLMClient`) evolve.
*   **Simulation Fidelity:** Simulations are not perfect replicas of real-world services. Complex behaviors or specific error conditions of live services might not be fully captured by the simulators. This means integration with actual live services still needs thorough testing in a staging or UAT environment.

## Alternatives Considered

1.  **Mocking Libraries Only (e.g., `unittest.mock`):** Relying solely on mocking individual methods of live provider classes during tests. While useful for unit tests, setting up complex mock behaviors for entire data streams or conversational LLM interactions can be cumbersome. Simulated providers offer a more structured and reusable way to mimic the behavior of these services.
2.  **Recording and Replaying Live Interactions (e.g., VCR.py):** Recording actual API responses and replaying them during tests. This is a valid approach but can be complex to manage recordings, especially if API responses change or if dynamic data (like timestamps) is involved. Simulated providers give more direct control over the test data generated.
3.  **No Simulation (Testing against Live Dev/Sandbox APIs):** Directly using development or sandbox versions of live APIs. Rejected for general unit/integration testing due to reasons of speed, cost, determinism, and availability. 