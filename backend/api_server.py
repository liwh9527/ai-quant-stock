#!/usr/bin/env python3
"""
量化交易系统 API
提供REST接口给Web仪表盘
"""

import os
import json
import requests
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logger import get_trades, get_snapshots, get_signals, get_trade_summary, log_trade, log_signal

app = Flask(__name__, static_folder='static')
CORS(app)

MIXIANG_CONFIG = {
    "base_url": "https://mkapi2.dfcfs.com/finskillshub",
    "apikey": os.environ.get("MX_APIKEY", ""),
}


def mixiang_request(endpoint, data=None):
    """妙想API请求"""
    headers = {"Content-Type": "application/json", "apikey": MIXIANG_CONFIG["apikey"]}
    try:
        resp = requests.post(
            f"{MIXIANG_CONFIG['base_url']}{endpoint}",
            headers=headers, json=data or {}, timeout=10
        )
        return resp.json()
    except Exception as e:
        return {"code": "-1", "message": str(e)}


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'dashboard.html')


@app.route('/api/quant/account')
def account():
    """获取账户信息"""
    result = mixiang_request("/api/claw/mockTrading/balance", {"moneyUnit": 1})
    if result.get("code") == "200":
        return jsonify(result.get("data", {}))
    return jsonify({"error": result.get("message", "Unknown error")}), 400


@app.route('/api/quant/positions')
def positions():
    """获取持仓"""
    result = mixiang_request("/api/claw/mockTrading/positions", {"moneyUnit": 1})
    if result.get("code") != "200":
        return jsonify({"error": result.get("message", "Unknown error")}), 400
    
    pos_list = result.get("data", {}).get("posList", []) or []
    positions = []
    for p in pos_list:
        code = p.get('secCode', '')
        name = p.get('secName', '')
        count = p.get('count', 0)
        cost_price = p.get('costPrice', 0)
        cost_dec = p.get('costPriceDec', 3)
        if cost_price > 0:
            cost_price = cost_price / (10 ** cost_dec)
        price = p.get('price', 0)
        price_dec = p.get('priceDec', 2)
        if price > 0:
            price = price / (10 ** price_dec)
        value = p.get('value', 0)
        profit = p.get('profit', 0)
        profit_pct = p.get('profitPct', 0)
        
        if count > 0:
            positions.append({
                'code': code,
                'name': name,
                'count': count,
                'cost_price': round(cost_price, 2),
                'current_price': round(price, 2),
                'value': round(value, 2),
                'profit': round(profit, 2),
                'profit_pct': round(profit_pct, 2),
            })
    
    return jsonify({"positions": positions})


@app.route('/api/quant/trades')
def trades():
    """获取交易记录"""
    days = request.args.get('days', 30, type=int)
    trades = get_trades(days)
    return jsonify({"trades": trades})


@app.route('/api/quant/signals')
def signals():
    """获取信号记录"""
    days = request.args.get('days', 7, type=int)
    signals = get_signals(days)
    return jsonify({"signals": signals})


@app.route('/api/quant/snapshots')
def snapshots():
    """获取每日快照"""
    days = request.args.get('days', 30, type=int)
    snapshots = get_snapshots(days)
    return jsonify({"snapshots": snapshots})


@app.route('/api/quant/stats')
def stats():
    """获取交易统计"""
    summary = get_trade_summary()
    return jsonify(summary)


@app.route('/api/quant/log_trade', methods=['POST'])
def log_trade_api():
    """记录交易"""
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400
    
    log_trade(
        code=data.get('code', ''),
        name=data.get('name', ''),
        action=data.get('action', ''),
        price=data.get('price', 0),
        quantity=data.get('quantity', 0),
        amount=data.get('amount', 0),
        reason=data.get('reason', ''),
        score=data.get('score', 0),
        pnl=data.get('pnl', 0),
        pnlcomm=data.get('pnlcomm', 0),
    )
    return jsonify({"success": True})


@app.route('/api/quant/log_signal', methods=['POST'])
def log_signal_api():
    """记录信号"""
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400
    
    log_signal(
        code=data.get('code', ''),
        name=data.get('name', ''),
        signal_type=data.get('signal_type', ''),
        score=data.get('score', 0),
        indicators=data.get('indicators'),
        executed=data.get('executed', False),
    )
    return jsonify({"success": True})


if __name__ == '__main__':
    # 创建static目录
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=5001, debug=False)
