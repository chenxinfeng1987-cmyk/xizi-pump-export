import os, json, re
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置
EXPORT_MODE = True
EXCHANGE_RATE = 6.7

# 加载数据
def load_json(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

DATA = load_json('data/DATA.json')
PRICE_DATA = load_json('pricing_data.json')
COUPLING = load_json('data/COUPLING.json')
SPEED_DATA = load_json('data/SPEED_DATA.json')
PUMP_WEIGHT = load_json('data/PUMP_WEIGHT.json') if os.path.exists(os.path.join(BASE_DIR, 'data', 'PUMP_WEIGHT.json')) else {}

# pricing_data.json 包含所有数据
if 'PUMP_WEIGHT' in PRICE_DATA:
    PUMP_WEIGHT = PRICE_DATA['PUMP_WEIGHT']
if 'SPEED_DATA' in PRICE_DATA:
    SPEED_DATA = PRICE_DATA['SPEED_DATA']
if 'COUPLING' in PRICE_DATA:
    COUPLING = PRICE_DATA['COUPLING']
SENSOR_PRICES = PRICE_DATA.get('SENSOR_PRICES', {'vibration': 2200, 'pt100': 350, 'protector': 350})
ACC = PRICE_DATA.get('ACC', {})

# 系列信息
SERIES_INFO = {
    'WQA': {'en': 'WQA Sewage Pump', 'zh': 'WQA潜水排污泵'},
    'WQ': {'en': 'WQ Sewage Pump', 'zh': 'WQ潜水排污泵'},
    'WQN': {'en': 'WQN Internal Cooling', 'zh': 'WQN内循环冷却'},
    'WQF': {'en': 'WQF Sewage Pump', 'zh': 'WQF潜水排污泵'},
    'WQB': {'en': 'WQB Explosion-proof', 'zh': 'WQB防爆型'},
    'WQAF': {'en': 'WQAF Stainless Steel', 'zh': 'WQAF不锈钢'},
    'WQE': {'en': 'WQE Economy', 'zh': 'WQE经济型'}
}

# 加载曲线映射
curve_mapping = load_json('data/curve_mapping.json')

def find_curve(model):
    """用 curve_mapping.json 匹配曲线"""
    # 先精确匹配
    if model in curve_mapping:
        return curve_mapping[model]
    # 模糊匹配（去掉 QG 后缀）
    base = model.upper().replace('QG', '')
    for k, v in curve_mapping.items():
        if k.upper().replace('QG', '') == base:
            return v
    return None

# 英文界面翻译
TRANSLATIONS = {
    'home_title': 'XIZI PUMPS Selection System',
    'home_subtitle': 'Professional sewage pump selection & configuration',
    'series': 'Series',
    'flow_label': 'Flow Rate (m³/h)',
    'head_label': 'Head (m)',
    'search_btn': 'Search',
    'model': 'Model',
    'flow': 'Flow',
    'head': 'Head',
    'power': 'Power',
    'voltage': 'Voltage',
    'select': 'Select',
    'detail': 'Detail',
    'back': '← Back',
    'price': 'FOB Price',
    'currency': 'USD',
    'config': 'Configuration',
    'impeller': 'Impeller Material',
    'impeller_std': 'Standard',
    'impeller_304': 'SS304',
    'impeller_ductile': 'Ductile Iron',
    'body': 'Pump Body',
    'body_std': 'Standard',
    'body_ductile': 'Ductile Iron',
    'bearing': 'Bearing',
    'bearing_std': 'Standard',
    'bearing_nsk': 'NSK',
    'bearing_skf': 'SKF',
    'mech': 'Mechanical Seal',
    'mech_std': 'Standard',
    'mech_bgm': 'Burgmann',
    'cable': 'Cable',
    'cable_9m': '9m Standard',
    'cable_star': 'Star-Delta',
    'coupling': 'Coupling',
    'sensors': 'Sensors',
    'vibration': 'Vibration Sensor',
    'pt100': 'PT100 Temp Sensor',
    'protector': 'Protector',
    'guide_rail': 'Guide Rail',
    'chain_hoist': 'Chain Hoist',
    'elbow': 'Elbow',
    'dflange': 'Double Flange',
    'discount': 'Discount Rate',
    'qty': 'Quantity',
    'subtotal': 'Subtotal',
    'total_fob': 'FOB Total',
    'pdf': 'Performance Curve',
    'no_data': 'No data available',
    'series_all': 'All Series',
    'series_all_en': 'All Series',
}

def calc_price(model, options):
    """详细报价计算"""
    price_info = PRICE_DATA.get('PRICE_DATA', PRICE_DATA).get(model, {})
    if not price_info:
        return None
    
    face = price_info.get('face', 0)
    discount = options.get('discount', 0.55)
    qty = options.get('qty', 1)
    is_60hz = options.get('freq', '50Hz') == '60Hz'
    is_voltage_adapt = options.get('voltage_adapt', False)
    
    # 基础价格
    base = face * discount
    
    # 选配件差价
    bearing_type = options.get('bearing', 'std')
    if bearing_type == 'nsk':
        base += price_info.get('bearing_nsk', 0) - price_info.get('bearing_std', 0)
    elif bearing_type == 'skf':
        base += price_info.get('bearing_skf', 0) - price_info.get('bearing_std', 0)
    
    mech_type = options.get('mech', 'std')
    if mech_type == 'bgm':
        base += price_info.get('mech_bgm', 0) - price_info.get('mech_std', 0)
    
    impeller_type = options.get('impeller', 'std')
    if impeller_type == '304':
        base += price_info.get('impeller_304', 0) - price_info.get('impeller_std', 0)
    elif impeller_type == 'ductile':
        base += price_info.get('impeller_ductile', 0) - price_info.get('impeller_std', 0)
    
    body_type = options.get('body', 'std')
    if body_type == 'ductile':
        base += price_info.get('body_ductile', 0) - price_info.get('body_std', 0)
    
    # 电缆
    cable_type = options.get('cable', '9m')
    if cable_type == 'star_delta':
        base += price_info.get('cable_star_delta', 0) - price_info.get('cable_9m', 0)
    
    # 联轴器
    if options.get('coupling'):
        coupling_price = options['coupling'].get('price', 0)
        base += coupling_price * discount
    
    # 传感器
    if options.get('vibration'):
        base += SENSOR_PRICES.get('vibration', 2200)
    if options.get('pt100'):
        base += SENSOR_PRICES.get('pt100', 350)
    if options.get('protector'):
        base += SENSOR_PRICES.get('protector', 350)
    
    # 导轨
    if options.get('guide_rail'):
        base += options['guide_rail'].get('price', 0)
    
    # 链条
    if options.get('chain'):
        base += options['chain'].get('price', 0)
    
    # 弯头
    if options.get('elbow'):
        base += options['elbow'].get('price', 0)
    
    # 双法兰
    if options.get('dflange'):
        base += options['dflange'].get('price', 0)
    
    subtotal = base * qty
    
    # 60Hz 加价
    if is_60hz:
        subtotal *= 1.1
    
    # 电压适配
    if is_voltage_adapt:
        subtotal *= 1.1
    
    # FOB 加价
    fob_cny = subtotal * 1.05
    fob_usd = round(fob_cny / EXCHANGE_RATE, 2)
    
    return {
        'face': face,
        'discount': discount,
        'base': round(base, 2),
        'subtotal': round(subtotal, 2),
        'fob_cny': round(fob_cny, 2),
        'fob_usd': fob_usd,
        'currency': 'USD'
    }

@app.route('/')
def index():
    export = EXPORT_MODE or request.args.get('mode') == 'export'
    series_list = []
    for key, info in SERIES_INFO.items():
        count = sum(1 for p in DATA if p.get('model', '').upper().startswith(key))
        if count > 0:
            series_list.append({
                'key': key,
                'name': info['en'] if export else info['zh'],
                'count': count
            })
    return render_template('index.html',
                         export=export,
                         series_list=series_list,
                         rate=EXCHANGE_RATE,
                         t=TRANSLATIONS)

@app.route('/api/products')
def api_products():
    export = EXPORT_MODE or request.args.get('mode') == 'export'
    series = request.args.get('series', '')
    q = request.args.get('q', '').strip()
    flow = request.args.get('flow', '').strip()
    head = request.args.get('head', '').strip()
    
    results = DATA
    if series:
        results = [p for p in results if p.get('series', '').upper() == series.upper() or p.get('model', '').upper().startswith(series.upper())]
    if q:
        q_lower = q.lower()
        results = [p for p in results if q_lower in p.get('model', '').lower()
                   or q_lower in str(p.get('flow', '')).lower()
                   or q_lower in str(p.get('head', '')).lower()]
    if flow:
        try:
            flow_val = float(flow)
            results = [p for p in results if abs(float(p.get('flow', 0) or 0) - flow_val) < 2]
        except:
            pass
    if head:
        try:
            head_val = float(head)
            results = [p for p in results if abs(float(p.get('head', 0) or 0) - head_val) < 10]
        except:
            pass
    
    # 排序
    def sort_key(p):
        m = p.get('model', '')
        flow = float(p.get('flow', 0) or 0)
        head = float(p.get('head', 0) or 0)
        return (m, flow, head)
    results.sort(key=sort_key)
    
    # 附加价格和曲线
    for p in results:
        model = p.get('model', '')
        price_info = PRICE_DATA.get('PRICE_DATA', PRICE_DATA).get(model, {})
        if price_info:
            p['has_price'] = True
        else:
            p['has_price'] = False
        
        # 查找曲线
        curve = find_curve(model)
        if curve:
            p['curve_file'] = curve
    
    return jsonify({
        'products': results,
        'total': len(results),
        'exchange_rate': EXCHANGE_RATE,
        'export': export
    })

@app.route('/api/product/<model>')
def api_product_detail(model):
    product = None
    for p in DATA:
        if p.get('model') == model:
            product = p
            break
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    price_info = PRICE_DATA.get('PRICE_DATA', PRICE_DATA).get(model, {})
    speed = SPEED_DATA.get(model, SPEED_DATA.get('SPEED_DATA', {}).get(model, 2950))
    weight = PUMP_WEIGHT.get(model, PUMP_WEIGHT.get('PUMP_WEIGHT', {}).get(model))
    curve = find_curve(model)
    
    return jsonify({
        'product': product,
        'price': price_info,
        'speed': speed,
        'weight': weight,
        'curve': curve,
        'coupling': COUPLING,
        'sensors': SENSOR_PRICES,
        'acc': ACC,
        'exchange_rate': EXCHANGE_RATE
    })

@app.route('/api/calc', methods=['POST'])
def api_calc():
    data = request.get_json()
    model = data.get('model', '')
    options = data.get('options', {})
    
    result = calc_price(model, options)
    if result is None:
        return jsonify({'error': 'Model not found or no price data'}), 404
    
    return jsonify(result)

@app.route('/curves/<path:filename>')
def serve_curve(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'data', 'curves'), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=True)
