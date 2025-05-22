#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录 (start.sh is in the root)
PROJECT_ROOT="$(pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    量化模型-个人交易系统启动脚本    ${NC}"
echo -e "${BLUE}========================================${NC}"

# --- Start: Directory Creation Logic (from bin/create_dirs.sh) ---
# 日志函数 (local to this script)
_start_sh_log() {
  echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 创建目录函数 (local to this script)
_start_sh_create_dir() {
  if [ ! -d "$1" ]; then
    mkdir -p "$1"
    _start_sh_log "${GREEN}创建目录: $1${NC}"
  else
    _start_sh_log "${BLUE}目录已存在: $1${NC}"
  fi
}

setup_project_directories() {
    _start_sh_log "${BLUE}开始创建/验证项目目录结构...${NC}"
    _start_sh_create_dir "${PROJECT_ROOT}/config"
    _start_sh_create_dir "${PROJECT_ROOT}/config/strategy_params"
    _start_sh_create_dir "${PROJECT_ROOT}/data"
    _start_sh_create_dir "${PROJECT_ROOT}/data/backup"
    # _start_sh_create_dir "${PROJECT_ROOT}/logs" # General logs, output/logs is primary
    _start_sh_create_dir "${PROJECT_ROOT}/output"
    _start_sh_create_dir "${PROJECT_ROOT}/output/cache/akshare"
    _start_sh_create_dir "${PROJECT_ROOT}/output/cache/market_analysis"
    _start_sh_create_dir "${PROJECT_ROOT}/output/cache/ths_http"
    _start_sh_create_dir "${PROJECT_ROOT}/output/cache/ths_sdk"
    _start_sh_create_dir "${PROJECT_ROOT}/output/data/cache/ths_http"
    _start_sh_create_dir "${PROJECT_ROOT}/output/data/cache/ths_sdk"
    _start_sh_create_dir "${PROJECT_ROOT}/output/logs" # Primary log location
    _start_sh_create_dir "${PROJECT_ROOT}/output/pids"
    _start_sh_create_dir "${PROJECT_ROOT}/output/.pid"
    _start_sh_create_dir "${PROJECT_ROOT}/output/plots"
    _start_sh_create_dir "${PROJECT_ROOT}/output/results"
    _start_sh_log "${GREEN}项目目录结构创建/验证完成.${NC}"

    # Permissions
    chmod +x "${PROJECT_ROOT}/start.sh" # This script itself

    if [ ! -f "${PROJECT_ROOT}/config/config.yml" ]; then
      _start_sh_log "${YELLOW}警告: 主配置文件 '${PROJECT_ROOT}/config/config.yml' 可能不存在。${NC}"
    fi
}
# --- End: Directory Creation Logic ---

# --- Start: Realtime Service Management (from bin/run-services.sh) ---
REALTIME_SERVICE_PID_FILE="${PROJECT_ROOT}/output/pids/realtime_service.pid"
REALTIME_SERVICE_LOG_FILE="${PROJECT_ROOT}/output/logs/realtime_service.log"
REALTIME_SERVICE_COMMAND="python ${PROJECT_ROOT}/src/services/realtime_service.py"

start_realtime_daemon() {
  _start_sh_log "${BLUE}启动实时数据服务守护进程...${NC}"
  if [ -f "$REALTIME_SERVICE_PID_FILE" ]; then
    PID=$(cat "$REALTIME_SERVICE_PID_FILE")
    if ps -p "$PID" > /dev/null; then
      _start_sh_log "${YELLOW}实时数据服务已在运行 (PID: $PID)${NC}"
      return
    fi
  fi
  
  nohup $REALTIME_SERVICE_COMMAND >> "$REALTIME_SERVICE_LOG_FILE" 2>&1 &
  local DAEMON_PID=$!
  echo "$DAEMON_PID" > "$REALTIME_SERVICE_PID_FILE"
  _start_sh_log "${GREEN}实时数据服务已启动 (PID: $DAEMON_PID). Log: $REALTIME_SERVICE_LOG_FILE${NC}"
}

stop_realtime_daemon() {
  _start_sh_log "${BLUE}停止实时数据服务守护进程...${NC}"
  if [ -f "$REALTIME_SERVICE_PID_FILE" ]; then
    PID=$(cat "$REALTIME_SERVICE_PID_FILE")
    if ps -p "$PID" > /dev/null; then
      kill "$PID"
      _start_sh_log "${YELLOW}发送停止信号到实时数据服务 (PID: $PID)${NC}"
      sleep 2
      if ps -p "$PID" > /dev/null; then
        _start_sh_log "${RED}服务未响应停止信号，强制终止...${NC}"
        kill -9 "$PID"
      fi
    else
      _start_sh_log "${YELLOW}实时数据服务PID文件存在但进程不在运行中${NC}"
    fi
    rm -f "$REALTIME_SERVICE_PID_FILE"
    _start_sh_log "${GREEN}实时数据服务已停止.${NC}"
  else
    _start_sh_log "${YELLOW}未找到实时数据服务PID文件，可能未启动.${NC}"
  fi
}

status_realtime_daemon() {
  _start_sh_log "${BLUE}检查实时数据服务状态...${NC}"
  if [ -f "$REALTIME_SERVICE_PID_FILE" ]; then
    PID=$(cat "$REALTIME_SERVICE_PID_FILE")
    if ps -p "$PID" > /dev/null; then
      _start_sh_log "${GREEN}实时数据服务: 运行中 (PID: $PID)${NC}"
    else
      _start_sh_log "${RED}实时数据服务: 已停止 (PID文件存在但进程不存在)${NC}"
    fi
  else
    _start_sh_log "${YELLOW}实时数据服务: 已停止 (无PID文件)${NC}"
  fi
}
# --- End: Realtime Service Management ---

# 检查是否有虚拟环境
VENV_ACTIVATED=false
if [ -d ".venv" ]; then
    echo -e "${GREEN}[✓] 发现虚拟环境，正在激活...${NC}"
    # 确保激活脚本存在
    if [ -f ".venv/bin/activate" ]; then
        # 强制重新激活虚拟环境，即使已经在虚拟环境中
        deactivate 2>/dev/null || true
        . .venv/bin/activate
        # 验证激活是否成功
        if [[ $(which python) == *".venv"* ]]; then
            echo -e "${GREEN}[✓] 虚拟环境激活成功: $(which python)${NC}"
            VENV_ACTIVATED=true
        else
            echo -e "${RED}[✗] 虚拟环境激活失败，将尝试使用系统Python${NC}"
        fi
    else
        echo -e "${RED}[✗] 虚拟环境激活脚本不存在: .venv/bin/activate${NC}"
    fi
else
    echo -e "${YELLOW}[!] 未发现虚拟环境，使用系统Python环境${NC}"
fi

# 确保必要的依赖已安装
if [ "$VENV_ACTIVATED" = true ]; then
    echo -e "${BLUE}[*] 检查必要的依赖...${NC}"
    # 检查websockets库
    if ! python -c "import websockets" &>/dev/null; then
        echo -e "${YELLOW}[!] 未找到websockets库，正在安装...${NC}"
        pip install websockets
    else
        echo -e "${GREEN}[✓] websockets库已安装${NC}"
    fi
fi

# 默认参数 (can be overridden by command line)
MODE="frontend"
SYMBOL="603486.SH,600919.SH"
START_DATE="2024-01-01"
END_DATE="2025-05-18"
INITIAL_CAPITAL=100000
PORT=5000
DEBUG_MODE="" # Changed from DEBUG="" to avoid issues with "set -u" if enabled
STRATEGY_PARAMS="pyramid_default.yaml"
REALTIME_ACTION=""

# --- Command Line Argument Parsing ---
# Store all args, then process.
ALL_ARGS=("$@")
idx=0
ARGC=$#

# First pass for global mode and special flags
if [[ $ARGC -gt 0 ]]; then
    case "${ALL_ARGS[0]}" in
        init|backtest|optimize|trade|frontend|realtime)
            MODE="${ALL_ARGS[0]}"
            idx=$((idx + 1)) # Consume the mode
            ;;
        --help|-h)
            # Help function will be defined later
            # For now, just set mode to help and exit parsing
            MODE="help"
            idx=$((idx + ARGC)) # Consume all args
            ;;
    esac
