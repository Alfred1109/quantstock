/**
 * 量化交易系统前端交互脚本
 */

document.addEventListener('DOMContentLoaded', function() {
    // 检查系统状态
    checkSystemStatus();
    
    // 加载交易标的
    loadSymbols();
    
    // 初始化图表控制按钮的事件监听器
    setupChartControls();
    
    // 每30秒更新一次系统状态
    setInterval(checkSystemStatus, 30000);
});

/**
 * 检查系统状态
 */
function checkSystemStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            if (data.code === 0) {
                updateStatusDisplay('api-status', data.data.api);
                updateStatusDisplay('backtest-status', data.data.backtest);
            }
        })
        .catch(error => {
            console.error('检查系统状态出错:', error);
            updateStatusDisplay('api-status', false);
            updateStatusDisplay('backtest-status', false);
        });
}

/**
 * 更新状态显示
 */
function updateStatusDisplay(elementId, isActive) {
    const element = document.getElementById(elementId);
    if (element) {
        element.className = isActive ? 'status active' : 'status inactive';
        element.textContent = isActive ? '在线' : '离线';
    }
}

/**
 * 加载交易标的列表
 */
function loadSymbols() {
    fetch('/api/symbols')
        .then(response => response.json())
        .then(data => {
            if (data.code === 0) {
                displaySymbols(data.data);
            } else {
                throw new Error(data.message || '加载交易标的失败');
            }
        })
        .catch(error => {
            console.error('加载交易标的出错:', error);
            document.getElementById('symbol-list').innerHTML = `
                <div class="loading">无法加载数据: ${error.message}</div>
            `;
        });
}

/**
 * 显示交易标的列表
 */
function displaySymbols(symbols) {
    const symbolList = document.getElementById('symbol-list');
    symbolList.innerHTML = '';
    
    if (!symbols || symbols.length === 0) {
        symbolList.innerHTML = '<div class="loading">暂无交易标的</div>';
        return;
    }
    
    symbols.forEach(item => {
        const li = document.createElement('li');
        li.className = 'symbol-item';
        li.dataset.symbol = item.code;
        
        const priceClass = Math.random() > 0.5 ? 'price-up' : 'price-down';
        const priceChange = Math.random() > 0.5 ? '+' : '-';
        const priceValue = (Math.random() * 2).toFixed(2);
        
        li.innerHTML = `
            <span class="symbol-name">${item.code}</span> - ${item.name}
            <span class="symbol-price ${priceClass}">${priceChange}${priceValue}%</span>
        `;
        
        li.addEventListener('click', function() {
            // 选中当前项
            document.querySelectorAll('.symbol-item').forEach(el => {
                el.classList.remove('selected');
            });
            li.classList.add('selected');
            
            // 获取K线数据
            loadKlineData(item.code);
        });
        
        symbolList.appendChild(li);
    });
    // 为LLM策略建议按钮添加事件监听器（如果存在）
    const llmSuggestionButton = document.getElementById('get-llm-suggestion-btn');
    if (llmSuggestionButton) {
        llmSuggestionButton.addEventListener('click', function() {
            const selectedSymbolItem = document.querySelector('.symbol-item.selected');
            if (selectedSymbolItem) {
                const symbol = selectedSymbolItem.dataset.symbol;
                getLlmSuggestion(symbol);
            }
        });
    }
}

/**
 * 加载K线数据
 */
function loadKlineData(symbol) {
    document.getElementById('chart-symbol').textContent = symbol;
    
    // 显示图表容器和加载状态
    const chartContainer = document.getElementById('chart-container');
    chartContainer.innerHTML = `
        <div class="loading">加载 ${symbol} 的图表数据...</div>
    `;
    
    // 如果有之前的图表，先清除
    if (window.priceChart) {
        window.priceChart.destroy();
        window.priceChart = null;
    }
    
    // 显示LLM建议按钮
    const llmSuggestionButton = document.getElementById('get-llm-suggestion-btn');
    if (llmSuggestionButton) {
        llmSuggestionButton.style.display = 'inline-block';
    }
    
    // 清除之前的LLM建议
    const llmSuggestionContainer = document.getElementById('llm-suggestion-container');
    if (llmSuggestionContainer) {
        llmSuggestionContainer.innerHTML = '';
    }
    
    // 获取当前选中的图表周期
    const activeChartPeriodBtn = document.querySelector('.chart-period-btn.active');
    const chartPeriod = activeChartPeriodBtn ? activeChartPeriodBtn.dataset.period : 'day';
    
    console.log(`加载${symbol}的${chartPeriod}周期数据`);
    
    fetch(`/api/kline/${symbol}?period=${chartPeriod}`)
        .then(response => response.json())
        .then(data => {
            if (data.code === 0) {
                console.log(`成功获取数据: ${symbol}，周期: ${chartPeriod}，数据点数量:`, data.data ? data.data.length : 0);
                // 数据调试
                if (data.data && data.data.length > 0) {
                    console.log('数据样例:', data.data[0]);
                }
                displayKlineData(data.data, symbol);
            } else {
                throw new Error(data.message || 'K线数据加载失败');
            }
        })
        .catch(error => {
            console.error('加载K线数据出错:', error);
            const chartContainer = document.getElementById('chart-container');
            if (chartContainer) {
                chartContainer.innerHTML = `
                    <div class="loading">加载失败: ${error.message}</div>
                `;
            }
        });
}

