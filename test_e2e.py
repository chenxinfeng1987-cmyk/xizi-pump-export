import app as flask_app
import json

client = flask_app.app.test_client()

# Test 1: Products API
r = client.get('/api/products?series=WQA&dn=80')
data = json.loads(r.data)
print('=== Test 1: Products ===')
print('Series WQA DN80:', data['total'], 'products')

# Test 2: Product detail
model = data['products'][0]['model']
r2 = client.get('/api/product/' + model)
d2 = json.loads(r2.data)
print('=== Test 2: Detail', model, '===')
print('Face price:', d2['price'].get('face'))
print('Curve:', d2.get('curve'))
print('Weight:', d2.get('weight'))

# Test 3: Basic calc
r3 = client.post('/api/calc', json={'model': model, 'options': {'discount': 0.55, 'qty': 1}})
d3 = json.loads(r3.data)
print('=== Test 3: Basic Calc ===')
print('FOB CNY:', d3['fob_cny'], '/ USD:', d3['fob_usd'])

# Test 4: Full options calc
r4 = client.post('/api/calc', json={'model': model, 'options': {
    'discount': 0.55, 'qty': 1, 'freq': '50',
    'bearing': 'nsk', 'mech': 'bgm', 'impeller': '304',
    'vibration': True, 'vib_qty': 2,
    'guide_rail': True, 'gr_mat': 'ss304', 'gr_len': 12,
    'chain': True, 'ch_type': 'hc', 'ch_grade': '4', 'ch_size': '8', 'ch_len': 12,
    'elbow': True, 'el_mat': 'SS304', 'el_qty': 2,
    'dflange': True, 'df_mat': 'SS316', 'df_qty': 1
}})
d4 = json.loads(r4.data)
print('=== Test 4: Full Options ===')
print('FOB CNY:', d4['fob_cny'], '/ USD:', d4['fob_usd'])

# Test 5: Chain sizes
r5 = client.get('/api/chain_sizes?type=hc&grade=4')
d5 = json.loads(r5.data)
print('=== Test 5: Chain Sizes HC4 ===')
print(len(d5['sizes']), 'sizes:', [s['size'] for s in d5['sizes']])

r6 = client.get('/api/chain_sizes?type=ss')
d6 = json.loads(r6.data)
print('SS304:', len(d6['sizes']), 'sizes:', [s['size'] for s in d6['sizes']])

print()
print('ALL TESTS PASSED')
