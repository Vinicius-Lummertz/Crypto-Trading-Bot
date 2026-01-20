import time
import config
from storage import PortfolioManager
from binance_api import BinanceClient
from telegram_notifier import TelegramNotifier
from trade_executor import TradeExecutor
from datetime import datetime, timedelta, timezone
import math

class BotController:
    def __init__(self):
        self.db = PortfolioManager()
        self.api = BinanceClient()
        self.notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        self.executor = TradeExecutor(self.api, self.db, self.notifier)
        
        self.last_equity = 0.0
        self.alert_tracker = set() # Para evitar spam de alertas de PnL
        
        # Cooldown System
        self.cooldowns = {} 
        self.COOLDOWN_TIME_MINUTES = 30

    # --- LÓGICA DE INDICADORES ---
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

    def calculate_ema(self, prices, period=100):
        if len(prices) < period: return None
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period # Começa com SMA simples
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def calculate_rvol(self, volumes):
        # Volume Relativo: Volume da última vela / Média das 24 anteriores
        if len(volumes) < 25: return 1.0
        current_vol = volumes[-1]
        avg_vol = sum(volumes[-25:-1]) / 24
        if avg_vol == 0: return 0.0
        return current_vol / avg_vol

    def find_zombie_position(self, candidate_rsi=100):
        """
        Procura uma posição 'Zumbi' para sacrificar.
        Se o RSI da nova oportunidade for MUITO baixo (<18), ignora o tempo de casa.
        """
        positions = self.db.data['active_positions']
        worst_symbol = None
        worst_pnl = 0.0
        
        # Define urgência
        # Padrão: 2 horas de paciência
        # Urgência (RSI < 18): 0 horas de paciência (Vende qualquer coisa negativa)
        min_hours = 2.0
        if candidate_rsi < 18.0:
            min_hours = 0.0
            print(f"   🚨 URGÊNCIA DETECTADA (RSI {candidate_rsi:.1f}): Ignorando tempo mínimo de posição.")

        now = datetime.now(timezone.utc)
        
        for symbol, data in positions.items():
            # 1. Calcula tempo de casa
            try:
                entry_dt = datetime.strptime(data['entry_time'], '%Y-%m-%d %H:%M:%S')
                # Adiciona info de timezone se o python reclamar de offset-naive vs aware
                # Assumindo que o storage salva sem timezone info explícito mas é UTC/BRT
                entry_dt = entry_dt.replace(tzinfo=datetime.now(timezone.utc)) 
                
                duration = (now - entry_dt).total_seconds() / 3600 
            except:
                duration = 0

            # 2. Calcula PnL atual
            current_price = self.api.get_price(symbol)
            if not current_price: continue
            
            pnl_pct = ((current_price - data['buy_price']) / data['buy_price']) * 100

            # CRITÉRIO DE CORTE DINÂMICO:
            # Se tem mais tempo que o minimo exigido E está no prejuízo
            if duration >= min_hours and pnl_pct < -0.05: # -0.05% margem para não vender 0x0
                print(f"   💀 Candidato a Zumbi: {symbol} (PnL {pnl_pct:.2f}% | {duration:.1f}h)")
                
                if pnl_pct < worst_pnl:
                    worst_pnl = pnl_pct
                    worst_symbol = symbol

        return worst_symbol

    # --- LÓGICA DE TRAILING STOP & GESTÃO ---
    def manage_portfolio(self):
        # 1. Atualiza Auditoria Financeira
        # (Se você já adicionou a chamada no loop run(), pode remover essa linha aqui para não duplicar, 
        # mas deixar aqui não faz mal, só gasta uma chamada de API a mais)
        # self.update_financials() 

        positions = self.db.data['active_positions']
        # Cria uma cópia da lista para poder deletar itens durante o loop sem quebrar
        items = list(positions.items()) 

        for symbol, data in items:
            current_price = self.api.get_price(symbol)
            if not current_price: continue

            # 1. Atualiza Topo Histórico (High Water Mark)
            highest = data['highest_price']
            if current_price > highest:
                highest = current_price
                self.db.update_position_high(symbol, highest)
                # print(f"   📈 {symbol} renovou máxima: ${highest}")

            # 2. CÁLCULO DO STOP DINÂMICO (A Mágica acontece aqui)
            buy_price = data['buy_price']
            
            # Quanto a moeda já subiu no máximo desde a compra?
            max_profit_pct = (highest - buy_price) / buy_price
            
            # Lógica de "Afrouxar o Cinto":
            # Nível 1: Subiu pouco (< 3%) -> Stop Curto (3%) para proteger capital.
            # Nível 2: Subiu médio (> 3%) -> Stop Médio (4.5%).
            # Nível 3: Explodiu (> 7%) -> Stop Longo (6%) para aguentar volatilidade.
            
            if max_profit_pct > 0.07:    # Se já subiu mais de 7%
                current_trailing_pct = 0.06  # Aguenta queda de 6%
                status_label = "MOONSHOT 🚀"
            elif max_profit_pct > 0.03:  # Se já subiu mais de 3%
                current_trailing_pct = 0.045 # Aguenta queda de 4.5%
                status_label = "TENDÊNCIA 📈"
            else:                        # Se acabou de comprar ou está no zero
                current_trailing_pct = 0.025 # Stop curto de 2.5% (Mão de Ferro)
                status_label = "RISCO 🛡️"

            # Calcula o Preço de Gatilho
            drop_price = highest * (1 - current_trailing_pct)
            
            # Calcula recuo atual para mostrar no log
            drop_pct = ((highest - current_price) / highest) * 100

            # Atualiza log visual no terminal (opcional, mas bom pra ver o status)
            # print(f"   Update {symbol}: Topo ${highest:.4f} | Stop ${drop_price:.4f} ({status_label})")

            # 3. VERIFICAÇÃO DE VENDA (Trailing Stop)
            if current_price < drop_price:
                print(f"   📉 STOP ACIONADO PARA {symbol}!")
                print(f"      Topo: ${highest} | Preço Atual: ${current_price}")
                print(f"      Queda: {drop_pct:.2f}% (Limite Dinâmico: {current_trailing_pct*100}%)")
                
                # Executa venda
                self.close_position(symbol, current_price, "Trailing Stop Dinâmico")
            
            # 4. ALERTA DE PNL (Telegram)
            # Avisa se passar de 3% ou 5% de lucro (apenas uma vez por nível)
            pnl_pct = ((current_price - buy_price) / buy_price) * 100
            
            if pnl_pct >= 5.0:
                alert_key = f"{symbol}_5pct"
                if alert_key not in self.alert_tracker:
                    self.notifier.send_message(f"🚀 **{symbol}** explodiu! Lucro atual: **{pnl_pct:.2f}%**")
                    self.alert_tracker.add(alert_key)
                    self.alert_tracker.add(f"{symbol}_3pct") # Assume que já avisou do 3%
            
            elif pnl_pct >= 3.0:
                alert_key = f"{symbol}_3pct"
                if alert_key not in self.alert_tracker:
                    self.notifier.send_message(f"📈 **{symbol}** está indo bem! Lucro atual: **{pnl_pct:.2f}%**")
                    self.alert_tracker.add(alert_key)

    def close_position(self, symbol, price, reason):
        # Delega para o Executor
        success = self.executor.sell_position(symbol, reason)
        
        if success:
            # Limpa tracker de alertas
            self.alert_tracker.discard(f"{symbol}_3pct")
            self.alert_tracker.discard(f"{symbol}_5pct")

            # Desativa Cooldown se tiver lucro (opcional, mas bom pra rodar capital)
            # Mas se foi SWAP urgente, mantemos cooldown pra não comprar a mesma coisa ruim de volta
            if "SWAP" in reason:
                 # Adiciona Cooldown
                cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=self.COOLDOWN_TIME_MINUTES)
                self.cooldowns[symbol] = cooldown_until
                print(f"   ❄️ COOLDOWN: {symbol} bloqueada por {self.COOLDOWN_TIME_MINUTES} min.")

    def update_financials(self):
        # 1. Pega Saldo USDT Livre na Binance
        usdt_free = 0.0
        if not config.SIMULATION_MODE:
            acc = self.api.get_account()
            if acc:
                for b in acc['balances']:
                    if b['asset'] == 'USDT':
                        usdt_free = float(b['free'])
                        break
        else:
            # Em simulação, estimamos o livre subtraindo o alocado do inicial
            invested = sum(p['amount_usdt'] for p in self.db.data['active_positions'].values())
            usdt_free = max(0, 100.0 - invested) # Assumindo 100 inicial

        # 2. Soma Valor das Posições (Mark-to-Market)
        positions_value = 0.0
        positions = self.db.data['active_positions']
        
        for symbol, data in positions.items():
            current_price = self.api.get_price(symbol)
            if current_price:
                # Estima quantidade de moedas
                coin_qty = data['amount_usdt'] / data['buy_price']
                positions_value += (coin_qty * current_price)
            else:
                positions_value += data['amount_usdt'] # Fallback
        
        total_equity = positions_value
        
        # 3. Salva e Loga
        self.db.update_wallet_summary(total_equity)
        
        # Log histórico se mudou significativamente
        fluctuation = 0.0
        if self.last_equity > 0:
            fluctuation = ((total_equity - self.last_equity) / self.last_equity) * 100
            
        self.db.log_history(total_equity, f"{fluctuation:+.2f}%")
        self.last_equity = total_equity
        
        return total_equity

    # --- SCANNER ---
    def scan_market(self):
        print("\n🔍 ESCANEANDO (Filtros: RSI < 30 + Tendência + RVOL)...")
        tickers = self.api.get_ticker_24hr()
        if not tickers: return

        candidates = []
        active_symbols = self.db.data['active_positions']
        
        # 1. Filtro Bruto (Liquidez e Volatilidade)
        for t in tickers:
            sym = t['symbol']
            if not sym.endswith(config.SYMBOL_QUOTE) or sym in config.IGNORED_COINS: continue
            if sym in active_symbols: continue
            if float(t['quoteVolume']) < config.MIN_VOLUME_USDT: continue
            
            candidates.append({'symbol': sym, 'change': float(t['priceChangePercent'])})

        # Ordena pelas que mais caíram/subiram (Interesse do mercado)
        candidates.sort(key=lambda x: abs(x['change']), reverse=True)
        
        # 2. Filtro Fino (Indicadores Técnicos)
        # Analisa até 10 candidatos para achar O MELHOR, não o primeiro que aparecer
        checked_count = 0
        
        for cand in candidates[:15]: 
            sym = cand['symbol']
            # Pega dados (Preço e Volume)
            klines_data = self.api.get_klines(sym, limit=110)
            if not klines_data: continue

            prices = [x[0] for x in klines_data]
            volumes = [x[1] for x in klines_data]

            # A. Calcula RSI
            rsi = self.calculate_rsi(prices)
            if not rsi or rsi > config.RSI_BUY_THRESHOLD: 
                continue # Falhou no RSI, ignora

            # B. Calcula EMA (Tendência)
            # Queremos comprar apenas se o preço estiver ACIMA da EMA 100 (Tendência de Alta)
            # OU se estivermos agressivos, podemos ignorar isso, mas para segurança é bom.
            ema = self.calculate_ema(prices, period=100)
            current_price = prices[-1]
            
            trend_ok = True
            if ema and current_price < ema:
                # O preço está abaixo da média de 100 períodos. É uma tendência de baixa.
                # Só compramos se o RSI for MUITO baixo (Ex: < 20) para justificar o risco.
                if rsi > 20: 
                    trend_ok = False
            
            # C. Calcula RVOL (Volume Relativo)
            # Queremos ver se o volume está aumentando (interesse comprador)
            rvol = self.calculate_rvol(volumes)
            
            # LOG DO CANDIDATO (Feedback visual do porquê comprou ou rejeitou)
            status_icon = "✅" if trend_ok else "❌"
            print(f"   🧐 {sym:<10} | RSI: {rsi:.1f} | EMA: {status_icon} | RVOL: {rvol:.1f}x")

            if trend_ok:
                
                success = self.execute_buy(sym, current_price, rsi)
                
                if not success: 
                    # --- LÓGICA DE SWAP (NOVO) ---
                    # Se falhou por saldo E o sinal é MUITO bom (RSI < 20), tenta trocar
                    if rsi < 20:
                        print(f"   🔄 Sem saldo para {sym}. Procurando Zumbis para troca...")
                        zombie = self.find_zombie_position(candidate_rsi=rsi)
                        
                        if zombie:
                            print(f"   ⚔️ TROCA TÁTICA: Vendendo {zombie} para comprar {sym}")
                            self.close_position(zombie, self.api.get_price(zombie), "SWAP por Oportunidade Melhor")
                            time.sleep(2) # Espera vender e liberar saldo
                            self.execute_buy(sym, current_price, rsi) # Tenta comprar de novo
                        else:
                            print("   ❄️ Nenhuma posição Zumbi encontrada (todas recentes ou no lucro).")
                
                if success or (rsi < 20 and zombie): # Se comprou ou trocou, para o scanner
                    break
            
            time.sleep(0.2) # Delay leve

    def execute_buy(self, symbol, price, rsi):
        # --- GESTÃO DE CAPITAL PARA PEQUENAS CONTAS ---
        # Objetivo: Abrir o máximo de posições possíveis com o saldo disponível.
        
        balance = 0.0
        if not config.SIMULATION_MODE:
            acc = self.api.get_account()
            if acc:
                for b in acc['balances']:
                    if b['asset'] == 'USDT': balance = float(b['free'])
        else:
            balance = 100.0 # Simulação

        # Custo mínimo operacional (Binance pede $5, usamos $5.5 para garantir taxas e flutuação)
        # Isso maximiza o número de "balas" que temos para atirar.
        MIN_VIABLE_TRADE = 5.5 

        if balance < MIN_VIABLE_TRADE:
            # Se o saldo for menor que o mínimo, não adianta tentar, a API rejeita (Erro -2010)
            # Mas aqui podemos adicionar um log silencioso ou warning apenas se for muito critico
            # print(f"   ⚠️ Saldo insuficiente (${balance:.2f}) para {symbol}")
            return False

        # Definimos o valor da compra.
        # Em vez de % da banca, usamos o valor fixo mínimo para diversificar ao máximo.
        amount = MIN_VIABLE_TRADE

        # Trava de segurança: Se o saldo for tipo $5.80, usa tudo ($5.80) em vez de tentar guardar $0.30
        if balance < (MIN_VIABLE_TRADE * 1.5):
            amount = balance

        # Arredonda para 2 casas para evitar erros de precisão na API
        amount = round(amount - 0.1, 2) # Tira 10 centavos para garantir que não vai faltar taxa

        print(f"   🚀 COMPRANDO {symbol} | RSI {rsi:.2f} | Alvo: ${amount:.2f}")
        
        if not config.SIMULATION_MODE:
            res = self.api.place_order(symbol, 'BUY', amount)
            if not res: return False
        
        self.db.add_position(symbol, price, amount, rsi)
        
        # Notifica Telegram
        self.notifier.send_alert(symbol, "RSI Oversold", "BUY", price, f"📉 RSI: {rsi:.1f}")

        return True

    # --- LOOP ---
    def run(self):
        print(f"🤖 BOT V2 INICIADO (Trailing Stop Ativo)")
        print(f"📂 Configuração: Queda Max {config.TRAILING_DROP_PERCENT*100}% do Topo")
        
        while True:
            try:

                equity = self.update_financials()    
                # 1. Auditoria e Trailing Stop
                self.manage_portfolio()
                
                # 2. Novas Compras
                self.scan_market()
                
                print("\n⏳ Aguardando 60s...")
                time.sleep(60)
                
            except KeyboardInterrupt:
                print("\n🛑 Parando...")
                break
            except Exception as e:
                print(f"❌ Erro Loop: {e}")
                time.sleep(10)

if __name__ == "__main__":
    BotController().run()