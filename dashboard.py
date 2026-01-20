from nicegui import ui, app
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import asyncio

# Importa sua classe de conexão com o SQLite
from storage import PortfolioManager

# Inicializa conexão com o banco
db = PortfolioManager()

# ==============================================================================
# 1️⃣ ESTADO DA APLICAÇÃO (STATE MANAGEMENT)
# ==============================================================================
class AppState:
    def __init__(self):
        self.raw_data = {}
        self.df_pos = pd.DataFrame()
        self.df_hist = pd.DataFrame()
        # Filtros
        self.filter_time_hours = 24
        self.filter_symbols = []
        self.filter_min_invest = 0.0
        self.filter_max_invest = 500.0

state = AppState()

# ==============================================================================
# 2️⃣ COMPONENTES DE VISUALIZAÇÃO
# ==============================================================================

# --- Cabeçalho de KPIs ---
with ui.row().classes('w-full gap-4 mb-4'):
    with ui.card().classes('flex-1 bg-slate-800'):
        ui.label('Equity Total').classes('text-gray-400 text-sm')
        kpi_equity = ui.label('$0.00').classes('text-3xl font-bold')
        kpi_fluct = ui.label('0.00%').classes('text-sm')

    with ui.card().classes('flex-1 bg-slate-800'):
        ui.label('Ativos / Exposição').classes('text-gray-400 text-sm')
        kpi_positions = ui.label('0 / $0.00').classes('text-2xl font-bold')
    
    with ui.card().classes('flex-1 bg-slate-800'):
        ui.label('Última Atualização').classes('text-gray-400 text-sm')
        kpi_update = ui.label('--:--:--').classes('text-xl font-mono')

# --- Abas Principais ---
with ui.tabs().classes('w-full') as tabs:
    tab_macro = ui.tab('📈 Visão Macro (Equity)')
    tab_micro = ui.tab('🎒 Gestão Micro (Carteira)')

with ui.tab_panels(tabs, value=tab_macro).classes('w-full bg-transparent'):
    
    # PAINEL 1: MACRO (Gráfico)
    with ui.tab_panel(tab_macro):
        with ui.card().classes('w-full h-96 bg-slate-800 p-0'):
            chart_equity = ui.plotly({}).classes('w-full h-full')

    # PAINEL 2: MICRO (Tabela Rica)
    with ui.tab_panel(tab_micro):
        grid_positions = ui.aggrid({
            'defaultColDef': {'sortable': True, 'resizable': True, 'filter': True},
            'columnDefs': [
                {'headerName': 'Ativo', 'field': 'symbol', 'checkboxSelection': True, 'headerCheckboxSelection': True},
                {'headerName': 'Investido ($)', 'field': 'amount', 'valueFormatter': "x.toFixed(2)"},
                {'headerName': 'Entrada ($)', 'field': 'entry_price'},
                {'headerName': 'Topo Trailing ($)', 'field': 'high_price'},
                {'headerName': 'PnL Est. (%)', 'field': 'pnl_est', 
                 'cellStyle': {'color': 'params.value > 0 ? "#4ade80" : params.value < 0 ? "#f87171" : "#fbbf24"'}},
                {'headerName': 'Data Entrada', 'field': 'entry_time'}
            ],
            'rowData': [],
            'rowSelection': 'multiple',
            'pagination': True,
            'paginationPageSize': 10
        }).classes('w-full h-128 ag-theme-balham-dark')

# ==============================================================================
# 3️⃣ SIDEBAR DE FILTROS
# ==============================================================================
with ui.left_drawer(fixed=False).classes('bg-slate-900 q-pa-md') as drawer:
    ui.label('🎛️ Painel do Analista').classes('text-xl font-bold mb-6 text-blue-400')

    # Filtro de Tempo
    ui.label('⏳ Janela de Tempo (Gráfico)').classes('text-gray-400 mt-4')
    filter_time = ui.toggle({1: '1h', 6: '6h', 24: '24h', 168: '7d'}, value=24).bind_value(state, 'filter_time_hours')

    ui.separator().classes('my-4 bg-gray-700')

    # Filtro de Ativos
    ui.label('🪙 Filtrar Ativos').classes('text-gray-400')
    filter_pos_select = ui.select(options=[], multiple=True, label='Selecione').bind_value(state, 'filter_symbols').classes('w-full')

    ui.separator().classes('my-4 bg-gray-700')

    # Filtro de Valor
    ui.label('💰 Range de Investimento ($)').classes('text-gray-400 mb-6')
    with ui.row().classes('w-full justify-between text-xs text-gray-500'):
        lbl_min_invest = ui.label('$0')
        lbl_max_invest = ui.label('$500')
        
    filter_invest = ui.range(min=0, max=500, step=1, value={'min': 0, 'max': 500}).classes('w-full')
    filter_invest.on('update:model-value', 
                     lambda e: (setattr(state, 'filter_min_invest', e['min']),
                                setattr(state, 'filter_max_invest', e['max']),
                                lbl_min_invest.set_text(f'${e["min"]}'),
                                lbl_max_invest.set_text(f'${e["max"]}')))

