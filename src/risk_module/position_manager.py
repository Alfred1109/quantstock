# Manages position sizing and overall portfolio risk.

class PositionManager:
    def __init__(self, portfolio_cash, max_risk_per_trade_pct, max_portfolio_risk_pct):
        self.portfolio_cash = portfolio_cash
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        print("PositionManager initialized.")

    def calculate_position_size(self, symbol, entry_price, stop_loss_price, signal_confidence=1.0):
        """Calculates the number of shares to trade based on risk parameters."""
        if stop_loss_price >= entry_price and signal_confidence > 0: # Assuming long trade for simplicity
            print("Warning: Stop loss must be below entry price for a long trade.")
            return 0
        if entry_price <= 0:
             return 0

        risk_per_share = entry_price - stop_loss_price
        if risk_per_share <= 0:
            print("Warning: Risk per share is zero or negative.")
            return 0

        # Max cash to risk on this trade
        trade_risk_cash = self.portfolio_cash * self.max_risk_per_trade_pct * signal_confidence
        
        # Number of shares
        position_size = int(trade_risk_cash / risk_per_share)
        
        # Ensure this trade doesn't exceed overall portfolio risk (simplified)
        # A more complete check would involve current open positions and their risk.
        # For now, let's assume this is the only trade or portfolio risk is managed elsewhere.

        print(f"Calculated position size for {symbol}: {position_size} shares.")
        return position_size

    def check_portfolio_risk(self, current_positions):
        """Checks if overall portfolio risk is within limits."""
        # Placeholder for more complex portfolio risk calculation
        print("Portfolio risk check to be implemented.")
        return True 