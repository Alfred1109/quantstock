# Functions to parse LLM text output into structured signals
import re

def parse_trade_signal(llm_output_text):
    """Parses LLM text to extract action, confidence, and reasoning."""
    action = None
    confidence = None
    reasoning = ""

    # Example parsing logic (highly dependent on LLM output format)
    action_match = re.search(r"Recommended Action:\s*(BUY|SELL|HOLD)", llm_output_text, re.IGNORECASE)
    if action_match:
        action = action_match.group(1).upper()

    confidence_match = re.search(r"Confidence:\s*([0-1]\.\d+)", llm_output_text, re.IGNORECASE)
    if confidence_match:
        try:
            confidence = float(confidence_match.group(1))
        except ValueError:
            pass # Keep confidence as None if conversion fails
    
    reasoning_match = re.search(r"Reasoning:(.*)", llm_output_text, re.IGNORECASE | re.DOTALL)
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()

    if not action: # Fallback or more robust parsing needed
        print(f"Warning: Could not parse action from LLM output: {llm_output_text}")
        return {"action": "HOLD", "confidence": 0.0, "reasoning": "Parsing failed."}

    return {"action": action, "confidence": confidence, "reasoning": reasoning}

def parse_sentiment_analysis(llm_output_text):
    """Parses LLM text to extract sentiment, confidence, and justification."""
    sentiment = None
    confidence = None
    justification = ""

    sentiment_match = re.search(r"Sentiment:\s*(Bullish|Bearish|Neutral)", llm_output_text, re.IGNORECASE)
    if sentiment_match:
        sentiment = sentiment_match.group(1).capitalize()
    
    confidence_match = re.search(r"Confidence:\s*([0-1]\.\d+)", llm_output_text, re.IGNORECASE)
    if confidence_match:
        try:
            confidence = float(confidence_match.group(1))
        except ValueError:
            pass
            
    justification_match = re.search(r"Justification:(.*)", llm_output_text, re.IGNORECASE | re.DOTALL)
    if justification_match:
        justification = justification_match.group(1).strip()

    if not sentiment: # Fallback or more robust parsing needed
        print(f"Warning: Could not parse sentiment from LLM output: {llm_output_text}")
        return {"sentiment": "Neutral", "confidence": 0.0, "justification": "Parsing failed."}

    return {"sentiment": sentiment, "confidence": confidence, "justification": justification} 