/**
 * 显示K线数据
 */
function displayKlineData(klineData, symbol) {
    // 准备图表容器
    const chartContainer = document.getElementById('chart-container');
    if (!chartContainer) {
        console.error('图表容器未找到!');
        return;
    }

    // 确保容器中有canvas元素
    chartContainer.innerHTML = '<canvas id="price-chart"></canvas>';
    const canvas = document.getElementById('price-chart');
    
    // 检查数据
    if (!klineData || klineData.length === 0) {
        chartContainer.innerHTML = `<div class="loading">无K线数据可显示</div>`;
        return;
    }

    // 获取当前选中的图表类型和周期
    const activeChartTypeBtn = document.querySelector('.chart-type-btn.active');
    const activeChartPeriodBtn = document.querySelector('.chart-period-btn.active');

    const chartType = activeChartTypeBtn ? activeChartTypeBtn.dataset.type : 'candlestick';
    const chartPeriod = activeChartPeriodBtn ? activeChartPeriodBtn.dataset.period : 'day';
    
    console.log(`图表类型: ${chartType}, 周期: ${chartPeriod}`);

    try {
        // 处理数据
        const labels = [];
        const prices = [];
        const opens = [];
        const highs = [];
        const lows = [];
        const closes = [];
        
        // 按时间排序数据
        klineData.sort((a, b) => {
            const dateA = new Date(a.date);
            const dateB = new Date(b.date);
            return dateA - dateB;
        });
        
        // 提取数据点
        klineData.forEach(item => {
            const date = new Date(item.date);
            labels.push(date.toLocaleDateString('zh-CN'));
            opens.push(parseFloat(item.open));
            highs.push(parseFloat(item.high));
            lows.push(parseFloat(item.low));
            closes.push(parseFloat(item.close));
            prices.push(parseFloat(item.close)); // 使用收盘价作为价格
        });
        
        // 创建图表数据
        const data = {
            labels: labels,
            datasets: []
        };
        
        // 根据图表类型添加不同的数据集
        if (chartType === 'line') {
            // 折线图
            data.datasets.push({
                label: `${symbol} 价格`,
                data: prices,
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1,
                borderWidth: 2,
                pointRadius: 1
            });
        } else {
            // 蜡烛图 - 我们不能真正绘制蜡烛图，但可以用柱状图模拟
            // 绘制高低价范围
            data.datasets.push({
                label: '价格范围',
                data: highs.map((h, i) => h - lows[i]),
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                borderColor: 'rgb(75, 192, 192)',
                borderWidth: 1,
                barPercentage: 0.5,
                categoryPercentage: 0.8,
                yAxisID: 'y'
            });
            
            // 绘制开盘收盘价
            data.datasets.push({
                label: '收盘价',
                data: closes,
                type: 'line',
                borderColor: 'rgb(255, 99, 132)',
                borderWidth: 2,
                pointRadius: 0,
                yAxisID: 'y'
            });
        }
        
        // 图表配置
        const config = {
            type: chartType === 'line' ? 'line' : 'bar',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: `${symbol} ${chartPeriod === 'day' ? '日线' : (chartPeriod === 'week' ? '周线' : '月线')}`
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                const dataIndex = context.dataIndex;
                                if (chartType !== 'line') {
                                    return [
                                        `开盘: ${opens[dataIndex]}`,
                                        `最高: ${highs[dataIndex]}`,
                                        `最低: ${lows[dataIndex]}`,
                                        `收盘: ${closes[dataIndex]}`
                                    ];
                                }
                                return `${context.dataset.label}: ${context.parsed.y}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: '日期'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: '价格'
                        }
                    }
                }
            }
        };
        
        // 创建图表
        window.priceChart = new Chart(canvas, config);
        
        console.log('图表创建成功:', symbol);
    } catch (error) {
        console.error('图表渲染错误:', error);
        chartContainer.innerHTML = `<div class="loading">图表渲染失败: ${error.message}</div>`;
    }
}

/**
 * 获取并显示LLM策略建议
 */
function getLlmSuggestion(symbol) {
    const container = document.getElementById('llm-suggestion-container');
    if (!container) return;

    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <p>正在获取 ${symbol} 的LLM策略建议...</p>
            <p class="hint">首次分析可能需要1-2分钟，请耐心等待</p>
        </div>`;

    fetch(`/api/llm_strategy_suggestion/${symbol}`)
        .then(response => {
            if (!response.ok) {
                // 尝试解析后端返回的错误详情
                return response.json().then(errData => {
                    throw new Error(errData.message || `HTTP error ${response.status}`);
                }).catch(() => {
                     throw new Error(`HTTP error ${response.status}`); // 如果错误响应不是JSON，使用这个默认错误信息
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.code === 0 && data.data) {
                displayLlmSuggestion(data.data);
            } else {
                throw new Error(data.message || '获取LLM建议失败');
            }
        })
        .catch(error => {
            console.error(`获取LLM建议出错 (${symbol}):`, error);
            
            // 提供更友好的错误信息
            let errorMessage = error.message || '未知错误';
            let userFriendlyMessage = '';
            let troubleshootTips = [];
            
            // 根据错误类型提供具体建议
            if (errorMessage.includes('LLMEnhancedStrategy')) {
                userFriendlyMessage = '无法创建大模型策略分析实例';
                troubleshootTips = [
                    '请确认已正确配置AI模型接口',
                    '检查服务器日志获取详细错误信息',
                    '可能需要重启AI服务组件'
                ];
            } else if (errorMessage.includes('HTTP error 404')) {
                userFriendlyMessage = 'LLM策略分析API不可用';
                troubleshootTips = [
                    '确认后端API服务已启动',
                    '检查API路由配置是否正确'
                ];
            } else if (errorMessage.includes('HTTP error')) {
                userFriendlyMessage = '连接服务器失败，请检查网络或服务器状态';
                troubleshootTips = [
                    '确认API服务器运行状态',
                    '检查网络连接'
                ];
            } else if (errorMessage.includes('timeout')) {
                userFriendlyMessage = '请求超时，大模型分析可能需要更长时间';
                troubleshootTips = [
                    '请稍后再试',
                    '检查服务器负载情况'
                ];
            } else {
                userFriendlyMessage = '无法获取策略建议，请稍后再试';
                troubleshootTips = [
                    '刷新页面后重试',
                    '联系系统管理员'
                ];
            }
            
            // 构建错误提示HTML
            let errorHtml = `
                <div class="loading error">
                    <h3>💡 ${userFriendlyMessage}</h3>
                    <p class="error-detail">技术详情: ${errorMessage}</p>
                    <div class="troubleshoot-tips">
                        <p><strong>可能的解决方法:</strong></p>
                        <ul>`;
            
            troubleshootTips.forEach(tip => {
                errorHtml += `<li>${tip}</li>`;
            });
            
            errorHtml += `
                        </ul>
                    </div>
                    <button class="retry-btn" onclick="getLlmSuggestion('${symbol}')">重试</button>
                </div>`;
            
            container.innerHTML = errorHtml;
        });
}

/**
 * 显示LLM策略建议到UI
 */
function displayLlmSuggestion(suggestion) {
    const container = document.getElementById('llm-suggestion-container');
    if (!container) return;

    let html = '<h3>大模型策略建议</h3>';
    html += `<p><span class="label">交易信号:</span> <span class="value signal-${suggestion.signal?.toLowerCase()}">${suggestion.signal || '未知'}</span></p>`;
    html += `<p><span class="label">置信度:</span> <span class="value confidence-${suggestion.confidence?.toLowerCase()}">${suggestion.confidence || '未知'}</span></p>`;
    html += `<p><span class="label">时间框架:</span> <span class="value">${suggestion.timeframe || '未知'}</span></p>`;
    
    if (suggestion.entry_price !== null && suggestion.entry_price !== undefined) {
        html += `<p><span class="label">建议入场价:</span> <span class="value">${suggestion.entry_price.toFixed(2)}</span></p>`;
    }
    if (suggestion.stop_loss !== null && suggestion.stop_loss !== undefined) {
        html += `<p><span class="label">止损价格:</span> <span class="value price-down">${suggestion.stop_loss.toFixed(2)}</span></p>`;
    }
    if (suggestion.take_profit !== null && suggestion.take_profit !== undefined) {
        html += `<p><span class="label">止盈价格:</span> <span class="value price-up">${suggestion.take_profit.toFixed(2)}</span></p>`;
    }
    if (suggestion.position_size !== null && suggestion.position_size !== undefined) {
        html += `<p><span class="label">建议仓位:</span> <span class="value">${(suggestion.position_size * 100).toFixed(1)}%</span></p>`;
    }
    
    html += `<div class="reasoning"><span class="label">分析与理由:</span><br>${suggestion.reasoning || '无详细理由'}</div>`;
    
    // 为建议添加时间戳
    if (suggestion.timestamp) {
        const date = new Date(suggestion.timestamp * 1000);
        html += `<p style="font-size:0.8em; color: #7f8c8d; text-align:right; margin-top:10px;">建议生成于: ${date.toLocaleString()}</p>`;
    }

    container.innerHTML = html;
}

/**
 * 初始化图表控制按钮 (类型和周期切换)
 */
function setupChartControls() {
    const symbolList = document.getElementById('symbol-list');
    let currentSelectedSymbol = null;

    // 监听symbol-list的变化，以便在加载新symbol后能正确获取
    // 或者在 loadKlineData 成功后记录当前 symbol
    // 简单起见，我们假设 loadKlineData 会设置一个全局可访问的当前 symbol，或者我们从UI读取

    document.querySelectorAll('.chart-type-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.chart-type-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            const selectedSymbolItem = document.querySelector('.symbol-item.selected');
            if (selectedSymbolItem) {
                currentSelectedSymbol = selectedSymbolItem.dataset.symbol;
                loadKlineData(currentSelectedSymbol);
            } else {
                console.warn('没有选中的交易标的，无法更改图表类型。');
            }
        });
    });
    
    document.querySelectorAll('.chart-period-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.chart-period-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const selectedSymbolItem = document.querySelector('.symbol-item.selected');
            if (selectedSymbolItem) {
                currentSelectedSymbol = selectedSymbolItem.dataset.symbol;
                loadKlineData(currentSelectedSymbol);
            } else {
                console.warn('没有选中的交易标的，无法更改图表周期。');
            }
        });
    });

    console.log('图表控制按钮初始化完成。');
}

