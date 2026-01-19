import json
import os
from datetime import datetime, timedelta, timezone
from config import PORTFOLIO_FILE

class PortfolioManager:
    def __init__(self):
        self.data = self._load_data()
        self._migrate_data() # Garante compatibilidade com Trailing Stop

    def get_timestamp_brt(self):
        brt_time = datetime.now(timezone.utc) - timedelta(hours=3)
        return brt_time.strftime('%Y-%m-%d %H:%M:%S')

    def _load_data(self):
        structure = {
            "metadata": {"version": "1.1", "updated_at": ""}, # Versão atualizada
            "wallet_summary": {"current_equity": 0.0},
            "active_positions": {},
            "balance_history": []
        }
        
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Merge de chaves
                    for key in structure:
                        if key not in loaded: loaded[key] = structure[key]
                    return loaded
            except Exception:
                return structure
        return structure

    def _migrate_data(self):
        """Adiciona o campo 'highest_price' em posições antigas para o Trailing Stop"""
        changed = False
        for symbol, data in self.data['active_positions'].items():
            if 'highest_price' not in data:
                # Se não tinha histórico de topo, assume que o topo é o preço de compra
                data['highest_price'] = data['buy_price']
                changed = True
        if changed:
            self.save_data()

    def save_data(self):
        self.data["metadata"]["updated_at"] = self.get_timestamp_brt()
        with open(PORTFOLIO_FILE, 'w') as f:
            json.dump(self.data, f, indent=4)

    def log_history(self, equity, fluctuation):
        entry = {
            "timestamp": self.get_timestamp_brt(),
            "equity": round(equity, 4),
            "fluctuation": fluctuation,
            "positions": len(self.data['active_positions'])
        }
        self.data['balance_history'].append(entry)
        if len(self.data['balance_history']) > 1000:
            self.data['balance_history'].pop(0)
        self.save_data()

    def add_position(self, symbol, price, amount, rsi):
        self.data['active_positions'][symbol] = {
            'buy_price': price,
            'highest_price': price, # Inicializa o Trailing Stop
            'amount_usdt': amount,
            'rsi_at_entry': rsi,
            'entry_time': self.get_timestamp_brt()
        }
        self.save_data()

    def remove_position(self, symbol):
        if symbol in self.data['active_positions']:
            del self.data['active_positions'][symbol]
            self.save_data()