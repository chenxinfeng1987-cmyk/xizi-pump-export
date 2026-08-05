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
    'WQA-QG': {'en': 'WQA-QG High Head', 'zh': 'WQA-QG高扬程'},
    'WQ': {'en': 'WQ Sewage Pump', 'zh': 'WQ潜水排污泵'},
    'WQN': {'en': 'WQN Internal Cooling', 'zh': 'WQN内循环冷却'},
    'WQF': {'en': 'WQF Sewage Pump', 'zh': 'WQF潜水排污泵'},
    'WQB': {'en': 'WQB Explosion-proof', 'zh': 'WQB防爆型'},
    'WQAF': {'en': 'WQAF Stainless Steel', 'zh': 'WQAF不锈钢'},
    'WQE': {'en': 'WQE Economy', 'zh': 'WQE经济型'}
}

# 加载曲线映射
curve_mapping = load_json('data/curve_mapping.json')
curve_data = load_json('data/curve_data.json')

# 加载尺寸图映射
dim_mapping = load_json('data/dim_mapping.json')

SERIES_CURVE_MAP = {
    'WQN': 'WQA',
    'WQB': 'WQA',
    'WQAF': 'WQA',
    'WQE': 'WQE',
    'WQF': 'WQF',
}

# 预计算BEP（最高效率点）：从curve_data中提取η峰值对应的Q和H
BEP_DATA = {}
for _model, _cd in curve_data.items():
    _q = _cd.get('q', [])
    _eff = _cd.get('eff')
    _h = _cd.get('h')
    if _q and _eff and _h and len(_q) == len(_eff) == len(_h):
        _peak_i = _eff.index(max(_eff))
        # 去掉中文后缀匹配产品型号
        _clean = re.sub(r'[\u4e00-\u9fff]+$', '', _model).strip()
        _clean = re.sub(r'-\d+P-?$', '', _clean).strip()
        BEP_DATA[_clean.upper().replace('QG', '')] = {
            'bep_q': round(_q[_peak_i], 1),
            'bep_h': round(_h[_peak_i], 1),
            'bep_eff': round(_eff[_peak_i], 1),
        }

def find_curve(model):
    """用 curve_mapping.json 匹配曲线，WQN/WQB/WQAF 共用 WQA 曲线"""
    # 先精确匹配
    if model in curve_mapping:
        return curve_mapping[model]
    # 去掉 QG 后缀匹配
    base = model.upper().replace('QG', '')
    for k, v in curve_mapping.items():
        if k.upper().replace('QG', '') == base:
            return v
    # 系列映射（WQN→WQA 等）
    for src, dst in SERIES_CURVE_MAP.items():
        mapped = model.upper().replace(src, dst).replace('QG', '')
        for k, v in curve_mapping.items():
            if k.upper().replace('QG', '') == mapped:
                return v
    return None

def _strip_curve_key(k):
    """去掉key中的中文后缀（如'性能曲线图'）和-数字P后缀"""
    import re
    k = re.sub(r'[\u4e00-\u9fff]+$', '', k).strip()
    k = re.sub(r'-\d+P-?$', '', k).strip()
    return k

def find_curve_data(model):
    """模糊匹配curve_data，产品型号可能不带-4P/-2P后缀"""
    if model in curve_data:
        return curve_data[model]
    import re
    base = re.sub(r'-\d+P-?$', '', model)
    no_qg = base.upper().replace('QG', '')
    for k, v in curve_data.items():
        clean_k = _strip_curve_key(k)
        if clean_k == base:
            return v
    for k, v in curve_data.items():
        clean_k = _strip_curve_key(k).upper().replace('QG', '')
        if clean_k == no_qg:
            return v
    for src, dst in SERIES_CURVE_MAP.items():
        mapped = base.upper().replace(src, dst).replace('QG', '')
        for k, v in curve_data.items():
            if _strip_curve_key(k).upper().replace('QG', '') == mapped:
                return v
    return None

