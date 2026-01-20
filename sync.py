import config
from binance_api import BinanceClient
from storage import PortfolioManager
import time

print("🔄 INICIANDO SINCRONIZAÇÃO (SQLite v2)...")

api = BinanceClient()
db = PortfolioManager()

# 1. Pega saldo real da Binance
print("📡 Buscando saldos na Binance...")
try:
    acc = api.get_account()
except Exception as e:
    print(f"❌ Erro crítico ao buscar conta: {e}")
    exit()

real_balances = {}
current_usdt = 0.0

if acc:
    for b in acc['balances']:
        asset = b['asset']
        free = float(b['free'])
        locked = float(b['locked'])
        amount = free + locked
        
        # Guarda saldo de USDT (caixa livre)
        if asset == 'USDT':
            current_usdt = amount
            continue

        if amount > 0:
            symbol = f"{asset}USDT"
            
            # --- BLINDAGEM CONTRA ERRO -1121 ---
            try:
                # Tenta pegar preço. Se a moeda não tiver par USDT (ex: LDUSDT, NFT), falha silenciosamente.
                price = api.get_price(symbol)
                
                if price:
                    value_usdt = amount * price
                    # Filtro de Poeira: Só importa se valer mais de $1.00
                    if value_usdt > 1.0: 
                        real_balances[symbol] = {
                            'amount': amount,
                            'current_price': price,
                            'value_usdt': value_usdt
                        }
                        print(f"   ✅ Ativo: {symbol} | Qtd: {amount:.4f} | ${value_usdt:.2f}")
                else:
                    # Se price for None (API tratou erro mas não retornou valor)
                    pass
            except Exception as e:
                # Se der erro de Invalid Symbol, apenas ignoramos
                # print(f"   ⚠️ Ignorando ativo não-negociável: {asset}")
                continue

# 2. Compara com Banco de Dados Local (SQLite)
print("\n🔍 Comparando com Banco de Dados...")

# Acessa dados via propriedade .data (método de compatibilidade)
db_data = db.data 
local_positions = db_data['active_positions']
local_symbols = list(local_positions.keys())

# A. Adiciona o que está faltando (Recupera TIA e EIGEN)
for symbol, data in real_balances.items():
    if symbol not in local_symbols:
        print(f"   📥 IMPORTANDO: {symbol} (Detectado na Binance mas ausente no Bot)")
        
        # Recupera para o banco
        # Nota: RSI entra como 50 (neutro) pois perdemos o histórico original
        db.add_position(symbol, data['current_price'], data['value_usdt'], 50.0)

# B. Remove o que não existe mais (Limpeza)
for symbol in local_symbols:
    if symbol not in real_balances:
        print(f"   🗑️ LIMPANDO: {symbol} (Consta no Bot mas saldo é zero na Binance)")
        db.remove_position(symbol)

# 3. Atualiza Saldo Total (Equity)
print("\n💵 Recalculando Equity Total...")
total_equity = current_usdt

# Recarrega dados do banco atualizado
db_data = db.data
for symbol, data in db_data['active_positions'].items():
    price = api.get_price(symbol)
    if price:
        # Recalcula valor atual baseado na quantidade gravada
        qty = data['amount_usdt'] / data['buy_price'] # Estimativa baseada na entrada
        
        # Tenta refinar a quantidade usando o saldo real que acabamos de ler, se disponível
        if symbol in real_balances:
            qty = real_balances[symbol]['amount']
            
        position_val = qty * price
        total_equity += position_val

# Atualiza na tabela wallet
db.update_wallet_summary(total_equity)

print(f"✅ Sincronização Concluída.")
print(f"   💰 Equity Calculado: ${total_equity:.2f}")
print(f"   💵 Caixa Livre (USDT): ${current_usdt:.2f}")