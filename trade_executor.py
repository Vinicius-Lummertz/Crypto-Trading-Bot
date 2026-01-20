import math
import logging
from datetime import datetime, timezone
import config

# Configuração de Logs
logger = logging.getLogger(__name__)

class TradeExecutor:
    def __init__(self, api_client, db_manager, notifier):
        self.api = api_client
        self.db = db_manager
        self.notifier = notifier

    def sell_position(self, symbol, reason):
        """
        Executa a venda de uma posição:
        1. Verifica saldo na Binance
        2. Normaliza quantidade (Step Size)
        3. Envia ordem de venda
        4. Calcula PnL
        5. Notifica Telegram
        6. Remove do Banco de Dados
        """
        print(f"   ⚠️ Tentando vender {symbol} ({reason})...")
        
        # 1. Recupera Saldo Bruto
        asset_name = symbol.replace(config.SYMBOL_QUOTE, '')
        balance = 0.0
        
        if not config.SIMULATION_MODE:
            acc = self.api.get_account()
            
            if not acc:
                print(f"   ❌ Erro de Conexão ao verificar saldo de {symbol}.")
                return False

            for b in acc['balances']:
                if b['asset'] == asset_name:
                    balance = float(b['free'])
                    break
            
            if balance == 0:
                print(f"   ⚠️ Alerta: Saldo de {symbol} é zero na Binance. Removendo do registro local.")
                self.db.remove_position(symbol)
                return True # Considera "resolvido" pois removeu do DB

            # 2. Normalização de Quantidade
            step_size = self.api.get_symbol_step_size(symbol)
            qty_to_sell = balance
            
            if step_size:
                precision = int(round(-math.log(step_size, 10), 0))
                qty_to_sell = math.floor(balance / step_size) * step_size
                qty_to_sell = round(qty_to_sell, precision)
                print(f"   📐 Ajuste de Precisão: {balance} -> {qty_to_sell} (Step: {step_size})")
            
            if qty_to_sell == 0:
                print("   ❌ Saldo insuficiente após ajuste de precisão.")
                return False

            # 3. Envia Ordem
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': qty_to_sell 
            }
            
            res = self.api._send('POST', '/api/v3/order', params, signed=True)
            
            if not res or 'status' not in res or res['status'] not in ['FILLED', 'NEW']:
                print(f"   ❌ FALHA CRÍTICA NA VENDA DE {symbol}!")
                if res: print(f"   🔍 Resposta da API: {res}")
                return False

            print(f"   ✅ Venda Confirmada na Binance: {res.get('orderId')}")

        # 4. PnL Realizado & Notificação
        # Recupera dados ANTES de remover
        data = self.db.data['active_positions'].get(symbol)
        current_price = self.api.get_price(symbol) or 0.0
        
        if data:
            buy_price = data['buy_price']
            amount_usdt = data['amount_usdt']
            
            # Se for simulação ou se não conseguimos pegar preço atual, usa o do DB ou 0
            # Na verdade, se vendeu a mercado, o preço exato vem da ordem, mas aqui simplificamos usando o ticker atual
            
            profit_usd = 0.0
            if buy_price > 0:
                profit_usd = amount_usdt * ((current_price - buy_price) / buy_price)
            
            print(f"   💰 VENDIDO: {symbol} | Lucro: ${profit_usd:.2f} | Motivo: {reason}")
            
            # Notifica Telegram
            if self.notifier:
                self.notifier.send_alert(
                    symbol, 
                    "Trailing Stop / Manual", 
                    "SELL", 
                    current_price, 
                    f"💰 Lucro: ${profit_usd:.2f}\n📝 Motivo: {reason}"
                )
        
        # 5. Remove do DB
        self.db.remove_position(symbol)
        return True