def find_dimension(model):
    """用 dim_mapping.json 匹配尺寸图，WQN/WQB/WQAF 共用 WQA 尺寸图"""
    clean = model.strip()
    if clean in dim_mapping:
        return dim_mapping[clean]
    no_qg = clean.upper().replace('QG', '')
    for k in dim_mapping:
        if k.upper().replace('QG', '') == no_qg:
            return dim_mapping[k]
    mapped_name = clean.upper()
    for src, dst in SERIES_CURVE_MAP.items():
        mapped_name = mapped_name.replace(src, dst)
    mapped_name = mapped_name.replace('QG', '')
    for k in dim_mapping:
        if k.upper().replace('QG', '') == mapped_name:
            return dim_mapping[k]
    core_match = re.match(r'(\d+W[A-Z]+\d+-\d+-\d+)', mapped_name)
    if core_match:
        core = core_match.group(1)
        for k in dim_mapping:
            k_core = re.match(r'(\d+W[A-Z]+\d+-\d+-\d+)', k.upper().replace('QG', ''))
            if k_core and k_core.group(1) == core:
                return dim_mapping[k]
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

def calc_guide_rail_price(mat, length):
    """导轨价格计算（按长度计价）"""
    sizes = ACC.get('guide_rail', {}).get('sizes', [])
    if not sizes:
        return 0
    mat_key = {'galv': 'galv', 'ss304': 'ss304', 'ss316': 'ss316'}.get(mat, 'galv')
    first = sizes[0].get(mat_key, 0) if sizes else 0
    return first * length

def calc_chain_price(ch_type, grade, size, length):
    """链条价格计算（按长度计价）"""
    if ch_type == 'ss':
        chains = ACC.get('ss304_chain', [])
        for c in chains:
            if str(c.get('size','')) == str(size):
                return c.get('p304', 0) * length
        return 0
    # hc4 or hc8
    key = f'hc{grade}'
    data = ACC.get(key, [])
    for c in data:
        if str(c.get('size','')) == str(size):
            return c.get('price', 0) * length
    return 0

def calc_elbow_price(material, dn, qty):
    """弯头价格计算"""
    el = ACC.get('elbow', {}).get(material, {})
    return el.get(str(dn), 0) * qty

def calc_dflange_price(material, dn, qty):
    """双法兰弯头价格"""
    df = ACC.get('dflange', {}).get(material, {})
    return df.get(str(dn), 0) * qty

def nearest_dn_for_acc(dn):
    """取最近的<=DN"""
    valid = [100, 150, 200, 250, 300, 350, 400, 500, 600]
    best = valid[0]
    for v in valid:
        if v <= dn:
            best = v
    return best

def extract_dn(model):
    """从型号提取口径 DN"""
    m = re.match(r'(\d+)', model)
    if m:
        return int(m.group(1))
    return 100

