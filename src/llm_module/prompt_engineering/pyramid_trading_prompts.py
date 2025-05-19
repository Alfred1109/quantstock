"""
专门用于金字塔交易策略的提示模板。
这些模板用于指导大模型分析市场并生成适用于金字塔交易法的信号。
"""

def get_market_trend_analysis_prompt(
    ticker: str,
    price_data: str,
    volume_data: str,
    technical_indicators: str,
    news_headlines: str = ""
) -> str:
    """
    生成用于市场趋势分析的提示。
    该分析是金字塔交易的基础，用于确定市场总体趋势方向。
    
    Args:
        ticker: 股票代码
        price_data: 价格数据摘要（可能包含开盘、收盘、最高、最低价等）
        volume_data: 成交量数据摘要
        technical_indicators: 技术指标摘要（如MACD、RSI、均线等）
        news_headlines: 相关新闻标题，默认为空
        
    Returns:
        格式化的提示文本
    """
    # 修复f-string中嵌套表达式的反斜杠问题
    news_section = f"相关新闻:\n{news_headlines}" if news_headlines else ""
    
    return f"""
作为一名专业的量化交易分析师，请根据以下信息分析{ticker}的市场趋势。

价格数据:
{price_data}

成交量数据:
{volume_data}

技术指标:
{technical_indicators}

{news_section}

请分析市场总体趋势，并给出以下内容:

1. 市场趋势判断 (必须明确回答: 上升趋势/下降趋势/横盘整理)
2. 趋势强度评分 (1-10，其中10为最强)
3. 趋势可能持续的时间范围
4. 关键支撑位和阻力位
5. 支持你判断的关键因素分析

回答必须符合以下格式:
趋势: [上升趋势/下降趋势/横盘整理]
强度评分: [1-10的数字]
趋势持续性: [短期/中期/长期] - [估计持续时间]
关键支撑位: [价格水平1], [价格水平2]
关键阻力位: [价格水平1], [价格水平2]
分析依据:
[简要分析，200字以内]
"""

def get_entry_point_prompt(
    ticker: str,
    price_data: str,
    overall_trend: str,
    recent_price_action: str,
    technical_indicators: str
) -> str:
    """
    生成用于寻找入场点的提示。
    金字塔交易法要求在趋势方向上寻找高概率入场点。
    
    Args:
        ticker: 股票代码
        price_data: 价格数据摘要
        overall_trend: 总体趋势描述
        recent_price_action: 近期价格走势描述
        technical_indicators: 技术指标摘要
        
    Returns:
        格式化的提示文本
    """
    return f"""
作为金字塔交易策略专家，请为{ticker}分析最佳的入场点。

总体趋势:
{overall_trend}

近期价格走势:
{recent_price_action}

当前价格数据:
{price_data}

技术指标:
{technical_indicators}

请根据金字塔交易法则，分析最佳入场点。金字塔交易强调在趋势方向上分批建仓，逐步加仓。

回答必须包含以下内容:
1. 是否此时适合入场 (必须明确回答: 是/否)
2. 建议的入场价格区间
3. 建议的初始仓位大小 (占总资金的百分比)
4. 止损位置
5. 入场信号的可信度评分 (1-10)
6. 入场理由分析

回答必须符合以下格式:
入场决策: [是/否]
入场价格区间: [价格下限]-[价格上限]
初始仓位: [百分比]
止损位: [价格]
信号可信度: [1-10的数字]
入场理由:
[简要分析，不超过150字]
"""

def get_position_sizing_prompt(
    ticker: str,
    current_trend: str,
    current_position: str,
    risk_metrics: str,
    account_info: str,
    price_volatility: str
) -> str:
    """
    生成用于仓位管理的提示。
    金字塔交易法的核心在于仓位管理，根据趋势强度增加或减少仓位。
    
    Args:
        ticker: 股票代码
        current_trend: 当前趋势描述
        current_position: 当前持仓情况
        risk_metrics: 风险度量指标
        account_info: 账户信息（如可用资金等）
        price_volatility: 价格波动性描述
        
    Returns:
        格式化的提示文本
    """
    return f"""
作为金字塔交易的仓位管理专家，请为{ticker}提供仓位调整建议。

当前趋势:
{current_trend}

当前持仓:
{current_position}

风险指标:
{risk_metrics}

账户信息:
{account_info}

价格波动性:
{price_volatility}

请根据金字塔交易法则，提供仓位管理建议。金字塔交易强调在趋势确认后逐步加仓，趋势减弱时减仓。

回答必须包含以下内容:
1. 建议操作 (必须明确回答: 加仓/减仓/维持/清仓)
2. 如果建议加仓，建议的加仓百分比
3. 如果建议减仓，建议的减仓百分比
4. 此次操作后的总仓位占比
5. 本次调整的理由
6. 调整后的新止损位

回答必须符合以下格式:
建议操作: [加仓/减仓/维持/清仓]
操作百分比: [数字]%
操作后总仓位: [数字]%
新止损位: [价格]
操作理由:
[简要分析，不超过150字]
"""

def get_exit_strategy_prompt(
    ticker: str,
    entry_price: float,
    current_price: float,
    current_trend: str,
    profit_metrics: str,
    technical_warnings: str,
    position_details: str
) -> str:
    """
    生成用于制定退出策略的提示。
    金字塔交易法要求明确的退出条件，保护利润。
    
    Args:
        ticker: 股票代码
        entry_price: 入场价格
        current_price: 当前价格
        current_trend: 当前趋势描述
        profit_metrics: 盈利指标
        technical_warnings: 技术面预警信号
        position_details: 持仓详情
        
    Returns:
        格式化的提示文本
    """
    return f"""
作为金字塔交易策略的退出专家，请为{ticker}的持仓制定退出策略。

入场价格: {entry_price}
当前价格: {current_price}
当前盈亏: {((current_price - entry_price) / entry_price * 100):.2f}%

当前趋势:
{current_trend}

盈利指标:
{profit_metrics}

技术预警信号:
{technical_warnings}

持仓详情:
{position_details}

请根据金字塔交易法则，制定退出策略。金字塔交易强调在趋势反转信号出现时分批退出。

回答必须包含以下内容:
1. 是否应该退出部分或全部仓位 (必须明确回答: 是/否)
2. 如果建议退出，建议退出的百分比
3. 退出价格区间
4. 剩余仓位的新止损位
5. 退出的触发条件
6. 退出建议的置信度 (1-10)

回答必须符合以下格式:
退出决策: [是/否]
退出比例: [数字]%
退出价格区间: [价格下限]-[价格上限]
新止损位: [价格]
触发条件:
[具体条件描述]
置信度: [1-10的数字]
建议理由:
[简要分析，不超过150字]
""" 