# ==============================================================================
# 4️⃣ LÓGICA DE ATUALIZAÇÃO
# ==============================================================================
async def update_dashboard():
    try:
        # Lê do SQLite
        state.raw_data = db.data 
        if not state.raw_data: return

        # --- PROCESSAMENTO ---
        equity = state.raw_data.get('wallet_summary', {}).get('current_equity', 0.0)
        last_update = state.raw_data.get('metadata', {}).get('updated_at', '')

        # Positions Dataframe
        positions_dict = state.raw_data.get('active_positions', {})
        if positions_dict:
            df = pd.DataFrame.from_dict(positions_dict, orient='index')
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'symbol'}, inplace=True)
            df['pnl_est'] = ((df['highest_price'] - df['buy_price']) / df['buy_price'] * 100).round(2)
            state.df_pos = df
        else:
            state.df_pos = pd.DataFrame()

        # History Dataframe
        history_list = state.raw_data.get('balance_history', [])
        if history_list:
            df_h = pd.DataFrame(history_list)
            df_h['timestamp'] = pd.to_datetime(df_h['timestamp'])
            col_eq = 'equity' if 'equity' in df_h.columns else 'equity_usdt'
            df_h['equity_final'] = df_h[col_eq] if col_eq in df_h.columns else 0.0
            state.df_hist = df_h
        else:
            state.df_hist = pd.DataFrame()

        # --- UI UPDATE ---
        
        # 1. KPIs
        kpi_equity.set_text(f'${equity:.2f}')
        kpi_update.set_text(str(last_update).split(' ')[-1] if last_update else '--:--')
        
        exposure = state.df_pos['amount_usdt'].sum() if not state.df_pos.empty else 0.0
        count = len(state.df_pos)
        kpi_positions.set_text(f'{count} / ${exposure:.2f}')

        if not state.df_hist.empty:
            last_entry = state.df_hist.iloc[-1]
            fluct = last_entry.get('fluctuation', '0.00%')
            kpi_fluct.set_text(fluct)
            color = 'text-green-400' if '+' in fluct else ('text-red-400' if '-' in fluct else 'text-yellow-400')
            kpi_fluct.classes(replace=color)

        # 2. Filtros Dinâmicos
        if not state.df_pos.empty:
            all_symbols = sorted(state.df_pos['symbol'].unique().tolist())
            filter_pos_select.set_options(all_symbols)
            
            max_invest_found = state.df_pos['amount_usdt'].max()
            if max_invest_found > filter_invest.max:
                 filter_invest.props(f'max={max_invest_found + 50}')
                 lbl_max_invest.set_text(f'${state.filter_max_invest}')

        # 3. Tabela Micro
        df_filtered_pos = state.df_pos.copy()
        if not df_filtered_pos.empty:
            if state.filter_symbols:
                df_filtered_pos = df_filtered_pos[df_filtered_pos['symbol'].isin(state.filter_symbols)]
            
            df_filtered_pos = df_filtered_pos[
                (df_filtered_pos['amount_usdt'] >= state.filter_min_invest) & 
                (df_filtered_pos['amount_usdt'] <= state.filter_max_invest)
            ]
            
            row_data = []
            for _, row in df_filtered_pos.iterrows():
                row_data.append({
                    'symbol': row['symbol'],
                    'amount': row['amount_usdt'],
                    'entry_price': row['buy_price'],
                    'high_price': row['highest_price'],
                    'pnl_est': row['pnl_est'],
                    'entry_time': str(row['entry_time']).split('.')[0]
                })
            grid_positions.options['rowData'] = row_data
            grid_positions.update()

        # 4. Gráfico Macro
        if not state.df_hist.empty:
            cutoff_time = datetime.now() - timedelta(hours=state.filter_time_hours)
            df_chart = state.df_hist[state.df_hist['timestamp'] >= cutoff_time].copy()
            
            if not df_chart.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_chart['timestamp'], 
                    y=df_chart['equity_final'],
                    mode='lines',
                    name='Equity',
                    line=dict(color='#3b82f6', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(59, 130, 246, 0.1)'
                ))
                fig.update_layout(
                    template='plotly_dark',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=40, r=20, t=20, b=40),
                    height=380,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', autorange=True)
                )
                chart_equity.update_figure(fig)

    except Exception as e:
        ui.notify(f"Erro: {str(e)}", type='negative')
        print(f"Erro Dashboard: {e}")

# ==============================================================================
# 5️⃣ INICIALIZAÇÃO
# ==============================================================================
ui.timer(15.0, update_dashboard)

# AQUI ESTAVA O ERRO: Passamos as configurações no run() final
ui.run(
    title="Dex v2 Pro | Terminal",
    dark=True, 
    favicon="📊",
    storage_secret="dex_secret_key",
    port=8080, 
    show=False
)