# Prompts for market analysis and signal generation

def get_market_sentiment_prompt(news_headlines, market_data_summary):
    return f"""
    Analyze the following market information and determine the overall sentiment (Bullish, Bearish, Neutral).
    Provide a confidence score from 0.0 to 1.0 and a brief justification.

    News Headlines:
    {news_headlines}

    Recent Market Data Summary:
    {market_data_summary}

    Sentiment:
    Confidence:
    Justification:
    """

def get_trade_signal_prompt(asset_name, technical_analysis, sentiment_analysis):
    return f"""
    Based on the following analysis for {asset_name}, recommend a trading action (BUY, SELL, HOLD).
    Provide a confidence score (0.0 to 1.0) and a brief reasoning.

    Technical Analysis:
    {technical_analysis}

    Sentiment Analysis:
    {sentiment_analysis}

    Recommended Action:
    Confidence:
    Reasoning:
    """ 