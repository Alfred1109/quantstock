# ADR-0005: Refactoring of `src/utils/` into Domain-Specific Modules

**Date:** 2024-08-02

**Status:** Accepted

## Context

The project initially had a general utility directory `src/utils/` containing various helper functions, including database interaction (`db_utils.py`), iFind API configurations and wrappers (`ths_api_config.py`, `thsifind.py`), old logger and config implementations (`logger.py`, `config.py`), and risk control logic (`risk_control.py`). As the system grew, this directory became a miscellaneous collection, potentially violating the Single Responsibility Principle and making it harder to locate domain-specific utilities.

## Decision

We decided to refactor the `src/utils/` directory by migrating its contents into more appropriate, domain-specific modules. The key migrations were:

1.  **Database Utilities (`db_utils.py`):** Logic related to SQLite database interaction (connection, schema creation, CRUD operations for k-line data, etc.) was moved to `src/data_module/storage/sqlite_handler.py`. This co-locates database storage logic with other data module responsibilities.

2.  **iFind API Logic (`thsifind.py`, `ths_api_config.py`):** The iFind API wrapper and its specific configurations were identified as belonging to data provisioning. A placeholder `IFindDataProvider` was created in `src/data_module/providers/ifind_provider.py`, and the intention is for the logic from `thsifind.py` to be fully integrated here. `ths_api_config.py` became obsolete due to the new central configuration system.

3.  **Risk Control Logic (`risk_control.py`):** The `RiskController` class and its associated logic were integrated into the `SimpleRiskManager` (`src/risk_module/simple_risk_manager.py`). This consolidates risk management functionalities within the dedicated risk module.

4.  **Obsolete Utilities (`logger.py`, `config.py` in `src/utils/`):** The old logger and configuration utilities in `src/utils/` were superseded by the new `Logger` in `src/monitoring_module/` and the centralized YAML-based configuration loading in `main.py` (using `config/settings.yaml`, etc.). These obsolete files were deleted.

5.  **Result:** The `src/utils/` directory was subsequently emptied of primary code files and eventually removed (or its `__init__.py` deleted, leaving it as a non-package if system files like `__pycache__` remain).

This aligns with the "关注点分离 (Separation of Concerns)" and "边界清晰 (Clear Boundaries)" principles from the project's development规范.

## Consequences

**Positive:**
*   **Improved Modularity:** Code is organized into more logical, domain-specific modules, making the codebase easier to understand, navigate, and maintain.
*   **Enhanced Cohesion:** Related functionalities (e.g., all data storage, all risk management) are grouped together.
*   **Reduced Coupling:** Modules are more self-contained, reducing dependencies on a generic `utils` dump-ground.
*   **Clearer Responsibilities:** The purpose of each module is more clearly defined.
*   **Adherence to Design Principles:** Better follows architectural guidelines regarding separation of concerns.

**Negative:**
*   **Refactoring Effort:** Required effort to identify, move, and update imports for the affected utilities.
*   **Potential for Initial Disruption:** Team members needed to familiarize themselves with the new locations of these utilities.

## Alternatives Considered

1.  **Retaining `src/utils/` with sub-packages:** Creating sub-packages within `src/utils/` (e.g., `src/utils/db/`, `src/utils/risk/`). While an improvement, it doesn't fully co-locate utilities with their primary domain modules (e.g., database utilities are best kept within the data module itself).
2.  **Gradual Refactoring:** Moving utilities on an ad-hoc basis as they are touched. Rejected in favor of a more concerted effort to clean up `src/utils/` to establish a better structure sooner. 