def calc_price(model, options):
    """详细报价计算"""
    price_info = PRICE_DATA.get('PRICE_DATA', PRICE_DATA).get(model, {})
    if not price_info:
        return None

    dn = extract_dn(model)
    face = price_info.get('face', 0)
    discount = options.get('discount', 0.55)
    qty = options.get('qty', 1)
    freq = options.get('freq', '50')
    volt = options.get('volt', '380')
    
    # 基础价格（面价 × 折扣）
    base = face * discount
    
    # === 选配件差价 ===
    # 轴承
    bearing_type = options.get('bearing', 'std')
    if bearing_type == 'nsk':
        base += price_info.get('bearing_nsk', 0) - price_info.get('bearing_std', 0)
    elif bearing_type == 'skf':
        base += price_info.get('bearing_skf', 0) - price_info.get('bearing_std', 0)
    
    # 机封
    mech_type = options.get('mech', 'std')
    if mech_type == 'bgm':
        bgm_price = price_info.get('mech_bgm', 0)
        if bgm_price == 0:
            bgm_price = int(price_info.get('mech_std', 0) * 2.3) if price_info.get('mech_std', 0) > 0 else 0
        base += bgm_price - price_info.get('mech_std', 0)
    
    # 叶轮
    impeller_type = options.get('impeller', 'std')
    if impeller_type == '304':
        base += price_info.get('impeller_304', 0) - price_info.get('impeller_std', 0)
    elif impeller_type == 'ductile':
        base += price_info.get('impeller_ductile', 0) - price_info.get('impeller_std', 0)
    
    # 泵体
    body_type = options.get('body', 'std')
    if body_type == 'ductile':
        base += price_info.get('body_ductile', 0) - price_info.get('body_std', 0)
    
    # 电缆（标配9m差价=0）
    cable_type = options.get('cable_type', 'regular')
    if cable_type == 'star_delta':
        base += price_info.get('cable_star_delta', 0) - price_info.get('cable_9m', 0)
    # 额外电缆长度差价（标配9m之外）
    cable_m = float(options.get('cable_m', 9))
    if cable_m > 9:
        # 电缆差价 = (额外米数 × 单价差)，从 ACC 或固定值
        cable_extra = (cable_m - 9) * 5  # 约 ¥5/米差价
        base += cable_extra
    
    # 联轴器（按口径选价格）
    coupling_type = options.get('coupling', 'none')
    if coupling_type != 'none':
        coupling_key = 'coupling_heavy' if coupling_type == 'heavy_ht200' else ('coupling_light' if coupling_type == 'light_ht200' else 'coupling_304')
        c_price = price_info.get(coupling_key, 0)
        if not c_price:
            # 从 COUPLING 表取
            c_data = COUPLING.get(coupling_key, {})
            for k in sorted(c_data.keys(), key=lambda x: float(x)):
                if float(k) <= dn:
                    c_price = c_data[k]
        base += c_price * discount
    
    # === 传感器/保护器（按数量计价）===
    if options.get('vibration'):
        base += SENSOR_PRICES.get('vibration', 2200) * int(options.get('vib_qty', 1))
    if options.get('pt100'):
        base += SENSOR_PRICES.get('pt100', 350) * int(options.get('pt100_qty', 1))
    if options.get('protector'):
        base += SENSOR_PRICES.get('protector', 350) * int(options.get('prot_qty', 1))
    
    # === 备件 ===
    if options.get('spare'):
        base += price_info.get('bearing_std', 0)  # 轴承备件
        base += price_info.get('mech_std', 0)      # 机封备件
    
    # === 导轨（按长度计价）===
    if options.get('guide_rail'):
        gr_mat = options.get('gr_mat', 'galv')
        gr_len = int(options.get('gr_len', 6))
        base += calc_guide_rail_price(gr_mat, gr_len)
    
    # === 链条（按长度计价）===
    if options.get('chain'):
        ch_type = options.get('ch_type', 'hc')
        ch_grade = options.get('ch_grade', '4')
        ch_size = options.get('ch_size', '')
        ch_len = int(options.get('ch_len', 6))
        if ch_type == 'ss':
            base += calc_chain_price('ss', 0, ch_size, ch_len)
        else:
            base += calc_chain_price(ch_type, ch_grade, ch_size, ch_len)
    
    # === 弯头（按口径×数量计价）===
    if options.get('elbow'):
        el_dn = nearest_dn_for_acc(dn)
        base += calc_elbow_price(options.get('el_mat', 'HT200'), el_dn, int(options.get('el_qty', 1)))
    
    # === 双法兰（按口径×数量计价）===
    if options.get('dflange'):
        df_dn = nearest_dn_for_acc(dn)
        base += calc_dflange_price(options.get('df_mat', 'SS304'), df_dn, int(options.get('df_qty', 1)))
    
    subtotal = base * qty
    
    # 60Hz 加价
    if freq == '60':
        subtotal *= 1.1
    
    # 电压定制加价
    if volt == 'customize':
        subtotal *= 1.1
    
    # FOB 加价 5%
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
        if key == 'WQA-QG':
            count = sum(1 for p in DATA if p.get('series', '').upper() == 'WQA' and p.get('model', '').upper().endswith('QG'))
        elif key == 'WQA':
            count = sum(1 for p in DATA if p.get('series', '').upper() == 'WQA' and not p.get('model', '').upper().endswith('QG'))
        else:
            count = sum(1 for p in DATA if p.get('series', '').upper() == key.upper())
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
    dn = request.args.get('dn', '').strip()
    q = request.args.get('q', '').strip()
    flow = request.args.get('flow', '').strip()
    head = request.args.get('head', '').strip()
    
    results = DATA
    if series:
        if series.upper() == 'WQA-QG':
            results = [p for p in results if p.get('series', '').upper() == 'WQA' and p.get('model', '').upper().endswith('QG')]
        elif series.upper() == 'WQA':
            results = [p for p in results if p.get('series', '').upper() == 'WQA' and not p.get('model', '').upper().endswith('QG')]
        else:
            results = [p for p in results if p.get('series', '').upper() == series.upper() or p.get('model', '').upper().startswith(series.upper())]
    if dn:
        dn_val = dn.strip()
        results = [p for p in results if str(p.get('dia', '') or '').strip() == dn_val]
    if q:
        q_lower = q.lower()
        results = [p for p in results if q_lower in p.get('model', '').lower()
                   or q_lower in str(p.get('flow', '')).lower()
                   or q_lower in str(p.get('head', '')).lower()]
    
    use_bep = False
    flow_val = None
    head_val = None
    if flow:
        try:
            flow_val = float(flow)
        except:
            pass
    if head:
        try:
            head_val = float(head)
        except:
            pass
    
    if flow_val is not None or head_val is not None:
        use_bep = True
        # 用BEP匹配：为每个产品附加BEP信息和匹配分数
        for p in results:
            model = p.get('model', '')
            clean = model.upper().replace('QG', '')
            bep = BEP_DATA.get(clean, {})
            p['_bep_q'] = bep.get('bep_q', 0)
            p['_bep_h'] = bep.get('bep_h', 0)
            p['_bep_eff'] = bep.get('bep_eff', 0)
            
            # 计算匹配分数（越小越好）
            score = 0
            rated_flow = float(p.get('flow', 0) or 1)
            rated_head = float(p.get('head', 0) or 1)
            if flow_val is not None and p['_bep_q'] > 0:
                diff_q = abs(p['_bep_q'] - flow_val) / max(rated_flow, 1)
                score += diff_q
            if head_val is not None and p['_bep_h'] > 0:
                diff_h = abs(p['_bep_h'] - head_val) / max(rated_head, 1)
                score += diff_h
            p['_match_score'] = score
        
        # 过滤：BEP在合理范围内的才保留（±60%额定值）
        def in_range(p):
            rated_flow = float(p.get('flow', 0) or 1)
            rated_head = float(p.get('head', 0) or 1)
            ok = True
            if flow_val is not None and p['_bep_q'] > 0:
                ok = ok and abs(p['_bep_q'] - flow_val) < rated_flow * 0.6 + 3
            if head_val is not None and p['_bep_h'] > 0:
                ok = ok and abs(p['_bep_h'] - head_val) < rated_head * 0.6 + 3
            return ok
        results = [p for p in results if in_range(p)]
    else:
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
    if use_bep:
        results.sort(key=lambda p: (p.get('_match_score', 999), p.get('model', '')))
    else:
        def sort_key(p):
            m = p.get('model', '')
            f = float(p.get('flow', 0) or 0)
            h = float(p.get('head', 0) or 0)
            return (m, f, h)
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
        
        # 附加BEP信息
        if use_bep:
            p['bep_q'] = p.pop('_bep_q', 0)
            p['bep_h'] = p.pop('_bep_h', 0)
            p['bep_eff'] = p.pop('_bep_eff', 0)
            p['match_score'] = round(p.pop('_match_score', 999), 3)
        else:
            p.pop('_bep_q', None)
            p.pop('_bep_h', None)
            p.pop('_bep_eff', None)
            p.pop('_match_score', None)
    
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
    curve_data_result = find_curve_data(model)
    dimension = find_dimension(model)
    
    return jsonify({
        'product': product,
        'price': price_info,
        'speed': speed,
        'weight': weight,
        'curve': curve,
        'curve_data': curve_data_result,
        'dimension': dimension,
        'coupling': COUPLING,
        'sensors': SENSOR_PRICES,
        'acc': ACC,
        'exchange_rate': EXCHANGE_RATE
    })

@app.route('/api/chain_sizes')
def api_chain_sizes():
    """返回链条尺寸选项"""
    ch_type = request.args.get('type', 'hc')
    grade = request.args.get('grade', '4')
    if ch_type == 'ss':
        chains = ACC.get('ss304_chain', [])
        sizes = [{'size': c.get('size'), 'load': c.get('load', 0)} for c in chains]
        return jsonify({'sizes': sizes})
    else:
        key = f'hc{grade}'
        data = ACC.get(key, [])
        sizes = [{'size': c.get('size'), 'load': c.get('load', 0)} for c in data]
        return jsonify({'sizes': sizes})

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

@app.route('/dimensions/<path:filename>')
def serve_dimension(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'dimensions'), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=True)
