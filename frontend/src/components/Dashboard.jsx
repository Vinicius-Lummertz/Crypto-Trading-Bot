import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import KPISection from './KPISection';
import EquityChart from './EquityChart';
import PositionsTable from './PositionsTable';
import ScannerLog from './ScannerLog';
import { RefreshCw, ShieldCheck } from 'lucide-react';

const Dashboard = () => {
    // 1. Fetch Summary (Wallet & KPIs)
    const summaryQuery = useQuery({
        queryKey: ['summary'],
        queryFn: api.getSummary,
        refetchInterval: 5000, // 5s
    });

    // 2. Fetch Active Positions
    const positionsQuery = useQuery({
        queryKey: ['positions'],
        queryFn: api.getPositions,
        refetchInterval: 2000, // 2s for live prices
    });

    // 3. Fetch History (Chart)
    const historyQuery = useQuery({
        queryKey: ['history'],
        queryFn: api.getHistory,
        refetchInterval: 60000, // 1 min
    });

    // 4. Fetch Logs
    const logsQuery = useQuery({
        queryKey: ['logs'],
        queryFn: api.getLogs,
        refetchInterval: 2000, // 2s
    });

    if (summaryQuery.isLoading || positionsQuery.isLoading) {
        return (
            <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 animate-pulse">
                Loading Dashboard...
            </div>
        );
    }

    if (summaryQuery.isError) {
        return (
            <div className="min-h-screen bg-slate-950 flex items-center justify-center text-rose-500">
                Error connecting to API. Is the backend running?
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-950 p-6 md:p-8 font-sans text-slate-200">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <header className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
                    <div>
                        <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
                            DEX V2 Dashboard
                        </h1>
                        <p className="text-slate-500 text-sm mt-1 flex items-center gap-2">
                            <ShieldCheck className="w-4 h-4 text-emerald-500" />
                            System Operational • Last Update: {summaryQuery.data.updated_at}
                        </p>
                    </div>
                    <button
                        onClick={() => {
                            summaryQuery.refetch();
                            positionsQuery.refetch();
                            historyQuery.refetch();
                            logsQuery.refetch();
                        }}
                        className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm font-medium transition-colors border border-slate-700"
                    >
                        <RefreshCw className="w-4 h-4" />
                        Refresh Data
                    </button>
                </header>

                {/* KPIs */}
                <KPISection data={summaryQuery.data} />

                {/* Main Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                    {/* Chart (2/3 width) */}
                    <div className="lg:col-span-2">
                        <EquityChart history={historyQuery.data} />
                    </div>

                    {/* Logs (1/3 width) */}
                    <div className="lg:col-span-1">
                        <ScannerLog logs={logsQuery.data} />
                    </div>
                </div>

                {/* Positions Table */}
                <PositionsTable positions={positionsQuery.data} />
            </div>
        </div>
    );
};

export default Dashboard;
