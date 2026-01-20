import axios from 'axios';

const API_URL = 'http://localhost:8000/api';

export const api = {
    getSummary: () => axios.get(`${API_URL}/summary`).then(res => res.data),
    getPositions: () => axios.get(`${API_URL}/positions`).then(res => res.data),
    getHistory: () => axios.get(`${API_URL}/history`).then(res => res.data),
    getLogs: () => axios.get(`${API_URL}/logs`).then(res => res.data),
    sellPosition: (symbol) => axios.post(`${API_URL}/trade/sell/${symbol}`),
};
