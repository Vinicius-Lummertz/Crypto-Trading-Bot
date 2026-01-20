import React, { useEffect, useRef } from 'react';

const ScannerLog = ({ logs }) => {
    const scrollRef = useRef(null);

    // Auto-scroll to bottom when new logs arrive
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);

    if (!logs || logs.length === 0) {
        return (
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 font-mono text-sm h-64 flex items-center justify-center text-slate-600">
                Waiting for system logs...
            </div>
        );
    }

    return (
        <div className="bg-slate-950 rounded-xl border border-slate-800 font-mono text-sm h-64 flex flex-col shadow-inner">
            <div className="p-2 border-b border-slate-800 bg-slate-900/50 text-xs text-slate-500 uppercase tracking-wider font-semibold px-4">
                System Terminal
            </div>
            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-4 space-y-1 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent"
            >
                {logs.slice().reverse().map((log, index) => (
                    <div key={index} className="flex gap-3">
                        <span className="text-slate-600 shrink-0">[{log.timestamp.split(' ')[1]}]</span>
                        <span className={`
              ${log.level === 'INFO' ? 'text-blue-400' : ''}
              ${log.level === 'WARNING' ? 'text-amber-400' : ''}
              ${log.level === 'ERROR' ? 'text-rose-400' : ''}
              ${log.level === 'SUCCESS' ? 'text-emerald-400' : ''}
            `}>
                            {log.message}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ScannerLog;
