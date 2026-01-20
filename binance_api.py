import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from config import API_KEY, SECRET_KEY, BASE_URL

class BinanceClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'X-MBX-APIKEY': API_KEY})

    def _send(self, method, endpoint, params=None, signed=False):
        if params is None: params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = 60000
            query = urlencode(params)
            sig = hmac.new(SECRET_KEY.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
            url = f"{BASE_URL}{endpoint}?{query}&signature={sig}"
        else:
            url = f"{BASE_URL}{endpoint}"
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params if not signed else None)
            else:
                response = self.session.request(method, url)
                
            if response.status_code == 200:
                return response.json()
            
            print(f"\n🚨 ERRO API [{response.status_code}]: {response.text}")
            return None
        except Exception as e:
            print(f"❌ ERRO CONEXÃO: {e}")
            return None

    def get_account(self):
        return self._send('GET', '/api/v3/account', signed=True)

    def get_ticker_24hr(self):
        return self._send('GET', '/api/v3/ticker/24hr')

    def get_price(self, symbol):
        res = self._send('GET', '/api/v3/ticker/price', {'symbol': symbol})
        return float(res['price']) if res else None

    def get_klines(self, symbol, interval='1h', limit=110): # <--- Aumentado para 110
        res = self._send('GET', '/api/v3/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})
        # Retorna tupla (Close, Volume) para calcularmos preço e RVOL
        # Index 4 = Close Price, Index 5 = Volume
        return [(float(x[4]), float(x[5])) for x in res] if res else []

    def place_order(self, symbol, side, qty_usdt):
        params = {
            'symbol': symbol, 'side': side, 'type': 'MARKET',
            'quoteOrderQty': round(qty_usdt, 2)
        }
        return self._send('POST', '/api/v3/order', params, signed=True)
    
    def get_symbol_step_size(self, symbol):
        """Busca a precisão (LOT_SIZE) exigida pela Binance para o par."""
        # Endpoint público, não gasta peso de API assinada
        data = self._send('GET', '/api/v3/exchangeInfo', {'symbol': symbol})
        
        if not data or 'symbols' not in data:
            return None

        # Procura o filtro LOT_SIZE dentro da resposta gigante
        for f in data['symbols'][0]['filters']:
            if f['filterType'] == 'LOT_SIZE':
                return float(f['stepSize'])
        
        return None