/**
 * 交易系统相关功能
 */
function initializeTradingPage() {
    // 仅在交易页面才初始化这些功能
    if (!window.location.pathname.includes('/trading')) {
        return;
    }
    
    console.log("初始化交易页面...");
    
    // 模拟数据示例
    
    // 模拟获取持仓数据
    window.mockPositionsData = {
        positions: [
            {
                symbol: "603486.SH",
                name: "科沃斯",
                quantity: 300,
                entry_price: "118.50",
                current_price: "123.75",
                profit_loss: "+5.25 (4.43%)"
            },
            {
                symbol: "600919.SH",
                name: "江苏银行",
                quantity: 1000,
                entry_price: "7.45",
                current_price: "7.38",
                profit_loss: "-0.07 (-0.94%)"
            }
        ]
    };
    
    // 模拟获取信号数据
    window.mockSignalsData = {
        signals: [
            {
                symbol: "603486.SH",
                name: "科沃斯",
                action: "BUY",
                time: "2023-05-18 09:45:32",
                price: "118.50",
                reason: "交叉突破策略信号",
                executed: true
            },
            {
                symbol: "600919.SH",
                name: "江苏银行",
                action: "BUY",
                time: "2023-05-18 10:15:13",
                price: "7.45",
                reason: "动量策略信号",
                executed: true
            },
            {
                symbol: "603486.SH",
                name: "科沃斯",
                action: "SELL",
                time: "2023-05-18 14:32:01",
                price: "123.75",
                reason: "止盈触发",
                executed: false
            }
        ]
    };
    
    // 模拟状态数据
    window.mockStatusData = {
        is_active: true,
        last_signal_time: "2023-05-18 14:32:01",
        active_orders: 1,
        time: new Date().toLocaleString()
    };
    
    // 重写API函数，使用模拟数据
    if (typeof refreshPositions === 'function') {
        const originalRefreshPositions = refreshPositions;
        window.refreshPositions = function() {
            console.log("获取持仓数据...");
            
            // 检查是否有API端点返回真实数据
            $.ajax({
                url: '/api/trading/positions',
                type: 'GET',
                timeout: 3000,
                success: function(response) {
                    console.log("成功获取真实持仓数据");
                    renderPositions(response);
                },
                error: function() {
                    console.log("使用模拟持仓数据");
                    renderPositions(window.mockPositionsData);
                }
            });
        };
    }
    
    if (typeof refreshSignals === 'function') {
        const originalRefreshSignals = refreshSignals;
        window.refreshSignals = function() {
            console.log("获取信号数据...");
            
            // 检查是否有API端点返回真实数据
            $.ajax({
                url: '/api/trading/signals',
                type: 'GET',
                timeout: 3000,
                success: function(response) {
                    console.log("成功获取真实信号数据");
                    renderSignals(response);
                },
                error: function() {
                    console.log("使用模拟信号数据");
                    renderSignals(window.mockSignalsData);
                }
            });
        };
    }
    
    if (typeof refreshSystemStatus === 'function') {
        const originalRefreshSystemStatus = refreshSystemStatus;
        window.refreshSystemStatus = function() {
            console.log("获取系统状态...");
            
            // 检查是否有API端点返回真实数据
            $.ajax({
                url: '/api/trading/status',
                type: 'GET',
                timeout: 3000,
                success: function(response) {
                    console.log("成功获取真实系统状态");
                    renderSystemStatus(response);
                },
                error: function() {
                    console.log("使用模拟系统状态数据");
                    // 更新时间戳
                    window.mockStatusData.time = new Date().toLocaleString();
                    renderSystemStatus(window.mockStatusData);
                }
            });
        };
    }
    
    // 渲染函数
    function renderPositions(data) {
        var html = '';
        
        if(data.positions.length === 0) {
            html = '<div class="alert alert-warning">当前无持仓</div>';
        } else {
            html = '<table class="position-table">';
            html += '<thead><tr><th>股票</th><th>数量</th><th>成本</th><th>现价</th><th>盈亏</th></tr></thead>';
            html += '<tbody>';
            
            data.positions.forEach(function(position) {
                // 判断是盈利还是亏损
                const profitClass = position.profit_loss.includes('-') ? 'loss' : 'profit';
                
                html += '<tr>';
                html += '<td><strong>' + position.symbol + '</strong></td>';
                html += '<td>' + position.quantity + '</td>';
                html += '<td>' + position.entry_price + '</td>';
                html += '<td>' + position.current_price + '</td>';
                html += '<td class="' + profitClass + '">' + position.profit_loss + '</td>';
                html += '</tr>';
            });
            
            html += '</tbody></table>';
        }
        
        $("#positions-container").html(html);
    }
    
    function renderSignals(data) {
        var html = '';
        
        if(data.signals.length === 0) {
            html = '<div class="alert alert-warning">暂无交易信号</div>';
        } else {
            data.signals.forEach(function(signal) {
                var signalClass = signal.action === 'BUY' ? 'signal-buy' : 'signal-sell';
                var actionIcon = signal.action === 'BUY' ? '<i class="bi bi-arrow-up-circle-fill"></i>' : '<i class="bi bi-arrow-down-circle-fill"></i>';
                var actionText = signal.action === 'BUY' ? '买入' : '卖出';
                
                html += '<div class="signal-item ' + signalClass + '" data-aos="fade-left">';
                html += '<div class="signal-time">' + signal.time + '</div>';
                html += '<div class="signal-title">' + actionIcon + ' ' + signal.symbol + ' - ' + actionText + '</div>';
                html += '<div class="signal-detail">价格: ' + signal.price + '</div>';
                html += '<div class="signal-detail">原因: ' + signal.reason + '</div>';
                html += '<div class="mt-2">';
                html += '<span class="signal-status">' + (signal.executed ? '已执行' : '待执行') + '</span>';
                html += '</div>';
                html += '</div>';
            });
        }
        
        $("#signals-container").html(html);
    }
    
    function renderSystemStatus(response) {
        if(response.is_active) {
            $("#trading-status").html('<i class="bi bi-play-circle-fill"></i> <span>运行中</span>')
                .removeClass("inactive").addClass("active");
        } else {
            $("#trading-status").html('<i class="bi bi-stop-circle-fill"></i> <span>已停止</span>')
                .removeClass("active").addClass("inactive");
        }
        
        $("#last-signal-time").text(response.last_signal_time);
        $("#active-orders").text(response.active_orders);
        $("#system-time").text(response.time);
    }
}

// 页面加载完成后初始化
$(document).ready(function() {
    // ... existing code ...
    
    // 初始化交易页面
    initializeTradingPage();
}); 