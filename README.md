# 🤖 Crypto Trading Bot - Dual Strategy & Dashboard

Welcome to **Crypto Trading Bot**, an automated cryptocurrency trading system focused on Binance. This project uses a hybrid architecture with **Python** for the trading core and **React** for the monitoring dashboard.

## 🚀 Key Features

### 🧠 Intelligence & Strategies
The bot operates with a **Dual Strategy System**:

1.  **🛡️ Conservative**
    *   Focus on safety and sustainable trends.
    *   Entry based on **Low RSI (< 23)** and trend confirmation (EMA).
    *   High priority in capital allocation.
    *   **Dynamic Trailing Stop (Ladder Strategy)**: The stop moves up as profit increases (Protection -> Trend -> Moonshot).

2.  **⚡ Scalping (Aggressive)**
    *   Focus on quick profits with short movements.
    *   More permissive entry (**RSI < 40**).
    *   **Fixed Targets**: Short Stop Loss (-1%) and Quick Take Profit (+2.5%).
    *   Ideal for sideways markets or high volatility.

### 🧟 "Zombie Mode" Protection
Intelligent system that detects stagnant positions ("zombies") that haven't yielded profit after a certain time. If a **much better** new opportunity (critical RSI) appears and there is no balance, the bot sacrifices the zombie position to enter the new trade.

### 📊 Real-Time Dashboard
Modern interface built in **React + Vite** for you to track everything:
*   Wallet KPIs (Balance, Profit/Loss, Active Positions).
*   Positions Table with real-time PnL.
*   System Logs.
*   **Manual Control**: Panic sell button for each position.

### 📱 Telegram Notifications
Receive instant alerts on your mobile about:
*   New Buys.
*   Sells (Take Profit / Stop Loss).
*   PnL (Profit) Reports when hitting important milestones.

---

## 🛠️ Installation and Configuration

### Prerequisites
*   **Python 3.10+**
*   **Node.js** (for the dashboard)
*   **Binance** Account (with generated API Key and Secret Key)

### 1. Backend Configuration
1.  Clone the repository.
2.  Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    # Windows:
    .\venv\Scripts\activate
    # Linux/Mac:
    source venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Configure environment variables:
    *   Create a `.env` file in the project root.
    *   Add your keys:
        ```env
        BINANCE_API_KEY=your_api_key_here
        BINANCE_SECRET_KEY=your_secret_key_here
        TELEGRAM_BOT_TOKEN=your_telegram_token
        TELEGRAM_CHAT_ID=your_chat_id
        ```

### 2. Frontend Configuration (Dashboard)
1.  Navigate to the `frontend` folder:
    ```bash
    cd frontend
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```

---

## ▶️ How to Run

For the full system to work, you need **3 terminals** running simultaneously:

### Terminal 1: API (Backend)
This service feeds the dashboard with data.
```bash
# In the project root (with venv activated)
python api.py
```
*Access API documentation at: `http://localhost:8000/docs`*

### Terminal 2: Bot (Core)
This is the brain that analyzes the market and executes buys/sells.
```bash
# In the project root (with venv activated)
python main.py
```

### Terminal 3: Dashboard (Frontend)
Visual interface.
```bash
# In the frontend/ folder
npm run dev
```
*Open your browser at the indicated link (usually `http://localhost:5173`).*

---

## ⚙️ Fine Tuning (`config.py`)
You can customize the bot's behavior by editing the `config.py` file:
*   `AMOUNT_TO_TRADE`: Value in USDT per trade.
*   `RSI_BUY_THRESHOLD`: RSI level for conservative buy.
*   `SCALP_ENABLED`: Enable/Disable Scalp mode.
*   `IGNORED_COINS`: Blacklist of coins to not trade.

---

## ⚠️ Disclaimer
**This software is for educational purposes.** The cryptocurrency market is highly volatile and risky. The author is not responsible for financial losses resulting from the use of this bot.
> "Never invest money you cannot afford to lose."