fi

# Second pass for mode-specific arguments or general flags
while [[ $idx -lt $ARGC ]]; do
    arg="${ALL_ARGS[$idx]}"
    case $arg in
        # Args for 'realtime' mode
        --action)
            if [[ "$MODE" == "realtime" ]]; then
                REALTIME_ACTION="${ALL_ARGS[$((idx + 1))]}"
                if [[ ! "$REALTIME_ACTION" =~ ^(start|stop|status)$ ]]; then
                    echo -e "${RED}[x] Invalid action for realtime mode: $REALTIME_ACTION. Use start, stop, or status.${NC}"
                    exit 1
                fi
            else
                echo -e "${RED}[x] --action is only valid with 'realtime' mode.${NC}"
                exit 1
            fi
            idx=$((idx + 2))
            ;;
        # General args for main.py
        --symbols)
            SYMBOL="${ALL_ARGS[$((idx + 1))]}"
            idx=$((idx + 2))
            ;;
        --start-date)
            START_DATE="${ALL_ARGS[$((idx + 1))]}"
            idx=$((idx + 2))
            ;;
        --end-date)
            END_DATE="${ALL_ARGS[$((idx + 1))]}"
            idx=$((idx + 2))
            ;;
        --initial-capital)
            INITIAL_CAPITAL="${ALL_ARGS[$((idx + 1))]}"
            idx=$((idx + 2))
            ;;
        --strategy-params)
            STRATEGY_PARAMS="${ALL_ARGS[$((idx + 1))]}"
            idx=$((idx + 2))
            ;;
        --port)
            PORT="${ALL_ARGS[$((idx + 1))]}"
            idx=$((idx + 2))
            ;;
        --debug)
            DEBUG_MODE="--debug" # Set to the actual flag expected by main.py
            idx=$((idx + 1))
            ;;
        *)
            # If mode is already set and it's not 'help', this is an unknown arg for that mode
            if [[ "$MODE" != "help" ]]; then # Avoid erroring on --help itself
                 # If it's an unknown first argument, it might be an attempt to set mode
                if [[ $idx -eq 0 && "$MODE" != "${ALL_ARGS[0]}" ]]; then
                     echo -e "${RED}[x] Unknown mode or option: $arg${NC}"
                elif [[ $idx -gt 0 || "$MODE" == "${ALL_ARGS[0]}" ]]; then # Already past mode or mode was correctly set
                     echo -e "${RED}[x] Unknown option for mode '$MODE': $arg${NC}"
                fi
            fi
            # For now, let help handle unknown args if mode is 'help'
            if [[ "$MODE" != "help" ]]; then
                MODE="help" # Default to help on unknown arg
            fi
            # To prevent infinite loops on unknown args when help is shown:
            # Consume the problematic arg so parsing can continue or help is shown once.
            idx=$((idx + 1))
            break # Break to show help
            ;;
    esac
