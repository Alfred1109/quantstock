# ADR-0002: LLM Client Abstraction

**Date:** 2024-08-02

**Status:** Accepted

## Context

The system needs to integrate with Large Language Models (LLMs) for tasks like market trend analysis, signal generation, and potentially other natural language processing tasks. Different LLM providers (e.g., DeepSeek, OpenAI, local models) may be used over time or simultaneously for different purposes. A flexible way to switch between or add new LLM providers is required without significant code changes in the core strategy logic.

## Decision

We decided to implement an abstract base class (ABC) `BaseLLMClient` within `src/llm_module/clients/`. This ABC defines a common interface for interacting with LLMs, including methods like `generate_text()` and `get_embeddings()`. 

Concrete implementations for specific LLM providers, such as `DeepSeekClient`, inherit from `BaseLLMClient` and implement the abstract methods using the provider-specific APIs and authentication mechanisms.

A `SimulatedLLMClient` was also created, inheriting from `BaseLLMClient`. This client returns predefined or rule-based responses, crucial for:
*   Unit and integration testing without making actual API calls (saving costs and improving test determinism).
*   Offline development and debugging.
*   Providing a fallback if live LLM services are unavailable or not configured.

The choice of LLM client (e.g., `deepseek`, `simulated`) is configurable via `config/llm_config.yaml`, allowing easy switching.

## Consequences

**Positive:**
*   **Modularity & Flexibility:** New LLM providers can be integrated by creating a new class that implements the `BaseLLMClient` interface, without altering the strategy code that uses the client.
*   **Testability:** The `SimulatedLLMClient` greatly enhances testability by providing predictable LLM responses.
*   **Decoupling:** Strategies are decoupled from the specific LLM provider, adhering to the Dependency Inversion Principle.
*   **Simplified Configuration:** Switching LLM providers can be done through configuration changes.

**Negative:**
*   **Interface Maintenance:** The `BaseLLMClient` interface needs to be general enough to accommodate various LLM functionalities. If a new LLM offers a radically different interaction pattern, the base interface might need to be revised or extended.
*   **Overhead for Simple Cases:** For a system that might only ever use one LLM provider, the abstraction adds a small layer of indirection.

## Alternatives Considered

1.  **Direct API Integration:** Directly integrating a specific LLM provider's SDK into the strategy logic. Rejected because it would tightly couple the strategy to that provider, making it difficult to switch or test.
2.  **Generic HTTP Client Wrapper:** Creating a very generic HTTP client to call LLM APIs. Rejected as it would not provide a strong enough contract for LLM-specific operations and would shift too much LLM interaction logic (like prompt formatting for specific models) into the strategy. The `BaseLLMClient` provides a more domain-specific abstraction. 