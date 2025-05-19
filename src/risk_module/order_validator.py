# Validates orders against pre-trade risk checks.

class OrderValidator:
    def __init__(self, max_order_value_usd, allowed_symbols_list=None):
        self.max_order_value_usd = max_order_value_usd
        self.allowed_symbols_list = allowed_symbols_list or []
        print("OrderValidator initialized.")

    def validate_order(self, order_details):
        """
        Validates an order against defined rules.
        order_details (dict): e.g., {'symbol': 'AAPL', 'quantity': 100, 'price': 150.00, 'side': 'BUY'}
        """
        symbol = order_details.get('symbol')
        quantity = order_details.get('quantity', 0)
        price = order_details.get('price', 0)

        if not symbol:
            print("Order validation failed: Symbol missing.")
            return False

        if self.allowed_symbols_list and symbol not in self.allowed_symbols_list:
            print(f"Order validation failed: Symbol {symbol} not allowed.")
            return False

        if quantity <= 0:
            print("Order validation failed: Quantity must be positive.")
            return False

        if price <= 0:
            print("Order validation failed: Price must be positive.")
            return False
        
        order_value = quantity * price
        if order_value > self.max_order_value_usd:
            print(f"Order validation failed: Order value {order_value} exceeds max limit {self.max_order_value_usd}.")
            return False
        
        print(f"Order for {symbol} validated successfully.")
        return True 