done
# --- End: Command Line Argument Parsing ---

# Help Function
show_help() {
    echo -e "${BLUE}量化模型个人交易系统 - 统一启动脚本${NC}"
    echo ""
    echo -e "${GREEN}用法:${NC} $0 [mode] [options]"
    echo ""
    echo -e "${YELLOW}可用模式:${NC}"
    echo -e "  init                      初始化项目 (创建目录结构, 安装依赖)"
    echo ""
    echo -e "  realtime                  管理实时数据服务守护进程"
    echo -e "    --action [start|stop|status]  执行操作 (启动/停止/查看状态)"
    echo ""
    echo -e "  backtest                  运行回测"
    echo -e "  optimize                  运行策略优化"
    echo -e "  trade                     运行实盘交易模拟"
    echo -e "  frontend                  启动Web前端界面 (默认模式)"
    echo ""
    echo -e "${YELLOW}各模式通用选项 (当模式为 backtest, optimize, trade, frontend 时):${NC}"
    echo -e "  --symbols <symbol_list>   股票代码列表 (逗号分隔, e.g., "000001.SH,600000.SH")"
    echo -e "                            Default: "$SYMBOL""
    echo -e "  --start-date <YYYY-MM-DD> 开始日期. Default: "$START_DATE""
    echo -e "  --end-date <YYYY-MM-DD>   结束日期. Default: "$END_DATE""
    echo -e "  --initial-capital <amount> 初始资金. Default: $INITIAL_CAPITAL"
    echo -e "  --strategy-params <file.yaml> 策略参数文件名 (在 config/strategy_params/ 下)."
    echo -e "                            Default: "$STRATEGY_PARAMS""
    echo -e "  --port <port_num>         (仅frontend模式) Web服务端口. Default: $PORT"
    echo -e "  --debug                   (仅frontend模式) 启用Flask调试模式"
    echo ""
    echo -e "  --help, -h                显示此帮助信息"
    echo ""
    echo -e "${BLUE}示例:${NC}"
    echo -e "  $0 init"
    echo -e "  $0 realtime --action start"
    echo -e "  $0 realtime --action status"
    echo -e "  $0 backtest --symbols 600519.SH --start-date 2023-01-01"
    echo -e "  $0 frontend --port 8080 --debug"
    exit 0
}


# --- Main Logic ---
if [[ "$MODE" == "help" ]]; then
    show_help
fi

