# 项目架构说明 (structure.md)

本文档描述了"基于大模型的金字塔交易法量化交易系统"的整体架构和文件组织结构。

## 目录

- [1. 系统架构](#1-系统架构)
  - [1.1 核心理念](#11-核心理念)
  - [1.2 架构设计原则](#12-架构设计原则)
  - [1.3 系统核心功能模块](#13-系统核心功能模块)
    - [1.3.1 数据模块 (Data Module)](#131-数据模块-data-module)
    - [1.3.2 大模型信号生成模块 (LLM Signal Generation Module)](#132-大模型信号生成模块-llm-signal-generation-module)
    - [1.3.3 交易策略模块 (Trading Strategy Module - 金字塔法则)](#133-交易策略模块-trading-strategy-module---金字塔法则)
    - [1.3.4 风险管理模块 (Risk Management Module)](#134-风险管理模块-risk-management-module)
    - [1.3.5 订单执行模块 (Order Execution Module)](#135-订单执行模块-order-execution-module)
    - [1.3.6 投资组合与绩效管理模块 (Portfolio & Performance Management Module)](#136-投资组合与绩效管理模块-portfolio--performance-management-module)
    - [1.3.7 回测模块 (Backtesting Module)](#137-回测模块-backtesting-module)
    - [1.3.8 监控与日志模块 (Monitoring & Logging Module)](#138-监控与日志模块-monitoring--logging-module)
  - [1.4 数据与状态管理](#14-数据与状态管理)
  - [1.5 技术栈选型建议 (简述)](#15-技术栈选型建议-简述)
- [2. 目录与文件结构](#2-目录与文件结构)
  - [2.1 结构概览图](#21-结构概览图)
  - [2.2 顶层目录说明](#22-顶层目录说明)
  - [2.3 `src/` 核心源代码目录说明](#23-src-核心源代码目录说明)

## 1. 系统架构

### 1.1 核心理念

该系统的核心是通过大语言模型（LLM）分析市场数据（例如来源于AKShare、Tushare等多种数据源）、潜在的新闻、研报等信息，生成交易信号或市场判断，再结合金字塔交易法（一种趋势跟踪策略，在盈利时加仓，亏损时止损或减仓）来指导交易决策。

### 1.2 架构设计原则

系统设计遵循《Cursor 架构与开发规范》，重点强调以下原则：

*   **关注点分离 (P0):** 各模块职责单一、清晰。
*   **依赖倒置原则 (P0):** 高层模块依赖抽象而非具体实现。
*   **边界清晰 (P0):** 模块间通过定义良好的API通信。
*   **开闭原则应用 (P0):** 对扩展开放，对修改封闭。
*   **架构一致性 (P1):** 设计服务于高效可靠的量化交易目标。
*   **适度抽象 (P1):** 对外部服务和核心组件进行抽象。
*   **最小可行架构 (P1):** 从核心功能迭代构建。
*   **架构防腐层 (P1):** 隔离外部系统变化。

### 1.3 系统核心功能模块

系统主要由以下功能模块组成，形成分层结构：

```
+-----------------------------------+
|   用户界面/任务调度 (main.py)     |
+-----------------------------------+
      | (配置, 策略参数)
+-----------------------------------+
|   交易策略模块 (Strategy Module)  | 金字塔LLM策略
|   (结合LLM信号与金字塔法则)       |
+-----------------------------------+
      | (LLM信号)       |(交易指令)
      V                 V
+---------------------+ +-----------------------+
| LLM信号生成模块     | | 风险管理模块          |
| (LLM Module)        | | (Risk Module)         |
+---------------------+ +-----------------------+
      | (市场数据,特征)   | (订单校验)
      V                 V
+---------------------+ +-----------------------+
| 数据模块            | | 订单执行模块          |
| (Data Module)       | | (Execution Module)    |
| - 数据提供程序适配器 | | - 券商API适配器       |
| - 数据清洗/特征     | | - 模拟交易            |
| - 数据存储          | +-----------------------+
+---------------------+       | (成交回报, 状态)
      | (原始/处理后数据)     V
+-----------------------------------+
| 投资组合与绩效管理模块            |
| (Portfolio & Performance Module)  |
+-----------------------------------+
      | (日志, 监控数据)
+-----------------------------------+
|   监控与日志模块                  |
|   (Monitoring & Logging Module)   |
+-----------------------------------+
```

*(这是一个简化的模块交互示意图，实际数据流和控制流可能更复杂)*

#### 1.3.1 数据模块 (Data Module)

*   **职责:** 负责从多种数据源（如AKShare, Tushare, 模拟数据等）获取、清洗、存储和提供数据。
*   **子组件:**
    *   **数据接口适配器:** 安全、稳定地连接各类数据源，获取市场数据及资讯。
    *   **数据清洗与预处理:** 处理数据质量问题，如缺失值、异常值、数据对齐、复权。

#### 1.3.2 大模型信号生成模块 (LLM Signal Generation Module)

*   **职责:** 与大模型交互，基于输入数据生成交易信号或市场分析。
*   **子组件:**
    *   **LLM接口适配器:** 对接LLM API，管理密钥和请求。
    *   **Prompt工程:** 设计和优化引导LLM分析的提示。
    *   **输入构建与输出解析:** 转换数据为LLM输入，解析LLM输出为结构化信号。

#### 1.3.3 交易策略模块 (Trading Strategy Module - 金字塔法则)

*   **职责:** 实现金字塔交易法的核心逻辑，结合LLM信号进行决策。
*   **子组件:**
    *   **核心逻辑实现:** 初始建仓、盈利加仓、止盈/止损逻辑。
    *   **参数配置:** 允许灵活配置策略参数。

#### 1.3.4 风险管理模块 (Risk Management Module)

*   **职责:** 监控和控制交易风险。
*   **子组件:**
    *   **仓位管理:** 单笔和总体风险暴露控制。
    *   **止损止盈机制:** 执行预设的止损止盈条件。
    *   **事前风险评估:** 辅助分析交易信号的潜在风险。

#### 1.3.5 订单执行模块 (Order Execution Module)

*   **职责:** 与券商API对接（模拟或实盘），执行交易指令。
*   **子组件:**
    *   **券商接口适配器 (防腐层):** 对接交易API，处理订单生命周期。
    *   **模拟交易引擎:** 支持策略回测和模拟盘交易。

#### 1.3.6 投资组合与绩效管理模块 (Portfolio & Performance Management Module)

*   **职责:** 跟踪持仓、盈亏、计算绩效指标。
*   **子组件:**
    *   **实时持仓跟踪:** 管理资产、数量、成本、市值。
    *   **盈亏计算:** 计算各项盈亏数据。
    *   **绩效指标计算:** 如夏普比率、最大回撤等。

#### 1.3.7 回测模块 (Backtesting Module)

*   **职责:** 使用历史数据对LLM信号+金字塔策略进行回测和参数优化。
*   **子组件:**
    *   **回测引擎:** 驱动策略在历史数据上运行。
    *   **回测报告生成:** 输出详细的回测结果。

#### 1.3.8 监控与日志模块 (Monitoring & Logging Module)

*   **职责:** 记录系统运行状态、交易活动、错误信息，并提供监控接口。
*   **子组件:**
    *   **日志系统:** 结构化日志记录。
    *   **指标收集:** 收集关键性能指标 (KPIs)。
    *   **告警机制 (P1):** 关键问题触发告警。

### 1.4 数据与状态管理

*   **接口一致性 (P0):** 各模块间数据接口定义清晰，变更同步。
*   **数据流完整性 (P0):** 确保数据从源头到最终应用的准确性和一致性。
*   **扁平数据结构 (P1):** 优先使用扁平化数据结构，简化处理。
*   **数据所有权 (P1):** 明确数据主源及管理责任。
*   **状态最小化 (P1):** 核心交易逻辑尽量无状态，全局状态集中管理。

### 1.5 技术栈选型建议 (简述)

*   **语言:** Python
*   **核心框架:** FastAPI/Flask (微服务) 或事件驱动框架
*   **数据存储:** InfluxDB/TimescaleDB (时序), PostgreSQL/MySQL (元数据), Redis (缓存)
*   **消息队列:** RabbitMQ/Kafka (异步通信，模块解耦)
*   **LLM交互:** OpenAI Python SDK, Langchain
*   **部署:** Docker, Kubernetes

## 2. 目录与文件结构

### 2.1 结构概览图

```
quant_pyramid_llm/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── README.md
├── main.py
│
├── config/
│   ├── settings.yaml
│   ├── llm_config.yaml
│   ├── strategy_params/
│   │   └── pyramid_default.yaml
│   └── broker_config.yaml
│
├── docs/
│   ├── adr/
│   │   └── 0001-initial-architecture-choice.md
│   ├── structure.md             # (本文档)
│   ├── develop.md
│   ├── milestone.md
│   └── algorithms/
│       └── pyramid_llm_logic.md
│
├── src/
│   ├── __init__.py
│   ├── data_module/
│   │   ├── __init__.py
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base_provider.py
│   │   │   ├── akshare_provider.py # Example
│   │   │   └── tushare_provider.py # Example
│   │   ├── cleaners/
│   │   │   └── basic_cleaner.py
│   │   ├── feature_engineering/
│   │   │   ├── __init__.py
│   │   │   ├── technical_indicators.py
│   │   │   └── llm_feature_extractors.py
│   │   └── storage/
│   │       ├── __init__.py
│   │       ├── timeseries_db.py
│   │       └── metadata_db.py
│   │
│   ├── llm_module/
│   │   ├── __init__.py
│   │   ├── clients/
│   │   │   ├── __init__.py
│   │   │   ├── base_llm_client.py
│   │   │   └── openai_client.py
│   │   ├── prompt_engineering/
│   │   │   └── market_analysis_prompts.py
│   │   └── signal_parsers.py
│   │
│   ├── strategy_module/
│   │   ├── __init__.py
│   │   ├── base_strategy.py
│   │   └── pyramid_llm_strategy.py
│   │
│   ├── risk_module/
│   │   ├── __init__.py
│   │   ├── position_manager.py
│   │   └── order_validator.py
│   │
│   ├── execution_module/
│   │   ├── __init__.py
│   │   ├── brokers/
│   │   │   ├── __init__.py
│   │   │   ├── base_broker.py
│   │   │   ├── simulated_broker.py
│   │   │   └── ctp_broker.py
│   │   └── order_handler.py
│   │
│   ├── portfolio_module/
│   │   ├── __init__.py
│   │   ├── portfolio.py
│   │   └── performance.py
│   │
│   ├── backtesting_module/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── reporting.py
│   │
│   ├── monitoring_module/
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── metrics.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── datetime_helpers.py
│       └── math_utils.py
│
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── data_module/
│   │   └── ...
│   ├── integration/
│   └── conftest.py
│
└── scripts/
    ├── start_trading_bot.sh
    ├── stop_trading_bot.sh
    ├── run_backtest.py
    ├── download_historical_data.py
    └── setup_virtual_env.sh
```

### 2.2 顶层目录说明

*   **`quant_pyramid_llm/`**: 项目根目录。
*   **`.env.example`**: 环境变量模板。实际使用时复制为 `.env` 并填入敏感信息（如API密钥、数据库连接等）。
*   **`requirements.txt`**: Python项目依赖列表。
*   **`pyproject.toml`**: (可选) 若使用Poetry或PDM等现代包管理工具的项目配置文件。
*   **`README.md`**: 项目总体说明，包括如何安装、配置、运行主要任务（如启动交易、回测）。
*   **`main.py`**: 系统主入口点。根据命令行参数或配置，启动交易机器人、执行回测、数据下载任务等。
*   **`config/`**: 存放所有应用的配置文件，实现配置与代码分离。
    *   `settings.yaml`: 全局应用设置（如日志级别, 运行模式[dev/prod/backtest]）。
    *   `llm_config.yaml`: 大模型API相关配置。
    *   `strategy_params/`: 不同策略或同一策略不同参数版本的配置文件。
    *   `broker_config.yaml`: 券商接口（模拟盘/实盘）相关配置。
*   **`docs/`**: 存放所有项目相关的文档。
    *   `adr/`: 架构决策记录 (Architecture Decision Records)。
    *   `structure.md`: 本文档，描述项目架构和文件组织。
    *   `develop.md`: 开发计划与路线图。
    *   `milestone.md`: 开发进度与里程碑跟踪。
    *   `algorithms/`: 核心算法（如金字塔、LLM信号解读）的详细说明和数学原理。
*   **`src/`**: 存放所有核心应用逻辑的Python源代码。
*   **`tests/`**: 存放所有测试代码，包括单元测试和集成测试。
*   **`scripts/`**: 存放辅助性的脚本，如启动/停止服务、执行特定批处理任务、环境设置等。

### 2.3 `src/` 核心源代码目录说明

`src/` 目录按照功能模块组织，每个子目录对应架构中的一个核心模块：

*   **`data_module/`**: 数据处理模块。
    *   `providers/`: 各种数据源的适配器（如 `akshare_provider.py` 和 `tushare_provider.py`）。`base_provider.py` 定义通用接口。
    *   `cleaners/`: 数据清洗逻辑。
    *   `feature_engineering/`: 技术指标计算、LLM特征提取等。
    *   `storage/`: 数据持久化逻辑，抽象数据库操作。
*   **`llm_module/`**: 大模型交互模块。
    *   `clients/`: 调用不同LLM API的客户端实现。
    *   `prompt_engineering/`: 管理和构建Prompt模板。
    *   `signal_parsers.py`: 解析LLM输出，转换为结构化交易信号。
*   **`strategy_module/`**: 交易策略实现模块。
    *   `base_strategy.py`: 抽象策略基类，定义策略接口。
    *   `pyramid_llm_strategy.py`: 核心的金字塔结合LLM信号的策略实现。
*   **`risk_module/`**: 风险管理模块。
    *   `position_manager.py`: 仓位大小计算与管理。
    *   `order_validator.py`: 订单合法性及风险检查。
*   **`execution_module/`**: 订单执行模块。
    *   `brokers/`: 不同券商接口的适配器。`simulated_broker.py` 用于回测和模拟交易。
    *   `order_handler.py`: 订单生命周期管理。
*   **`portfolio_module/`**: 投资组合与绩效管理模块。
    *   `portfolio.py`: 跟踪和管理当前持仓信息。
    *   `performance.py`: 计算夏普比率、最大回撤等绩效指标。
*   **`backtesting_module/`**: 回测引擎模块。
    *   `engine.py`: 回测核心逻辑。
    *   `reporting.py`: 生成回测报告。
*   **`monitoring_module/`**: 监控与日志模块。
    *   `logger.py`: 日志系统配置和封装。
    *   `metrics.py`: (未来扩展) 系统性能指标收集。
*   **`utils/`**: 通用工具函数库，供各模块调用，如日期时间处理、数学计算等。

此结构旨在提供清晰的模块划分和良好的可维护性，并应随着项目的演进进行必要的调整。


大模型接口说明：
大模型的api使用火山引擎上的deepseek：api-key是3470059d-f774-4302-81e0-50fa017fea38 ，模型名称是deepseek-v3-250324，api接口文档是https://console.volcengine.com/ark/region:ark+cn-beijing/endpoint/detail?Id=ep-m-20250331153858-fmfsr&Tab=api&Type=preset