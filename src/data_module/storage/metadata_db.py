# Interface for Metadata Database operations (e.g., PostgreSQL, MySQL, SQLite)

class MetaDataDB:
    def __init__(self, config):
        self.config = config
        # Initialize connection to DB
        print("MetaDataDB initialized.")

    def store_strategy_params(self, strategy_name, params):
        print(f"Storing params for strategy {strategy_name}: {params}")
        pass

    def get_strategy_params(self, strategy_name):
        print(f"Getting params for strategy {strategy_name}")
        return {}

    def store_trade_log(self, trade_details):
        print(f"Storing trade log: {trade_details}")
        pass 