if [[ "$MODE" == "init" ]]; then
    echo -e "${BLUE}[*] 初始化模式执行...${NC}"
    setup_project_directories

    echo -e "${BLUE}[*] 检查并安装项目依赖 (from requirements.txt)...${NC}"
    if [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
        pip install -r "${PROJECT_ROOT}/requirements.txt"
        REQUIREMENTS_INSTALL_STATUS=$?
        if [ $REQUIREMENTS_INSTALL_STATUS -eq 0 ]; then
            echo -e "${GREEN}[✓] requirements.txt 安装完成 (或已满足).${NC}"
        else
            echo -e "${RED}[✗] requirements.txt 安装遇到问题 (退出码: $REQUIREMENTS_INSTALL_STATUS).${NC}"
        fi
    else
        echo -e "${RED}[✗] requirements.txt 未找到于项目根目录!${NC}"
    fi

    echo -e "${GREEN}[✓] 初始化完成.${NC}"

elif [[ "$MODE" == "realtime" ]]; then
    echo -e "${BLUE}[*] 实时数据服务管理模式...${NC}"
    if [[ -z "$REALTIME_ACTION" ]]; then
        echo -e "${RED}[✗] --action [start|stop|status] 必须为realtime模式指定!${NC}"
        show_help
        exit 1
    fi
    case "$REALTIME_ACTION" in
        start) start_realtime_daemon ;;
        stop)  stop_realtime_daemon ;;
        status) status_realtime_daemon ;;
    esac
    echo -e "${GREEN}[✓] 实时数据服务操作 '$REALTIME_ACTION' 完成.${NC}"

elif [[ "$MODE" == "backtest" || "$MODE" == "optimize" || "$MODE" == "trade" || "$MODE" == "frontend" ]]; then
    echo -e "${BLUE}[*] 应用程序模式: ${MODE}${NC}"
    
    # Dependency checks (example from old start.sh) - now primarily a quick check
    echo -e "${BLUE}[*] 快速检查核心依赖 (akshare)...${NC}"
    if ! python -c "import akshare" &> /dev/null; then
        echo -e "${YELLOW}[!] 未找到AKShare。请先运行 './start.sh init' 来安装所有依赖。${NC}"
        # Optionally, you could offer to run pip install here again, but init should be the primary way.
        # pip install akshare --upgrade 
    else
        echo -e "${GREEN}[✓] AKShare已找到.${NC}"
    fi

    # Ensure necessary output directories (some might be created by setup_project_directories if init was run)
    # For safety, specific ones used by main.py could be re-ensured here if not covered by init.
    # setup_project_directories # Calling this here ensures dirs exist even if 'init' wasn't run first.

    echo -e "${BLUE}[*] 系统配置:${NC}"
    echo -e "  - 运行模式: ${YELLOW}${MODE}${NC}"
    echo -e "  - 股票代码: ${YELLOW}${SYMBOL}${NC}"
    echo -e "  - 开始日期: ${YELLOW}${START_DATE}${NC}"
    echo -e "  - 结束日期: ${YELLOW}${END_DATE}${NC}"
    echo -e "  - 初始资金: ${YELLOW}${INITIAL_CAPITAL}${NC}"
    echo -e "  - 策略参数: ${YELLOW}${STRATEGY_PARAMS}${NC}"
    if [[ "$MODE" == "frontend" ]]; then
        echo -e "  - 端口: ${YELLOW}${PORT}${NC}"
        if [[ -n "$DEBUG_MODE" ]]; then
             echo -e "  - 调试模式: ${YELLOW}启用${NC}"
        fi
    fi
    
    CMD_MAIN_PY="python main.py --mode $MODE"
    if [[ "$MODE" == "frontend" ]]; then
        CMD_MAIN_PY="$CMD_MAIN_PY --port $PORT $DEBUG_MODE"
    else # Common args for backtest, optimize, trade
        CMD_MAIN_PY="$CMD_MAIN_PY --symbols "$SYMBOL" --start-date "$START_DATE" --end-date "$END_DATE" --initial-capital $INITIAL_CAPITAL --strategy-params "$STRATEGY_PARAMS""
    fi
    
    echo -e "${BLUE}[*] 启动应用程序 (${MODE})...${NC}"
    echo -e "${BLUE}----------------------------------------${NC}"
    eval "$CMD_MAIN_PY" # Use eval if args can contain quotes or spaces that need careful handling
    EXIT_STATUS=$?
    echo -e "${BLUE}----------------------------------------${NC}"
    if [ $EXIT_STATUS -eq 0 ]; then
        echo -e "${GREEN}[✓] 应用程序 (${MODE}) 正常退出${NC}"
    else
        echo -e "${RED}[✗] 应用程序 (${MODE}) 异常退出，退出码: ${EXIT_STATUS}${NC}"
    fi

else
    echo -e "${RED}[✗] 未知或未处理的模式: $MODE${NC}"
    show_help
    exit 1
fi

# 如果激活了虚拟环境，则退出
if [[ "$VENV_ACTIVATED" == true ]]; then
    echo -e "${BLUE}[*] 退出虚拟环境...${NC}"
    deactivate
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}脚本执行完毕.${NC}"
exit 0 