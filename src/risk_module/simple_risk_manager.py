import logging
from typing import Dict, Any, Tuple, Optional, List
import numpy as np # For potential use if advanced calculations are kept
# import pandas as pd # Not immediately needed for core logic migration
from datetime import datetime, timedelta

from .base_risk_manager import BaseRiskManager
# from portfolio_module.portfolio import Portfolio # For type hinting if portfolio object passed directly

logger = logging.getLogger('app') # Or getLogger(__name__)

class SimpleRiskManager(BaseRiskManager):
    """
    增强的风险管理器，整合了原 RiskController 的功能。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Parameters from RiskController, to be sourced from self.config
        self.initial_capital: float = self.config.get('initial_capital', 100000.0) # Should be set by engine/portfolio
        self.current_capital: float = self.initial_capital
        self.high_water_mark: float = self.initial_capital
        
        self.max_risk_per_trade_pct: float = self.config.get('max_risk_per_trade_pct', 0.02) # Renamed for clarity
        self.max_total_risk_pct: float = self.config.get('max_total_risk_pct', 0.05) # Renamed for clarity
        self.max_drawdown_limit_pct: float = self.config.get('max_drawdown_limit_pct', 0.1) # Renamed for clarity
        
        # Position sizing method (from RiskController)
        self.position_sizing_method: str = self.config.get('position_sizing_method', "percent_risk") 
                                            # Options: "percent_risk", "fixed_amount_per_trade", "fixed_quantity"

        # Risk tracking (from RiskController)
        self.current_total_risk_amount: float = 0.0 # Sum of risk_amount for all open positions
        self.positions_risk: Dict[str, float] = {} # Stores risk_amount per symbol for open positions

        # Original SimpleRiskManager params (can be kept or re-evaluated)
        self.max_order_value_pct: float = self.config.get('max_order_value_pct', 0.1)
        self.max_position_pct_asset: float = self.config.get('max_position_pct_asset', 0.2)
        self.min_cash_balance_pct: float = self.config.get('min_cash_balance_pct', 0.05)
        
        # 用于check_order方法所需的属性
        self.trade_history: Dict[str, Dict[str, Any]] = {}  # 记录交易历史
        self.last_order_time: Optional[datetime] = None  # 记录最后下单时间
        
        # 数据提供者，用于获取市场数据进行风控决策
        self.data_provider = None
        
        # 如果配置中提供了数据提供者工厂，则使用它获取数据提供者
        if 'data_provider_factory' in self.config:
            try:
                provider_factory = self.config['data_provider_factory']
                provider_type = self.config.get('data_provider_type', 'akshare')
                self.data_provider = provider_factory(provider_type)
                logger.info(f"风险管理器成功获取数据提供者: {provider_type}")
            except Exception as e:
                logger.error(f"风险管理器无法获取数据提供者: {e}", exc_info=True)
        
        logger.info(f"SimpleRiskManager (enhanced) initialized. Initial Capital: {self.initial_capital}, "
                    f"Max Risk/Trade: {self.max_risk_per_trade_pct:.2%}, Max Total Risk: {self.max_total_risk_pct:.2%}, "
                    f"Max Drawdown: {self.max_drawdown_limit_pct:.2%}, Sizing: {self.position_sizing_method}")

    def update_portfolio_state(self, portfolio_state: Dict[str, Any]):
        """
        更新风险管理器的内部资本视图，用于回撤等计算。
        portfolio_state is expected to come from Portfolio.get_summary() or similar.
        Expected keys: 'total_value', 'cash', 'initial_capital' (optional, if RM needs to re-sync)
        """
        new_capital = portfolio_state.get('total_value')
        if new_capital is None:
            logger.warning("RiskManager: Portfolio state update did not contain 'total_value'. Cannot update capital.")
            return

        self.current_capital = new_capital
        if self.current_capital > self.high_water_mark:
            self.high_water_mark = self.current_capital
        
        # Recalculate current total risk based on open positions if needed, or assume it's managed elsewhere.
        # For now, self.current_total_risk_amount is managed by add/remove_position_risk calls.

        current_drawdown = self._calculate_current_drawdown()
        if current_drawdown >= self.max_drawdown_limit_pct:
            logger.warning(f"DRAWDOWN ALERT: Current drawdown {current_drawdown:.2%} has reached or exceeded "
                           f"the max limit of {self.max_drawdown_limit_pct:.2%}. Consider risk mitigation.")
            # Future: Implement risk mitigation actions (e.g., reduce new trade sizes, halt trading)

    def _calculate_current_drawdown(self) -> float:
        if self.high_water_mark == 0: # Avoid division by zero if capital started at 0
            return 0.0
        drawdown = (self.high_water_mark - self.current_capital) / self.high_water_mark
        return drawdown if drawdown > 0 else 0.0 # Drawdown cannot be negative

    def _get_risk_amount_for_trade(self, entry_price: float, stop_loss_price: float, quantity: float) -> float:
        if quantity <= 0 or entry_price <= 0 or stop_loss_price <= 0:
            return 0.0
        return abs(entry_price - stop_loss_price) * quantity

    def _add_position_risk(self, symbol: str, risk_amount: float):
        if risk_amount <= 0: return
        self.current_total_risk_amount -= self.positions_risk.get(symbol, 0) # Deduct old risk if updating
        self.positions_risk[symbol] = risk_amount
        self.current_total_risk_amount += risk_amount
        logger.debug(f"Risk added/updated for {symbol}: {risk_amount:.2f}. Total portfolio risk: {self.current_total_risk_amount:.2f}")

    def _remove_position_risk(self, symbol: str):
        removed_risk = self.positions_risk.pop(symbol, 0)
        self.current_total_risk_amount -= removed_risk
        logger.debug(f"Risk removed for {symbol}: {removed_risk:.2f}. Total portfolio risk: {self.current_total_risk_amount:.2f}")

    def validate_signal(self, 
                        signal: Dict[str, Any], 
                        portfolio_state: Optional[Dict[str, Any]], 
                        position_state: Optional[Dict[str, Any]] 
                       ) -> Tuple[bool, str]:
        """
        验证交易信号是否符合风险规定。
        Enhanced with RiskController logic.
        Signal must now include 'stop_loss_price' for BUY/SHORT signals to calculate risk.
        """
        if not portfolio_state:
            return False, "Portfolio state missing."

        action = signal.get('action', '').upper()
        symbol = signal.get('symbol')
        quantity = signal.get('quantity')
        price = signal.get('price') # Entry price
        stop_loss_price = signal.get('stop_loss_price')

        if not all([action, symbol, price]): # Quantity can be 'all'
            return False, "Signal missing action, symbol, or price."
        if price <= 0:
            return False, f"Invalid entry price: {price}"
        
        # Update internal capital view based on fresh portfolio_state
        self.update_portfolio_state(portfolio_state)

        # Check for drawdown limit breach
        current_drawdown = self._calculate_current_drawdown()
        if current_drawdown >= self.max_drawdown_limit_pct:
            return False, f"Trading halted/restricted: Max drawdown limit {self.max_drawdown_limit_pct:.2%} reached (current: {current_drawdown:.2%})."

        # For SELL 'all', validation is simpler as it's reducing risk.
        if action == 'SELL' and quantity == 'all':
            if not position_state or position_state.get('quantity', 0) <= 0:
                return False, f"Cannot sell 'all' for {symbol}: No existing position."
            return True, "Sell 'all' signal preliminarily valid."
        
        try:
            if quantity is not None: # quantity can be None if determined by risk sizing
                quantity = float(quantity)
                if quantity <= 0: return False, "Quantity must be positive."
        except ValueError:
            return False, f"Invalid quantity format: {quantity}"
        
        proposed_risk_amount = 0
        if action in ['BUY', 'SHORT'] and quantity is not None: # If quantity is provided, calculate risk based on it
            if stop_loss_price is None or stop_loss_price <= 0:
                return False, f"Signal for {action} {symbol} missing valid 'stop_loss_price'."
            if (action == 'BUY' and price <= stop_loss_price) or \
               (action == 'SHORT' and price >= stop_loss_price):
                return False, f"Entry price {price} is not favorable compared to stop loss {stop_loss_price} for {action}."
            proposed_risk_amount = self._get_risk_amount_for_trade(price, stop_loss_price, quantity)
        
        # Check max risk per trade (if proposed_risk_amount is calculated)
        # This limit applies if strategy provides a quantity. If RM determines quantity, it will obey this.
        max_risk_allowed_per_trade = self.current_capital * self.max_risk_per_trade_pct
        if proposed_risk_amount > 0 and proposed_risk_amount > max_risk_allowed_per_trade:
            return False, (f"Proposed risk {proposed_risk_amount:.2f} for trade exceeds max risk per trade limit "
                           f"({max_risk_allowed_per_trade:.2f}).")

        # Check total portfolio risk
        # Risk from this trade will be calculated by adjust_order_size if quantity is not fixed.
        # If quantity is fixed, we use proposed_risk_amount.
        risk_from_this_trade = proposed_risk_amount # Assume this for now if quantity is fixed.
                                                    # adjust_order_size will do the final check.

        # Calculate potential new total risk
        current_risk_for_symbol = self.positions_risk.get(symbol, 0)
        additional_risk = risk_from_this_trade - (current_risk_for_symbol if action in ['BUY', 'SHORT'] else 0)
        if action in ['SELL', 'COVER']: # Reducing or closing a position
             additional_risk = -current_risk_for_symbol # Approximation, actual PnL changes capital

        potential_total_risk = self.current_total_risk_amount + additional_risk
        max_total_portfolio_risk_abs = self.current_capital * self.max_total_risk_pct

        if potential_total_risk > max_total_portfolio_risk_abs and additional_risk > 0 : # Only block if increasing risk beyond limit
             return False, (f"Trade would exceed max total portfolio risk. "
                            f"Current: {self.current_total_risk_amount:.2f}, "
                            f"This trade adds ~{additional_risk:.2f}, Potential: {potential_total_risk:.2f} "
                            f"Limit: {max_total_portfolio_risk_abs:.2f}")
        
        # Original SimpleRiskManager checks (can be kept as secondary checks or re-evaluated)
        total_portfolio_value = portfolio_state.get('total_value', 0)
        available_cash = portfolio_state.get('cash', 0)

        if total_portfolio_value <= 0:
             return False, "Portfolio total value is zero or invalid."
        
        order_value = quantity * price if quantity is not None else 0

        if action == 'BUY':
            if order_value > 0: # Only if quantity and price are valid
                if order_value > total_portfolio_value * self.max_order_value_pct:
                    return False, f"Order value {order_value:.2f} exceeds max order value limit ({total_portfolio_value * self.max_order_value_pct:.2f})."
                
                min_cash_needed = total_portfolio_value * self.min_cash_balance_pct
                if available_cash - order_value < min_cash_needed:
                    return False, f"Insufficient cash after trade for min balance. Available: {available_cash:.2f}, Order: {order_value:.2f}, MinCash: {min_cash_needed:.2f}"

            # Max position check should be done by adjust_order_size or based on its calculation
            # For pure validation, if a quantity is given, we can check it here:
            if quantity is not None:
                current_asset_value = 0
                if position_state and position_state.get('quantity', 0) > 0:
                    # Use current_price for existing position value for consistency
                    current_asset_value = position_state.get('quantity',0) * price 
                new_asset_value = current_asset_value + order_value
                if new_asset_value > total_portfolio_value * self.max_position_pct_asset:
                    return False, f"Asset {symbol} value {new_asset_value:.2f} would exceed max position limit ({total_portfolio_value * self.max_position_pct_asset:.2f})."
        
        elif action == 'SELL' and quantity is not None: # Not 'all'
            if not position_state or quantity > position_state.get('quantity', 0):
                return False, f"Sell quantity {quantity} exceeds holdings {position_state.get('quantity', 0) if position_state else 0}."
                
        return True, "Signal preliminarily valid (final size TBD by adjust_order_size)."

    def calculate_max_position_size(self, 
                                    symbol: str, 
                                    current_price: float, # Entry price
                                    portfolio_state: Dict[str, Any],
                                    stop_loss_price: Optional[float] = None, # Crucial for percent_risk
                                    # volatility: Optional[float] = None, # Future use
                                    # confidence: Optional[float] = None, # Future use
                                    action: str = 'BUY' # To handle SHORT if unit risk is different
                                   ) -> float: # Returns quantity (shares/contracts)
        """
        Calculates max position size (quantity) based on risk parameters.
        This is a helper for adjust_order_size, or can be called by strategy.
        """
        if not portfolio_state or current_price <= 0: return 0.0
        self.update_portfolio_state(portfolio_state) # Ensure capital view is fresh

        if self._calculate_current_drawdown() >= self.max_drawdown_limit_pct:
             logger.warning("Max drawdown reached, max position size calculated as 0.")
             return 0.0

        capital_for_risk_calc = self.current_capital
        
        # Determine risk amount for this single trade
        risk_amount_for_this_trade = capital_for_risk_calc * self.max_risk_per_trade_pct
        
        # Cap by total available risk budget
        remaining_total_risk_budget = (capital_for_risk_calc * self.max_total_risk_pct) - self.current_total_risk_amount
        risk_amount_for_this_trade = min(risk_amount_for_this_trade, max(0, remaining_total_risk_budget))

        if risk_amount_for_this_trade <= 0: return 0.0 # No risk budget left

        quantity = 0
        if self.position_sizing_method == "percent_risk":
            if stop_loss_price is None or stop_loss_price <=0:
                logger.warning(f"Cannot use 'percent_risk' sizing for {symbol}: stop_loss_price not provided or invalid.")
                return 0.0
            if (action == 'BUY' and current_price <= stop_loss_price) or \
               (action == 'SHORT' and current_price >= stop_loss_price):
                logger.warning(f"Cannot use 'percent_risk' sizing: entry {current_price} vs stop {stop_loss_price} for {action} is unfavorable.")
                return 0.0
            
            unit_risk = abs(current_price - stop_loss_price)
            if unit_risk == 0: return 0.0 # Avoid division by zero
            quantity = risk_amount_for_this_trade / unit_risk
        
        elif self.position_sizing_method == "fixed_amount_per_trade":
            # Risk amount per trade IS self.max_risk_per_trade_pct * capital (interpreted as investment amount)
            # This might be a misnomer from original RiskController; let's assume it means 'fixed_investment_value'
            # This method does not inherently limit risk based on stop-loss.
            # Let's use risk_amount_for_this_trade as the investment value for this interpretation.
            quantity = risk_amount_for_this_trade / current_price # risk_amount_for_this_trade is effectively max investment here.

        elif self.position_sizing_method == "fixed_quantity":
            # This method implies quantity is fixed by strategy, not calculated by RM.
            # This method here should then just return a large number or be handled differently.
            # For now, let's assume it's not the role of this function if method is "fixed_quantity".
            logger.warning("'fixed_quantity' sizing method means RM doesn't calculate max size this way.")
            return float('inf') # Or handle as an error / special case
        else:
            logger.error(f"Unknown position sizing method: {self.position_sizing_method}")
            return 0.0

        # Further constraints from original SimpleRiskManager
        # 1. Max value for asset based on total portfolio
        max_value_for_asset_overall = capital_for_risk_calc * self.max_position_pct_asset
        max_qty_by_asset_limit = max_value_for_asset_overall / current_price
        
        # 2. Max value based on available cash (for BUYs)
        if action == 'BUY':
            available_cash = portfolio_state.get('cash', 0)
            min_cash_balance_abs = capital_for_risk_calc * self.min_cash_balance_pct
            max_investment_from_cash = available_cash - min_cash_balance_abs
            if max_investment_from_cash <=0: return 0.0
            max_qty_by_cash = max_investment_from_cash / current_price
            quantity = min(quantity, max_qty_by_cash)

        quantity = min(quantity, max_qty_by_asset_limit)
        
        # 3. Max order value (if this function also respects single order limits)
        max_order_val = capital_for_risk_calc * self.max_order_value_pct
        max_qty_by_order_val_limit = max_order_val / current_price
        quantity = min(quantity, max_qty_by_order_val_limit)
        
        # 4. 基于市场数据的更智能头寸规模限制
        if self.data_provider:
            try:
                # 获取股票的历史数据
                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
                hist_data = self.data_provider.get_historical_data(symbol, start_date, end_date)
                
                if not hist_data.empty:
                    # 成交量约束：限制在日均成交量的小比例
                    if 'volume' in hist_data.columns:
                        avg_volume = hist_data['volume'].mean()
                        if avg_volume > 0:
                            # 以日均成交量的0.5%为上限，避免过度影响市场价格
                            volume_limit = max(1, int(avg_volume * 0.005))
                            quantity = min(quantity, volume_limit)
                            logger.debug(f"成交量约束: 限制在日均成交量{avg_volume}的0.5% = {volume_limit}股")
                    
                    # 波动率约束：波动性高的股票降低仓位规模
                    if 'close' in hist_data.columns and len(hist_data) >= 5:
                        daily_returns = hist_data['close'].pct_change().dropna()
                        volatility = daily_returns.std()
                        
                        # 根据波动率调整头寸规模
                        volatility_factor = 1.0
                        if volatility > 0.03:  # 3%以上日波动率
                            volatility_factor = 0.7  # 降低30%
                        elif volatility > 0.02:  # 2%以上日波动率
                            volatility_factor = 0.85  # 降低15%
                        
                        if volatility_factor < 1.0:
                            old_quantity = quantity
                            quantity *= volatility_factor
                            logger.debug(f"波动率约束: 波动率{volatility:.2%}，调整因子{volatility_factor}，数量从{old_quantity}调整为{quantity}")
                    
                    # 流动性约束：检查买入价相对于最近价格的偏离度
                    if 'close' in hist_data.columns and len(hist_data) >= 5:
                        recent_avg_price = hist_data['close'].iloc[-5:].mean()
                        price_deviation = abs(current_price - recent_avg_price) / recent_avg_price
                        
                        # 如果价格偏离超过一定比例，减少仓位
                        if price_deviation > 0.05:  # 价格偏离超过5%
                            deviation_factor = max(0.5, 1.0 - price_deviation) # 最少减少50%
                            old_quantity = quantity
                            quantity *= deviation_factor
                            logger.debug(f"价格偏离约束: 偏离度{price_deviation:.2%}，调整因子{deviation_factor}，数量从{old_quantity}调整为{quantity}")
            except Exception as e:
                logger.warning(f"获取{symbol}市场数据进行头寸规模优化时出错: {e}", exc_info=True)

        return float(int(quantity)) # Return whole shares/contracts

    def adjust_order_size(self, 
                          original_order: Dict[str, Any], 
                          portfolio_state: Dict[str, Any],
                          position_state: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
        """
        Adjusts order quantity based on risk.
        If signal has quantity, it's validated. If no quantity, it's calculated.
        `portfolio_state` should be up-to-date.
        `position_state` is for the specific symbol.
        """
        adjusted_order = original_order.copy()
        action = adjusted_order.get('action', '').upper()
        symbol = adjusted_order.get('symbol')
        price = adjusted_order.get('price') # Entry price
        stop_loss_price = adjusted_order.get('stop_loss_price')
        requested_quantity = adjusted_order.get('quantity') # Can be None or 'all'

        self.update_portfolio_state(portfolio_state) # Ensure internal state is fresh

        if not all([action, symbol, price]) or price <= 0:
            adjusted_order['quantity'] = 0
            adjusted_order['reason'] = "Invalid order fields (action, symbol, price)."
            return adjusted_order
        
        current_holding_qty = 0
        if position_state:
            current_holding_qty = position_state.get('quantity', 0)

        final_quantity = 0
        calculated_risk_for_trade = 0

        if action == 'BUY' or action == 'SHORT':
            if self._calculate_current_drawdown() >= self.max_drawdown_limit_pct:
                logger.warning(f"Max drawdown reached. {action} order for {symbol} quantity set to 0.")
                adjusted_order['quantity'] = 0
                adjusted_order['reason'] = "Max drawdown limit reached."
                # No risk added if quantity is 0
                self._remove_position_risk(symbol) # Ensure any prior risk placeholder is cleared if trade is voided
                return adjusted_order

            if requested_quantity is None or self.position_sizing_method != "fixed_quantity":
                # Calculate quantity based on risk if not provided or method is not fixed_quantity
                # For percent_risk, stop_loss_price is essential.
                if self.position_sizing_method == "percent_risk" and (stop_loss_price is None or stop_loss_price <= 0):
                    adjusted_order['quantity'] = 0
                    adjusted_order['reason'] = f"'percent_risk' sizing requires valid 'stop_loss_price' in signal."
                    self._remove_position_risk(symbol)
                    return adjusted_order
                
                # calculate_max_position_size returns max *new* quantity to acquire
                # It already considers various limits (per-trade risk, total risk, asset % limit, cash)
                # This function is for calculating the size of a *new* position or *addition* to position.
                # If we are *adding* to a position, this calculation should be for the *entire* desired position size,
                # then we subtract current_holding_qty.
                # Let's refine: calculate_max_position_size computes total allowable position size.
                
                max_total_allowable_qty_for_symbol = self.calculate_max_position_size(
                    symbol=symbol, 
                    current_price=price, 
                    portfolio_state=portfolio_state,
                    stop_loss_price=stop_loss_price, # Crucial for percent_risk
                    action=action
                )
                
                # The actual quantity to trade is the difference, or the full amount if no current holdings.
                # This is for a *new* order. If sizing an existing position, strategy should decide total target.
                # For now, assume this is a new signal for a new trade/addition.
                qty_to_trade = max_total_allowable_qty_for_symbol
                if action == 'BUY':
                    # If we are adding, this is the max *additional* quantity
                    # The max_total_allowable_qty_for_symbol should represent the TOTAL desired position size
                    # So, qty_to_trade_for_this_order = max_total_allowable_qty_for_symbol - current_holding_qty
                    # This interpretation implies calculate_max_position_size calculates *total* target quantity
                    # Let's make calculate_max_position_size return the *new* quantity to trade
                    # No, let calculate_max_position_size return the *total size allowed for the asset*.
                    # Then, adjust_order_size determines how much of that is for *this* order.

                    # If requested_quantity is provided, we are validating/clipping it.
                    # If not, we are calculating it.
                    if requested_quantity is not None:
                        try:
                            final_quantity = min(float(requested_quantity), max_total_allowable_qty_for_symbol - current_holding_qty)
                            final_quantity = max(0, final_quantity) # Ensure not negative
                        except ValueError:
                            final_quantity = 0 # Invalid requested_quantity
                    else: # Calculate quantity
                        final_quantity = max(0, max_total_allowable_qty_for_symbol - current_holding_qty)
                
                elif action == 'SHORT': # Similar logic for shorting
                     if requested_quantity is not None:
                        try:
                            final_quantity = min(float(requested_quantity), max_total_allowable_qty_for_symbol - abs(current_holding_qty)) # abs for short
                            final_quantity = max(0, final_quantity) 
                        except ValueError:
                            final_quantity = 0 
                     else: # Calculate quantity
                        final_quantity = max(0, max_total_allowable_qty_for_symbol - abs(current_holding_qty))


            elif self.position_sizing_method == "fixed_quantity" and requested_quantity is not None:
                # Validate fixed quantity against limits
                try:
                    final_quantity = float(requested_quantity)
                    # Perform basic validation checks if fixed quantity is used
                    is_valid, reason = self.validate_signal(original_order, portfolio_state, position_state)
                    if not is_valid:
                        final_quantity = 0
                        adjusted_order['reason'] = reason
                except ValueError:
                    final_quantity = 0
                    adjusted_order['reason'] = "Invalid fixed quantity."
            else: # fixed_quantity but no quantity provided in signal - error
                final_quantity = 0
                adjusted_order['reason'] = "Fixed_quantity sizing method but no quantity in signal."

            final_quantity = float(int(final_quantity)) # Whole shares

            if final_quantity > 0 and stop_loss_price: # stop_loss_price might be None if not percent_risk
                 calculated_risk_for_trade = self._get_risk_amount_for_trade(price, stop_loss_price, final_quantity)
            
            adjusted_order['quantity'] = final_quantity
            if final_quantity > 0:
                self._add_position_risk(symbol, calculated_risk_for_trade)
                adjusted_order['calculated_risk'] = calculated_risk_for_trade
            else: # If quantity is 0, ensure no risk is associated
                self._remove_position_risk(symbol)
                if 'reason' not in adjusted_order:
                    adjusted_order['reason'] = "Calculated quantity is zero."


        elif action == 'SELL' or action == 'COVER':
            qty_to_trade = 0
            if requested_quantity == 'all':
                qty_to_trade = current_holding_qty
            else:
                try:
                    requested_qty_float = float(requested_quantity)
                    qty_to_trade = min(requested_qty_float, current_holding_qty) # Cannot sell more than holding
                except (ValueError, TypeError):
                    logger.warning(f"Invalid quantity {requested_quantity} for {action} {symbol}.")
                    qty_to_trade = 0
            
            final_quantity = float(int(max(0, qty_to_trade)))
            adjusted_order['quantity'] = final_quantity
            
            # If closing out the position fully or partially
            if final_quantity >= current_holding_qty and current_holding_qty > 0 : # Full exit
                self._remove_position_risk(symbol)
                adjusted_order['reason'] = "Position closed."
            elif final_quantity > 0: # Partial exit
                # Risk needs to be re-evaluated for remaining position or simply reduced proportionally.
                # For simplicity, if stop_loss_price for original position was known, can update.
                # Or, remove all risk and let next BUY/SHORT signal re-establish it.
                # Safest is to remove for now, assuming strategy will manage risk on remaining.
                # This is an oversimplification. Proper partial exit risk needs more.
                # For now, let's assume risk is removed on ANY sell/cover. Re-added if position re-entered.
                self._remove_position_risk(symbol) 
                adjusted_order['reason'] = f"Partial exit. Original risk for {symbol} removed."


        if adjusted_order.get('quantity', 0) == 0 and 'reason' not in adjusted_order:
            adjusted_order['reason'] = "Quantity is zero after adjustment."
            
        logger.info(f"Order adjustment: Original: {original_order.get('quantity')}, Adjusted: {adjusted_order.get('quantity')}, "
                    f"Symbol: {symbol}, Action: {action}, Reason: {adjusted_order.get('reason','')}")
        return adjusted_order

    def check_order(self, order, portfolio=None):
        """
        检查订单是否符合风险控制规则
        
        Args:
            order (dict): 订单信息
            portfolio (Portfolio, optional): 投资组合对象。当提供时，可进行更详细的风险评估
            
        Returns:
            (bool, str): (通过检查?, 拒绝原因)
        """
        logger.debug(f"检查订单风控: {order}")
        
        # 获取风控参数配置
        max_position_pct = self.config.get('max_position_percent', 0.15)  # 单一仓位最大比例
        max_daily_trades = self.config.get('max_daily_trades', 10)  # 每日最大交易次数
        max_stock_volatility = self.config.get('max_volatility', 0.1)  # 最大允许波动率
        max_loss_pct = self.config.get('max_loss_percent', 0.05)  # 最大允许亏损比例
        min_order_interval = self.config.get('min_order_interval_seconds', 60)  # 最小订单间隔(秒)
        
        symbol = order.get('symbol')
        quantity = order.get('quantity', 0)
        price = order.get('price', 0)
        side = order.get('side', '')  # 'buy' or 'sell'
        order_value = price * quantity  # 订单价值
        
        # 1. 检查投资组合限制
        if portfolio:
            # 获取总资产
            total_value = portfolio.get_total_value()
            total_position_value = portfolio.get_total_position_value()
            cash_balance = portfolio.get_cash_balance()
            
            # 检查现金是否足够（买入时）
            if side.lower() == 'buy' and cash_balance < order_value:
                return False, f"现金不足: 需要 {order_value}, 只有 {cash_balance}"
            
            # 检查持仓比例限制
            if side.lower() == 'buy':
                current_position_value = portfolio.get_position_value(symbol) if portfolio.has_position(symbol) else 0
                new_position_value = current_position_value + order_value
                new_position_pct = new_position_value / (total_value + order_value - current_position_value)
                
                if new_position_pct > max_position_pct:
                    return False, f"超过单一持仓比例限制: {new_position_pct:.2%}, 限制: {max_position_pct:.2%}"
        
        # 2. 检查交易频率限制
        current_time = datetime.now()
        today = current_time.date()
        
        # 获取今日交易历史
        today_trades = []
        for trade_time, trade_info in self.trade_history.items():
            if isinstance(trade_time, str):
                try:
                    trade_datetime = datetime.fromisoformat(trade_time)
                    if trade_datetime.date() == today:
                        today_trades.append(trade_info)
                except (ValueError, TypeError):
                    continue
            elif hasattr(trade_time, 'date') and trade_time.date() == today:
                today_trades.append(trade_info)
        
        # 检查今日交易次数限制
        if len(today_trades) >= max_daily_trades:
            return False, f"超过每日最大交易次数: {len(today_trades)}/{max_daily_trades}"
        
        # 检查交易时间间隔
        if self.last_order_time:
            time_since_last_order = (current_time - self.last_order_time).total_seconds()
            if time_since_last_order < min_order_interval:
                return False, f"订单间隔过短: {time_since_last_order}秒, 最小间隔: {min_order_interval}秒"
        
        # 3. 检查市场数据和波动性限制
        if self.data_provider:
            try:
                # 获取历史数据用于波动性计算
                end_date = current_time.strftime('%Y-%m-%d')
                start_date = (current_time - timedelta(days=20)).strftime('%Y-%m-%d')
                hist_data = self.data_provider.get_historical_data(symbol, start_date, end_date)
                
                if not hist_data.empty and 'close' in hist_data.columns:
                    # 计算20日波动率
                    daily_returns = hist_data['close'].pct_change().dropna()
                    volatility = daily_returns.std()
                    
                    if volatility > max_stock_volatility:
                        return False, f"股票波动性过高: {volatility:.2%}, 限制: {max_stock_volatility:.2%}"
                    
                    # 获取当前价格和近期最低价，检查是否接近上涨或下跌限制
                    if len(hist_data) > 1:
                        current_price = hist_data['close'].iloc[-1]
                        min_price = hist_data['close'].min()
                        max_price = hist_data['close'].max()
                        
                        # 计算从最低点的涨幅
                        rise_from_min = (current_price - min_price) / min_price if min_price > 0 else 0
                        
                        # 计算从最高点的跌幅
                        drop_from_max = (max_price - current_price) / max_price if max_price > 0 else 0
                        
                        # 设定涨跌幅阈值 (可以根据市场情况在配置中调整)
                        max_rise_threshold = self.config.get('max_rise_threshold', 0.20)  # 最大允许涨幅
                        max_drop_threshold = self.config.get('max_drop_threshold', 0.10)  # 最大允许跌幅
                        
                        if side.lower() == 'buy' and rise_from_min > max_rise_threshold:
                            return False, f"股票已大幅上涨: 从低点涨幅 {rise_from_min:.2%}, 建议不买入"
                        
                        if side.lower() == 'sell' and drop_from_max > max_drop_threshold:
                            return False, f"股票已大幅下跌: 从高点跌幅 {drop_from_max:.2%}, 建议不卖出"
            except Exception as e:
                logger.warning(f"获取市场数据进行风控检查时出错: {e}")
        
        # 4. 检查是否有超过单日亏损限制
        if portfolio:
            # 获取今日亏损情况
            initial_value = portfolio.get_initial_value()
            current_value = portfolio.get_total_value()
            
            if initial_value > 0:
                loss_pct = (initial_value - current_value) / initial_value
                
                if loss_pct > max_loss_pct:
                    return False, f"已超过单日最大亏损限制: 当前亏损 {loss_pct:.2%}, 限制: {max_loss_pct:.2%}"
        
        # 5. 检查订单是否合理有效
        if quantity <= 0:
            return False, "订单数量必须大于零"
            
        if price <= 0:
            return False, "订单价格必须大于零"
            
        # 通过所有风控检查
        logger.info(f"订单通过风控检查: {order}")
        self.last_order_time = current_time
        
        # 记录交易历史
        self.trade_history[current_time.isoformat()] = {
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            'side': side,
            'value': order_value
        }
        
        # 可以在此处记录风控决策过程，以便审计
        return True, "通过风控检查"

    # get_risk_assessment can be implemented later if needed, using RiskController's get_risk_report ideas.
    # def get_risk_assessment(self, symbol: str, portfolio_state: Dict[str, Any]) -> Dict[str, Any]:
    #     return {"message": "Risk assessment pending full integration."} 