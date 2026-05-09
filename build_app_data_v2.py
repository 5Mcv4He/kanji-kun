#!/usr/bin/env python3
"""
Build kanji_app_data.json v2 — fixed TR, CP, SF, ON_RULES.

Key fixes:
- SF: Use network shared_stem edges (NOT the noisy reverse_index stem_index)
- TR: Build from known patterns + V9 reading index
- CP: Extract from kanji_learn word compounds
- ON_RULES: Directly use kanji_learn rule kanji_matches (tier 1-2)
"""

import json, os, re
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))

# ── Load network ──
with open(os.path.join(BASE, 'output/kun_network_data.json')) as f:
    net = json.load(f)

# Build adjacency from network edges
adj = defaultdict(lambda: defaultdict(set))
for e in net['edges']:
    s, t, tp = e['source'], e['target'], e['type']
    adj[s][tp].add(t)
    adj[t][tp].add(s)

# Index shared_stem edges by source/target with stem info
ss_by_kanji = defaultdict(lambda: defaultdict(set))
for e in net['edges']:
    if e['type'] == 'shared_stem':
        stem = e.get('stem', '')
        ss_by_kanji[e['source']][stem].add(e['target'])
        ss_by_kanji[e['target']][stem].add(e['source'])

# ── Load V9 reverse index (for TR patterns) ──
with open(os.path.join(BASE, 'output/kun_v8_reverse_index.json')) as f:
    rev = json.load(f)
reading_index = rev.get('reading_index', {})

# ── Load kanji_learn data ──
kl_data = {}
for lv in ['n5', 'n4', 'n3', 'n2', 'n1']:
    path = os.path.join(BASE, f'../kanji_learn/web/data/{lv}.json')
    if not os.path.exists(path):
        continue
    with open(path) as f:
        d = json.load(f)
    for ik, kd in d.get('kanji', {}).items():
        if ik not in kl_data:
            kl_data[ik] = {
                'levels': set(), 'words': [], 'onyomi': [], 'kunyomi': [],
                'pinyin': '', 'radical': '',
            }
        kl_data[ik]['levels'].add(lv.upper())
        kl_data[ik]['words'].extend(kd.get('words', []))
        for o in kd.get('onyomi', []):
            if o and o not in kl_data[ik]['onyomi']:
                kl_data[ik]['onyomi'].append(o)
        for ku in kd.get('kunyomi', []):
            if ku and ku not in kl_data[ik]['kunyomi']:
                kl_data[ik]['kunyomi'].append(ku)
        kl_data[ik]['pinyin'] = kd.get('pinyin', '')
        kl_data[ik]['radical'] = kd.get('radical', '')

# Also collect all rules
all_rules = []
for lv in ['n5', 'n4', 'n3', 'n2', 'n1']:
    path = os.path.join(BASE, f'../kanji_learn/web/data/{lv}.json')
    if not os.path.exists(path):
        continue
    with open(path) as f:
        d = json.load(f)
    all_rules.extend(d.get('rules', []))

print(f"Loaded: {len(net['nodes'])} network nodes, {len(kl_data)} kanji_learn entries, {len(all_rules)} rules")

# ── Build node lookup ──
nodes = {n['id']: n for n in net['nodes']}

# ── Sort key: by JLPT level (N5→N1), then hub score, then code point ──
LV_ORDER = {'N5': 0, 'N4': 1, 'N3': 2, 'N2': 3, 'N1': 4}
def _min_level(ik):
    if ik in kl_data and kl_data[ik]['levels']:
        return min(LV_ORDER.get(l, 99) for l in kl_data[ik]['levels'])
    n = nodes.get(ik, {})
    lvs = n.get('levels', [])
    if lvs:
        return min(LV_ORDER.get(l, 99) for l in lvs)
    return 99

def _hub(ik):
    n = nodes.get(ik, {})
    if n:
        return sum(len(adj[ik].get(tp, set())) for tp in adj[ik])
    return 0

def sort_kanji(iks):
    return sorted(iks, key=lambda ik: (_min_level(ik), -_hub(ik), ik))

def get_kun(ik):
    if ik in kl_data and kl_data[ik]['kunyomi']:
        primary = kl_data[ik]['kunyomi'][0]  # kanji_learn has correct primary first
        # Cross-reference with network to get stem form
        n = nodes.get(ik, {})
        for nk in n.get('kun_readings', []):
            if primary.startswith(nk) or nk.startswith(primary):
                return nk  # network stem form
        # Fallback: strip trailing kana
        stem = re.sub(r'[ぁ-ん]+$', '', primary)
        return stem or primary
    n = nodes.get(ik, {})
    kuns = n.get('kun_readings', [])
    return kuns[0] if kuns else ''

def get_on(ik):
    if ik in kl_data and kl_data[ik]['onyomi']:
        return kl_data[ik]['onyomi'][0]  # primary from kanji_learn
    n = nodes.get(ik, {})
    ons = n.get('on_readings', [])
    return ons[0] if ons else ''

