# 量化模型-个人交易 (Quantitative Trading System with LLM)

This project implements a quantitative trading system, primarily designed around a pyramid strategy enhanced by Large Language Models (LLMs). It features a modular architecture for strategy development, backtesting, (simulated) execution, and performance analysis.

**详细项目文档 (Detailed Project Documentation):** See the `docs/` directory, including:
*   `docs/README.md`: Overall project vision and details (if more extensive than this root README).
*   `docs/structure.md`: Detailed explanation of the project architecture and module responsibilities.
*   `docs/develop.md`: Development plan and phased approach.
*   `docs/milestone.md`: Live tracking of development progress and milestones.
*   `docs/adr/`: Architecture Decision Records documenting key design choices.

## Core Features

*   **Modular Design:** Separated modules for data handling, LLM interaction, strategies, risk management, execution, portfolio management, and backtesting.
*   **LLM Integration:** Designed to incorporate LLMs for market analysis, signal generation, and position sizing advice (e.g., `PyramidLLMStrategy`).
*   **Backtesting Engine:** A robust engine to test strategies against historical data.
*   **Simulated Components:** Includes simulated data providers, LLM clients, and brokers for testing and development without live dependencies.
*   **Configuration Driven:** Key parameters, paths, and settings are managed via YAML configuration files in the `config/` directory.
*   **Comprehensive Logging:** Centralized logging to console and files via `src/monitoring_module/logger.py`.

## Project Structure

The project follows a structured layout. Key directories include:

```
量化模型-个人交易/
├── .venv/                  # Virtual environment
├── config/                 # Configuration files (settings.yaml, llm_config.yaml, etc.)
│   └── strategy_params/    # Strategy-specific parameter files
├── data/                   # Local data storage (e.g., SQLite database, CSVs)
├── docs/                   # Project documentation (architecture, ADRs, plans)
│   └── adr/                # Architecture Decision Records
├── output/                 # Output files from operations
│   ├── cache/              # Cache files
│   ├── logs/               # Application log files
│   └── results/            # Backtest reports, trade logs, etc.
├── src/                    # Core source code
│   ├── backtesting_module/ # Backtesting engine and reporting
│   ├── data_module/        # Data providers, cleaners, storage
│   ├── execution_module/   # Order handling and broker interactions
│   ├── llm_module/         # LLM client abstractions and prompt engineering
│   ├── monitoring_module/  # Logging and monitoring utilities
│   ├── portfolio_module/   # Portfolio tracking and performance calculation
│   ├── risk_module/        # Risk management components
│   └── strategy_module/    # Trading strategy implementations and utilities
├── tests/                  # Unit and integration tests
│   ├── unit/
│   └── integration/
├── .env.example            # Example environment file for API keys, etc.
├── main.py                 # Main application entry point for different modes
├── requirements.txt        # pip-compatible dependency list
├── setup.py                # Python package setup script
├── start.sh                # Unified script for setup, services, and running modes
└── README.md               # This file
```

For a detailed explanation of each module's responsibility, please refer to `docs/structure.md`.

## Setup and Installation

### Prerequisites

*   Python 3.10 or higher.
*   `bash` shell for running `start.sh` (standard on Linux/macOS, available on Windows via WSL or Git Bash).

### Installation Steps

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd 量化模型-个人交易
    ```

2.  **Initialize Project using `start.sh` (Recommended):**
    This script will handle virtual environment creation/activation, dependency installation, and directory setup.
    ```bash
    chmod +x start.sh
    ./start.sh init
    ```
    If you encounter issues, ensure `start.sh` has execute permissions and your environment can run shell scripts.

3.  **Environment Variables (if needed):**
    Copy the `.env.example` file to `.env` and fill in any necessary API keys or sensitive credentials if you plan to use services requiring them (e.g., specific LLM providers not covered by default simulated clients).
    ```bash
    cp .env.example .env
    # Edit .env with your actual keys
    ```
    The application (e.g., LLM clients) can load these variables.

4.  **Configuration Files:**
    Review and customize the configuration files in the `config/` directory as needed:
    *   `settings.yaml`: Main application settings (logging, paths are often managed by `start.sh` or `main.py` defaults now).
    *   `llm_config.yaml`: Configuration for LLM clients.
    *   `broker_config.yaml`: Settings for broker connections.
    *   `config/strategy_params/`: Directory for strategy-specific parameter files.

    The `start.sh init` command already creates necessary output directories. Database initialization is also typically handled by the application on first run if needed, or by specific data loading scripts.

### Manual Setup (Alternative to `start.sh init`)

If you prefer or need to set up manually:

1.  **Create and Activate Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Linux/macOS
    # .venv\Scripts\activate    # On Windows
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Create Directories:**
    Manually create directories like `output/logs`, `output/pids`, `data/`, etc., if they don't exist. (Refer to `start.sh` or `main.py` for typical structures if needed).

## Running the System

The `start.sh` script is the primary way to run different operational modes and manage services.

### General Usage

```bash
./start.sh <mode> [options]
```

Execute `./start.sh --help` to see all available modes and their options.

### Common Modes

*   **`init`**: Initializes the project (dependencies, directories).
*   **`backtest`**: Run a backtest of a strategy.
*   **`frontend`**: Launch the Web UI (if configured and available).
*   **`realtime --action [start|stop|status]`**: Manage the realtime data service (Note: this service's data fetching capability is currently disabled pending refactor after iFind removal).
*   Other modes like `trade`, `optimize` may be available or planned.

### Backtesting Example

To run a backtest using the `PyramidLLMStrategy`:

```bash
./start.sh backtest \
    --symbols SIM_TEST_STOCK \
    --start-date 2023-01-01 \
    --end_date 2023-03-31 \
    --initial_capital 100000 \
    --strategy_params pyramid_default.yaml
```

Review the output of `./start.sh backtest --help` (or `./start.sh --help` for general options) for all available arguments for backtesting.
Backtest results are typically saved to the `output/results/` directory.

## Development & Testing

(Ensure your virtual environment, e.g., `.venv/bin/activate`, is active before running tests.)

*   **Unit Tests:** Run unit tests using `unittest` from the project root:
    ```bash
    python -m unittest discover -s tests/unit -p "test_*.py"
    ```
*   **Integration Tests:** Run integration tests:
    ```bash
    python -m unittest discover -s tests/integration -p "test_*.py"
    ```
*   **Code Style & Linting:** (Details to be added - e.g., Flake8, Black)

## Contributing

(Contribution guidelines to be added)

## License

(License information to be added) 