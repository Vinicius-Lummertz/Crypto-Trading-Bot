import time
import hmac
import hashlib
import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from urllib.parse import urlencode
load_dotenv()

# ==========================================
# ⚙️ CONFIGURAÇÕES AVANÇADAS
# ==========================================
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
BASE_URL = 'https://api.binance.com'

# Estratégia
SYMBOL_QUOTE = 'USDT'
MIN_VOLUME_USDT = 2_000_000
AMOUNT_TO_TRADE = 15.0       

# Indicadores & Risco
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 30
TAKE_PROFIT = 0.05
STOP_LOSS = -0.03

# Arquivo de Dados
PORTFOLIO_FILE = 'portfolio_data.json' # Nome alterado para evitar conflito com versão antiga
IGNORED_COINS = [
    'USDCUSDT', 'FDUSDUSDT', 'USDPUSDT', 'TUSDUSDT', 'BUSDUSDT', 
    'EURUSDT', 'DAIUSDT', 'FRAXUSDT', 'USDDUSDT', 'AEURUSDT'
]

SIMULATION_MODE = False
SIMULATION_START_BALANCE = 100.0 # Saldo inicial para cálculos de simulação

class BinanceBot:
    def __init__(self):

        if not API_KEY or not SECRET_KEY:
            raise ValueError("⚠️⚠️⚠️ ERRO MAIS CRITICO DE TODOS ⚠️⚠️⚠️: Chaves de API não encontradas no arquivo .env")

        self.session = requests.Session()
        self.session.headers.update({'X-MBX-APIKEY': API_KEY})
        
        # Inicializa estrutura de dados
        self.data = self.load_data()
        
        # Estado volátil (memória RAM) para cálculo de flutuação imediata
        self.last_equity_check = self.get_total_equity()

    # --- 🕒 Utilitários de Tempo (Brasília UTC-3) ---
    def get_timestamp_brt(self):
        # Subtrai 3 horas do UTC para pegar horário de Brasília
        brt_time = datetime.utcnow() - timedelta(hours=3)
        return brt_time.strftime('%Y-%m-%d %H:%M:%S')

    # --- 💾 Persistência de Dados (JSON Estruturado) ---
    def load_data(self):
        structure = {
            "metadata": {"version": "1.0", "created_at": self.get_timestamp_brt()},
            "wallet_summary": {"current_equity": 0.0, "total_pnl_pct": 0.0},
            "active_positions": {},
            "balance_history": []
        }
        
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Merge simples para garantir que chaves novas existam em arquivos velhos
                    for key in structure:
                        if key not in loaded:
                            loaded[key] = structure[key]
                    return loaded
            except Exception as e:
                print(f"⚠️ Erro ao ler JSON: {e}. Criando novo.")
                return structure
        return structure

    def save_data(self):
        # Atualiza timestamp da última modificação
        self.data["metadata"]["last_update"] = self.get_timestamp_brt()
        with open(PORTFOLIO_FILE, 'w') as f:
            json.dump(self.data, f, indent=4)

    def log_history(self, equity, fluctuation_pct):
        """Grava o snapshot financeiro no histórico"""
        entry = {
            "timestamp": self.get_timestamp_brt(),
            "equity_usdt": round(equity, 4),
            "fluctuation_since_last_check": f"{fluctuation_pct:+.2f}%",
            "active_positions_count": len(self.data['active_positions'])
        }
        # Mantém apenas os últimos 1000 registros para o arquivo não ficar gigante
        self.data['balance_history'].append(entry)
        if len(self.data['balance_history']) > 1000:
            self.data['balance_history'].pop(0)
        
        self.save_data()

    # --- 🌐 Camada de Rede (API) ---
    def _send_signed_request(self, method, endpoint, params=None):
        if params is None: params = {}
        
        # Correção do Timestamp (remove o aviso de Deprecation e sincroniza melhor)
        # Sincroniza com UTC global para evitar erro -1021 (Timestamp outside window)
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 10000 # Aumentei para 10s para aceitar lags de rede
        
        query_string = urlencode(params)
        signature = hmac.new(SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        url = f"{BASE_URL}{endpoint}?{query_string}&signature={signature}"
        
        try:
            response = self.session.request(method, url)
            return self._handle_response(response)
        except Exception as e:
            print(f"❌ ERRO CRÍTICO DE CONEXÃO: {e}")
            return None

    def _send_public_request(self, endpoint, params=None):
        try:
            return self._handle_response(self.session.get(f"{BASE_URL}{endpoint}", params=params))
        except: return None

    def _handle_response(self, response):
        if response.status_code == 200:
            return response.json()
        
        # --- DEBUG VISUAL ---
        # Aqui vamos ver exatamente por que a Binance está rejeitando a ordem
        print(f"\n🚨 ERRO API BINANCE [{response.status_code}]:")
        print(f"   Mensagem: {response.text}")
        print(f"   URL Tentada: {response.url.split('?')[0]}") # Mostra endpoint sem vazar chaves
        print("-" * 30)
        
        return None

    # --- 💰 Gestão Financeira (O Auditor) ---
    def get_usdt_balance(self):
        """Retorna apenas o USDT Livre na carteira"""
        if SIMULATION_MODE:
            # Em simulação, calculamos: Saldo Inicial - Custo das Posições Abertas + Lucro das Fechadas
            # Simplificação: Usamos um campo simulado no JSON se quiséssemos persistência perfeita.
            # Aqui faremos uma aproximação baseada no equity.
            invested = sum(p['amount_usdt'] for p in self.data['active_positions'].values())
            return SIMULATION_START_BALANCE - invested # (Isso é simplificado, não considera lucro realizado acumulado)
            
        data = self._send_signed_request('GET', '/api/v3/account')
        if not data: return 0.0
        for asset in data['balances']:
            if asset['asset'] == 'USDT':
                return float(asset['free'])
        return 0.0

    def get_total_equity(self):
        """
        Calcula o PATRIMÔNIO LÍQUIDO REAL.
        Equity = USDT Livre + Valor Atual de todas as posições abertas.
        """
        usdt_free = self.get_usdt_balance()
        positions_value = 0.0
        
        # Itera sobre posições abertas para somar valor atual
        # Precisamos fazer cópia das chaves para evitar erro se o dicionário mudar durante iteração
        active_symbols = list(self.data['active_positions'].keys())
        
        for symbol in active_symbols:
            pos_data = self.data['active_positions'][symbol]
            current_price = self.get_current_price(symbol)
            
            if current_price:
                # Estima a quantidade de moedas (Amount Investido / Preço de Compra)
                # Obs: Em produção real, consulte a API '/account' para pegar a quantidade exata de moedas
                qty = pos_data['amount_usdt'] / pos_data['buy_price']
                current_val = qty * current_price
                positions_value += current_val
            else:
                # Se falhar a API, assume valor de entrada para não quebrar o cálculo
                positions_value += pos_data['amount_usdt']

        total_equity = usdt_free + positions_value
        
        # Ajuste para modo simulação manter coerência visual (adiciona lucros passados se necessário)
        if SIMULATION_MODE and not self.data['active_positions']:
            total_equity = SIMULATION_START_BALANCE 

        return total_equity

    def print_financial_report(self):
        """Imprime o relatório financeiro solicitado"""
        current_equity = self.get_total_equity()
        
        # Calcula flutuação desde o último ciclo
        delta = current_equity - self.last_equity_check
        pct_change = (delta / self.last_equity_check) * 100 if self.last_equity_check > 0 else 0.0
        
        # Cor da flutuação para o terminal
        color = "\033[92m" if pct_change >= 0 else "\033[91m" # Verde ou Vermelho
        reset = "\033[0m"
        
        print(f"\n📊 RELATÓRIO FINANCEIRO [{self.get_timestamp_brt()}]")
        print(f"   💵 Patrimônio Total: ${current_equity:.2f} USDT")
        print(f"   📈 Flutuação Ciclo:  {color}{pct_change:+.3f}% ({delta:+.2f} USDT){reset}")
        print(f"   🎒 Posições Abertas: {len(self.data['active_positions'])}")
        print("-" * 40)
        
        # Persiste os dados
        self.log_history(current_equity, pct_change)
        
        # Atualiza referência para o próximo loop
        self.last_equity_check = current_equity
        self.data["wallet_summary"]["current_equity"] = current_equity
        self.save_data()

    # --- Lógica de Mercado (Métodos Anteriores Mantidos) ---
    def get_current_price(self, symbol):
        res = self._send_public_request('/api/v3/ticker/price', {'symbol': symbol})
        return float(res['price']) if res else None

    def get_market_candidates(self):
        print("🔍 Escaneando oportunidades...")
        tickers = self._send_public_request('/api/v3/ticker/24hr')
        if not tickers: return []
        
        candidates = []
        for t in tickers:
            symbol = t['symbol']
            if not symbol.endswith(SYMBOL_QUOTE) or symbol in IGNORED_COINS: continue
            if float(t['quoteVolume']) < MIN_VOLUME_USDT: continue
            if symbol in self.data['active_positions']: continue # Checa no novo local do JSON

            candidates.append({
                'symbol': symbol,
                'price': float(t['lastPrice']),
                'change': float(t['priceChangePercent'])
            })
        candidates.sort(key=lambda x: abs(x['change']), reverse=True)
        return candidates[:5]

    def get_klines(self, symbol):
        data = self._send_public_request('/api/v3/klines', {'symbol': symbol, 'interval': '1h', 'limit': 60})
        return [float(c[4]) for c in data] if data else []

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1: return None
        gains, losses = [], []
        for i in range(1, len(prices)):
            delta = prices[i] - prices[i-1]
            gains.append(max(delta, 0))
            losses.append(abs(min(delta, 0)))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0: return 100.0
        return 100 - (100 / (1 + (avg_gain / avg_loss)))

    def calculate_position_size(self, symbol, rsi):
        available_balance = self.get_usdt_balance()
        MIN_ORDER_VALUE = 6.0
        
        if available_balance < MIN_ORDER_VALUE: return 0.0
        
        if rsi < 20: allocation_pct = 0.50
        elif rsi < 25: allocation_pct = 0.35
        else: allocation_pct = 0.20

        amount = available_balance * allocation_pct
        if amount < MIN_ORDER_VALUE: amount = MIN_ORDER_VALUE
        if amount > available_balance: amount = available_balance
        return amount

    # --- Execução Atualizada para Nova Estrutura JSON ---
    def open_position(self, symbol, price, rsi):
        amount_usdt = self.calculate_position_size(symbol, rsi)
        if amount_usdt == 0: return

        print(f"   🚀 COMPRANDO {symbol} a {price} (Alvo: ${amount_usdt:.2f})")
        
        if not SIMULATION_MODE:
            params = {'symbol': symbol, 'side': 'BUY', 'type': 'MARKET', 'quoteOrderQty': round(amount_usdt, 2)}
            res = self._send_signed_request('POST', '/api/v3/order', params)
            if not res: return
        
        # Salva na estrutura nova
        self.data['active_positions'][symbol] = {
            'buy_price': price,
            'amount_usdt': amount_usdt,
            'rsi_at_entry': rsi,
            'entry_time': self.get_timestamp_brt()
        }
        self.save_data()
        print(f"   ✅ {symbol} registrado no sistema.")

    def close_position(self, symbol, current_price, reason):
        print(f"   💰 VENDENDO {symbol} a {current_price} ({reason})")
        
        if not SIMULATION_MODE:
            # Em produção, adicionar lógica de envio de ordem SELL aqui
            pass 

        # Cálculo de PnL
        pos_data = self.data['active_positions'][symbol]
        buy_price = pos_data['buy_price']
        profit_pct = ((current_price - buy_price) / buy_price) * 100
        profit_usdt = (pos_data['amount_usdt'] * (profit_pct / 100))
        
        print(f"   📉 PnL Trade: {profit_pct:.2f}% (${profit_usdt:+.2f})")
        
        # Remove da lista de ativos
        del self.data['active_positions'][symbol]
        self.save_data()

    def manage_portfolio(self):
        if not self.data['active_positions']: return
        
        active_symbols = list(self.data['active_positions'].keys())
        for symbol in active_symbols:
            pos_data = self.data['active_positions'][symbol]
            current_price = self.get_current_price(symbol)
            if not current_price: continue

            buy_price = pos_data['buy_price']
            pct_change = (current_price - buy_price) / buy_price
            
            # Checa saída
            if pct_change >= TAKE_PROFIT:
                self.close_position(symbol, current_price, "TAKE PROFIT ✅")
            elif pct_change <= STOP_LOSS:
                self.close_position(symbol, current_price, "STOP LOSS ❌")

    def run(self):
        print(f"🤖 Bot Iniciado - {self.get_timestamp_brt()}")
        print(f"📁 Database: {PORTFOLIO_FILE}")
        
        while True:
            try:
                # 1. Relatório Financeiro (Print solicitado)
                self.print_financial_report()

                # 2. Gestão de Carteira
                self.manage_portfolio()

                # 3. Scanner
                top_coins = self.get_market_candidates()
                for coin in top_coins:
                    symbol = coin['symbol']
                    prices = self.get_klines(symbol)
                    rsi = self.calculate_rsi(prices)
                    
                    if rsi and rsi <= RSI_BUY_THRESHOLD:
                        print(f"   💎 {symbol} RSI: {rsi:.2f}")
                        self.open_position(symbol, prices[-1], rsi)
                    
                    time.sleep(0.5) # Respeita rate limit

                print("⏳ Aguardando próximo ciclo...")
                time.sleep(60)

            except KeyboardInterrupt:
                print("\n🛑 Encerrando...")
                break
            except Exception as e:
                print(f"❌ Erro Crítico: {e}")
                time.sleep(10)

if __name__ == "__main__":
    bot = BinanceBot()
    bot.run()