# ═══════════════════════════════════════════════
# SF: from network shared_stem edges
# ═══════════════════════════════════════════════
sf_data = {}
for ik in nodes:
    stem_map = ss_by_kanji.get(ik, {})
    families = []
    for stem, others in stem_map.items():
        if stem and len(others) >= 1:
            families.append({'st': stem, 'ks': sort_kanji(others), 'ex': []})
    # Sort families by member count descending
    families.sort(key=lambda f: -len(f['ks']))
    sf_data[ik] = families

# ═══════════════════════════════════════════════
# TR: from 10 known patterns via reading_index
# ═══════════════════════════════════════════════
TR_PATTERNS = [
    ('まる', 'める', '〜まる↔〜める'),
    ('がる', 'げる', '〜がる↔〜げる'),
    ('く',   'ける', '〜く↔〜ける'),
    ('る',   'す',   '〜る↔〜す'),
    ('れる', 'る',   '〜れる↔〜る'),
    ('かる', 'ける', '〜かる↔〜ける'),
    ('う',   'える', '〜う↔〜える'),
    ('つ',   'てる', '〜つ↔〜てる'),
    ('ぶ',   'べる', '〜ぶ↔〜べる'),
    ('む',   'める', '〜む↔〜める'),
]

tr_data = defaultdict(list)
for a_end, t_end, pattern in TR_PATTERNS:
    # Find all readings ending with a_end (auto form)
    for reading, kanji_dict in reading_index.items():
        if not reading.endswith(a_end):
            continue
        stem = reading[:-len(a_end)]
        if not stem:
            continue
        t_form = stem + t_end
        if t_form not in reading_index:
            continue

        a_kanji = set(kanji_dict.keys()) if isinstance(kanji_dict, dict) else set(kanji_dict)
        t_dict = reading_index[t_form]
        t_kanji = set(t_dict.keys()) if isinstance(t_dict, dict) else set(t_dict)
        common = a_kanji & t_kanji

        for ik in common:
            if ik in nodes:
                a_examples = kanji_dict.get(ik, {}) if isinstance(kanji_dict, dict) else {}
                t_examples = t_dict.get(ik, {}) if isinstance(t_dict, dict) else {}
                tr_data[ik].append({
                    'p': pattern,
                    'a': [{'w': ik + a_end, 'k': reading}],
                    't': [{'w': ik + t_end, 'k': t_form}],
                })

# Supplement from network transitivity_pair edges
for e in net['edges']:
    if e['type'] == 'transitivity_pair':
        s, t = e['source'], e['target']
        if s in nodes and not tr_data.get(s):
            tr_data[s].append({
                'p': '自他对应',
                'a': [{'w': s, 'k': get_kun(s)}],
                't': [{'w': t, 'k': get_kun(t)}],
            })

tr_data = dict(tr_data)

# ═══════════════════════════════════════════════
# CP: from kanji_learn word compounds
# ═══════════════════════════════════════════════
cp_data = defaultdict(set)
for ik, kd in kl_data.items():
    if ik not in nodes:
        continue
    seen = set()
    for w in kd['words']:
        wt = w.get('word', '')
        for c in wt:
            if c != ik and c in nodes:
                seen.add(c)
    cp_data[ik] = sort_kanji(seen)

# ═══════════════════════════════════════════════
# SC, RB: from network edges
# ═══════════════════════════════════════════════
sc_data = {ik: sort_kanji(adj[ik].get('same_component', set())) for ik in nodes}
rb_data = {ik: sort_kanji(adj[ik].get('same_radical', set())) for ik in nodes}

# ═══════════════════════════════════════════════
# SO: from kanji_learn onyomi
# ═══════════════════════════════════════════════
on_index = defaultdict(set)
for ik, kd in kl_data.items():
    for o in kd['onyomi']:
        if o: on_index[o].add(ik)

so_data = defaultdict(list)
for ik in nodes:
    if ik in kl_data:
        for o in kl_data[ik]['onyomi']:
            if o and len(on_index.get(o, set())) >= 2:
                others = sort_kanji((on_index[o] - {ik}) & set(nodes))
                if others:
                    so_data[ik].append({'r': o, 'ks': others})
so_data = dict(so_data)

# ═══════════════════════════════════════════════
# ON_RULES: from kanji_learn rule kanji_matches (tier 1-2, 确定)
# ═══════════════════════════════════════════════
on_rules_data = defaultdict(list)
seen_rules = defaultdict(set)  # ik → {rule_key} for dedup

for rule in all_rules:
    tier = rule.get('tier', 99)
    conf = rule.get('confidence', '')
    if tier > 2: continue
    if conf not in ('确定', '大概率'): continue

    rtext = rule.get('rule_text', '')
    onyomi = rule.get('onyomi', '')
    source = rule.get('source', '')
    acc = rule.get('accuracy', 0.5)

    for ik in rule.get('kanji_matches', []):
        if ik not in nodes:
            continue
        key = rtext + onyomi
        if key in seen_rules[ik]:
            continue
        seen_rules[ik].add(key)
        on_rules_data[ik].append({
            't': rtext,
            'o': onyomi,
            'c': '确定' if conf == '确定' else '可能',
            'a': acc,
            's': source,
            'r': tier,
        })

