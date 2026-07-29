import json, os, math, copy
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
EXCHANGE_RATE = 7.2

data_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(data_dir, 'data', 'DATA.json'), encoding='utf-8') as f:
    PRODUCTS = json.load(f)
with open(os.path.join(data_dir, 'data', 'PRICE_DATA.json'), encoding='utf-8') as f:
    PRICES = json.load(f)
with open(os.path.join(data_dir, 'data', 'COUPLING.json'), encoding='utf-8') as f:
    COUPLING = json.load(f)
with open(os.path.join(data_dir, 'data', 'SPEED_DATA.json'), encoding='utf-8') as f:
    SPEEDS = json.load(f)
with open(os.path.join(data_dir, 'static', 'curve_mapping.json'), encoding='utf-8') as f:
    CURVES = json.load(f)

def find_curve(model):
    """Fuzzy match model to available curve PDF"""
    if model in CURVES:
        return CURVES[model]
    # WQAF/WQN use same curves as WQA
    for alias in ('WQAF', 'WQN', 'WQB'):
        if alias in model:
            wqa = model.replace(alias, 'WQA')
            c = find_curve(wqa)
            if c:
                return c
    # Try without QG suffix (autocoupling)
    base = model.replace('QG', '')
    if base in CURVES:
        return CURVES[base]
    # Try truncating last decimal (e.g. 40WQA8-15-1.1 -> 40WQA8-15-1)
    parts = base.rsplit('-', 1)
    if len(parts) == 2 and '.' in parts[1]:
        alt = parts[0] + '-' + parts[1].split('.')[0]
        if alt in CURVES:
            return CURVES[alt]
    return None

SERIES_INFO = {
    'WQA': {'name': 'WQA 系列污水泵', 'name_en': 'WQA Series Sewage Pump', 'color': '#1565c0', 'desc': '高效节能污水泵', 'desc_en': 'High-efficiency sewage pump'},
    'WQAF': {'name': 'WQAF 系列污水泵', 'name_en': 'WQAF Series Sewage Pump', 'color': '#00838f', 'desc': '不锈钢污水泵', 'desc_en': 'Stainless steel sewage pump'},
    'WQB': {'name': 'WQB 系列潜水泵', 'name_en': 'WQB Series Submersible Pump', 'color': '#2e7d32', 'desc': '潜水排污泵', 'desc_en': 'Submersible drainage pump'},
    'WQE': {'name': 'WQE 系列污水泵', 'name_en': 'WQE Series Sewage Pump', 'color': '#e65100', 'desc': '经济型污水泵', 'desc_en': 'Economy sewage pump'},
    'WQF': {'name': 'WQF 系列污水泵', 'name_en': 'WQF Series Sewage Pump', 'color': '#6a1b9a', 'desc': '防腐型污水泵', 'desc_en': 'Anti-corrosion sewage pump'},
    'WQN': {'name': 'WQN 系列污水泵', 'name_en': 'WQN Series Sewage Pump', 'color': '#c62828', 'desc': '耐热型污水泵', 'desc_en': 'High-temp sewage pump'},
}

@app.route('/')
def index():
    mode = request.args.get('mode', '')
    return render_template('index.html', export_mode=(mode == 'export' or os.environ.get('RAILWAY') == '1'))

@app.route('/api/series')
def get_series():
    export = request.args.get('mode') == 'export'
    series_counts = {}
    for p in PRODUCTS:
        s = p['series']
        series_counts[s] = series_counts.get(s, 0) + 1
    result = {}
    for k, v in SERIES_INFO.items():
        item = dict(v)
        item['count'] = series_counts.get(k, 0)
        if export:
            item['name'] = v.get('name_en', v['name'])
            item['desc'] = v.get('desc_en', v['desc'])
        result[k] = item
    return jsonify(result)

@app.route('/api/products')
def get_products():
    series = request.args.get('series', '')
    flow = request.args.get('flow', '')
    head = request.args.get('head', '')

    results = PRODUCTS
    if series:
        results = [p for p in results if p['series'] == series]
    if flow:
        try:
            f = float(flow)
            results = [p for p in results if abs(p['flow'] - f) / max(p['flow'], 0.1) <= 0.3]
        except:
            pass
    if head:
        try:
            h = float(head)
            results = [p for p in results if abs(p['head'] - h) / max(p['head'], 0.1) <= 0.3]
        except:
            pass

    results.sort(key=lambda p: abs(p['flow'] - float(flow or 0)) + abs(p['head'] - float(head or 0)) * 0.5)
    export_mode = request.args.get('mode') == 'export'
    out = results[:50]
    if export_mode:
        out = [{k: v for k, v in p.items() if k not in ('face', 'fob_both')} for p in out]
    return jsonify(out)

@app.route('/api/product/<model>')
def get_product(model):
    product = next((p for p in PRODUCTS if p['model'] == model), None)
    if not product:
        return jsonify({'error': 'not found'}), 404
    price = PRICES.get(model, {})
    speed = SPEEDS.get(model, 1450)
    curve = find_curve(model)
    export_mode = request.args.get('mode') == 'export'
    coupling = copy.deepcopy(COUPLING)
    result = {
        'product': product,
        'price': price,
        'speed': speed,
        'curve': curve,
        'coupling': coupling,
        'export_mode': export_mode,
        'exchange_rate': EXCHANGE_RATE,
    }
    if export_mode:
        result['product'] = {k: v for k, v in product.items() if k not in ('face', 'fob_both')}
        rate = EXCHANGE_RATE
        result['price'] = {k: round(v / rate, 2) if isinstance(v, (int, float)) else v for k, v in price.items()}
        for ctype in coupling:
            for size in coupling[ctype]:
                coupling[ctype][size] = round(coupling[ctype][size] / rate, 2)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=True)
