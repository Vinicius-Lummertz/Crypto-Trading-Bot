import requests
import logging
import time
from typing import Optional

# Configuração de Logs específica para este módulo
logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        """
        Inicializa o notificador do Telegram.
        
        Args:
            bot_token (str): O token gerado pelo @BotFather.
            chat_id (str): O ID numérico do seu usuário ou grupo.
        """
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id
        self.disabled = False
        
        # Validação simples de inicialização
        if not bot_token or not chat_id:
            logger.warning("TelegramNotifier: Token ou Chat ID não configurados. Notificações desativadas.")
            self.disabled = True
        else:
            # Tenta enviar mensagem de boas vindas para validar
            try:
                self.send_message("🤖 Bot de Trading Iniciado! Sistema de notificação online.")
            except Exception as e:
                logger.error(f"Erro ao inicializar Telegram: {e}")
                self.disabled = True

    def send_message(self, message: str) -> bool:
        """
        Envia uma mensagem de texto para o chat configurado.
        Retorna True se sucesso, False caso contrário.
        """
        if self.disabled:
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown" # Permite usar negrito, itálico, monospaced
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Falha ao enviar mensagem Telegram: {e}")
            return False

    def send_alert(self, symbol: str, strategy: str, action: str, price: float, extra_info: str = ""):
        """
        Formata um alerta padrão de trading e envia.
        Ex: 🚨 COMPRA DETECTADA: BTCUSDT
        """
        emoji = "🟢" if "BUY" in action.upper() else "🔴" if "SELL" in action.upper() else "⚠️"
        
        formatted_msg = (
            f"{emoji} **SINAL DE {action.upper()}**\n\n"
            f"🪙 Ativo: `{symbol}`\n"
            f"📈 Preço: `${price:,.4f}`\n"
            f"🧠 Estratégia: _{strategy}_\n"
            f"{extra_info}"
        )
        
        self.send_message(formatted_msg)