on_rules_data = dict(on_rules_data)

# ═══════════════════════════════════════════════
# Assemble
# ═══════════════════════════════════════════════
app_kanji = {}
for ik in nodes:
    n = nodes[ik]
    kl = kl_data.get(ik, {})

    primary_ku = get_kun(ik)
    # Collect all kun readings from sf stems
    all_kun_from_sf = set()
    for f in sf_data.get(ik, []):
        all_kun_from_sf.add(f['st'])
    if primary_ku:
        all_kun_from_sf.add(primary_ku)

    on_all = sorted(kl.get('onyomi', set()))

    levels = sorted(kl.get('levels', set()) or set(n.get('levels', [])))

    hub = sum(len(adj[ik].get(tp, set())) for tp in adj[ik])

    words = []
    seen_w = set()
    for w in kl.get('words', []):
        key = w.get('word', '')
        if key not in seen_w:
            seen_w.add(key)
            words.append({
                'w': key,
                'k': w.get('kana', ''),
                't': w.get('reading_type', ''),
                'l': '',
            })
    words = words[:8]

    app_kanji[ik] = {
        'ku': primary_ku,
        'on': get_on(ik),
        'lv': min(levels, key=lambda l: LV_ORDER.get(l, 99)) if levels else '',
        'lv_all': levels,
        'rd': n.get('radical', ''),
        'hub': hub,
        'ws': words,
        'py': kl.get('pinyin', ''),
        'on_all': on_all,
        'sf': sf_data.get(ik, []),
        'sc': sc_data.get(ik, []),
        'so': so_data.get(ik, []),
        'cp': cp_data.get(ik, []),
        'rb': rb_data.get(ik, []),
        'rb_rd': n.get('radical', ''),
        'tr': tr_data.get(ik, []),
        'on_rules': on_rules_data.get(ik, []),
    }

# Hub list for random
hubs = sorted(app_kanji.keys(), key=lambda ik: app_kanji[ik]['hub'], reverse=True)

output = {
    'total': len(app_kanji),
    'hubs': hubs,
    'lookup': {},
    'kanji': app_kanji,
}

# ── Stats ──
def count(field, condition=None):
    if condition is None:
        return sum(1 for d in app_kanji.values() if d[field])
    return sum(1 for d in app_kanji.values() if condition(d[field]))

N = len(app_kanji)
print(f"\n{'='*60}")
print(f"Total kanji: {N}")
print(f"  同读法(sf):     {count('sf'):>5} ({count('sf')/N*100:.1f}%)  max={max((len(d['sf']) for d in app_kanji.values()), default=0)}")
print(f"  自他对应(tr):   {count('tr'):>5} ({count('tr')/N*100:.1f}%)  max={max((len(d['tr']) for d in app_kanji.values()), default=0)}")
print(f"  复合词共现(cp): {count('cp'):>5} ({count('cp')/N*100:.1f}%)  max={max((len(d['cp']) for d in app_kanji.values()), default=0)}")
print(f"  同部首(rb):     {count('rb'):>5} ({count('rb')/N*100:.1f}%)  max={max((len(d['rb']) for d in app_kanji.values()), default=0)}")
print(f"  同部件(sc):     {count('sc'):>5} ({count('sc')/N*100:.1f}%)  max={max((len(d['sc']) for d in app_kanji.values()), default=0)}")
print(f"  同音读(so):     {count('so'):>5} ({count('so')/N*100:.1f}%)  max={max((sum(len(g['ks']) for g in d['so']) for d in app_kanji.values()), default=0)}")
print(f"  音读推导(on_r): {count('on_rules'):>5} ({count('on_rules')/N*100:.1f}%)  max={max((len(d['on_rules']) for d in app_kanji.values()), default=0)}")

# ── Verify ──
for ik in ['退', '高', '生', '變', '変', '会', '進', '健']:
    d = app_kanji.get(ik, {})
    if not d:
        print(f"\n  {ik}: NOT IN DATA")
        continue
    sf = d.get('sf', [])
    sf_summary = [(f['st'], len(f['ks'])) for f in sf[:6]]
    print(f"\n  {ik}: ku='{d.get('ku','')}' on='{d.get('on','')}' on_all={d.get('on_all')}")
    print(f"    sf=[{', '.join(f'{s}({n})' for s,n in sf_summary)}{'...' if len(sf) > 6 else ''}]")
    print(f"    tr={len(d.get('tr',[]))} cp={len(d.get('cp',[]))} rb={len(d.get('rb',[]))} sc={len(d.get('sc',[]))}")
    print(f"    so={[(g['r'], len(g['ks'])) for g in d.get('so',[])]}")
    print(f"    on_rules={len(d.get('on_rules',[]))}")

# ── Write ──
out_path = os.path.join(BASE, 'output/kanji_app_data.json')
with open(out_path, 'w') as f:
    json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

size_kb = os.path.getsize(out_path) / 1024
print(f"\nWritten: {out_path} ({size_kb:.0f} KB)")
