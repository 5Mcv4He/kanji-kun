#!/usr/bin/env python3
"""
kun_network_v1.py — Kun-Yomi Association Network
Unfold the full web of connections between JLPT kanji as a LEARNER'S COGNITIVE MAP.
Produces: JSON data + comprehensive Markdown cognitive map.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from gold_panning_v3 import load_kanji_db

# ─── Configuration ───────────────────────────────────────────────────────────

V9_PATH = f'{BASE}/output/kun_v9_data.json'
REVERSE_PATH = f'{BASE}/output/kun_v8_reverse_index.json'
KANJI_DB_PATH = f'{BASE}/漢字検索V2.xlsm'
OUT_JSON = f'{BASE}/output/kun_network_data.json'
OUT_MAP_MD = f'{BASE}/output/kun_network_map.md'

LEVEL_ORDER = {'N5': 5, 'N4': 4, 'N3': 3, 'N2': 2, 'N1': 1}

EDGE_META = {
    'shared_stem':        ('共享词干', '这些汉字共享完全相同的训读词干。看到其中一个，就能猜出另一个的读法。'),
    'same_component':     ('共享部件', '这些汉字包含相同的非部首部件。共享部件的汉字有时也共享训读词干（声符类推）。'),
    'same_radical':       ('共享部首', '同一部首下的汉字。部首暗示语义域，进而暗示训读/音读倾向。'),
    'same_semantic':      ('共享语义域', '这些汉字属于同一语义领域（如身体、自然、动作）。同域汉字有相似的读法模式。'),
    'shared_okurigana':   ('共享送假名', '这些汉字在JLPT词汇中搭配相同的送假名。相同送假名→相同词类→相同活用。'),
    'compound_neighbor':  ('复合词邻居', '这些汉字在JLPT词汇中频繁共同出现在复合词中。共现关系帮助记忆词汇整体。'),
    'transitivity_pair':  ('清浊自他对应', '一个清音词干对应一个浊音词干，形成自他动词对。知道一个就能推另一个。'),
    'rendaku_variant':    ('连浊变体', '同一汉字在不同词汇中因连浊而呈现清浊交替。不是不同读法，是同一词干的变体。'),
    'same_on_reading':    ('共享音读', '这些汉字共享同一个音读。对训读学习来说，共享音读=共享"音读排除信号"。'),
    'co_occurring_stem':  ('词干家族共现', '这些汉字同时属于多个词干家族。它们是词干网络中的交汇点。'),
    'near_synonym':       ('近义训读邻居', '语义域相同且都以训读为主的汉字。意义相近、读法模式也相近。'),
    'radical_wclass':     ('部首词类倾向', '同一部首的汉字有强烈的词类一致性（>70%同为名词或同为动词）。'),
    'semantic_stem':      ('语义词干模式', '词干尾音相同+送假名模式相同的汉字。形态-语义双重关联。'),
    'multi_kun_hub':      ('多训字枢纽', '拥有≥3个训读的"怪物汉字"。它们是网络中连接最多的节点。'),
}


# ─── Phase 1: Node Extraction ────────────────────────────────────────────────

def load_v9_data():
    with open(V9_PATH) as f:
        return json.load(f)


def build_nodes(v9_data, kanji_db):
    """Extract all unique JLPT kanji with metadata from V9 + kanji_db."""
    db_index = {k['kanji']: k for k in kanji_db}

    kanji_stats = defaultdict(lambda: {
        'kun_count': 0, 'on_count': 0, 'levels': set(),
        'kun_readings': set(), 'on_readings': set(),
        'words': [], 'okurigana_set': set(), 'domains': set(),
        'positions': defaultdict(int), 'word_details': [],
    })

    for word in v9_data['annotated_words']:
        level = word['level']
        for detail in word.get('gt_details', []):
            ch = detail['kanji']
            stats = kanji_stats[ch]
            stats['words'].append(word['word'])
            if detail['type'] == 'kun':
                stats['kun_count'] += 1
                stats['kun_readings'].add(detail['reading'])
            else:
                stats['on_count'] += 1
                stats['on_readings'].add(detail['reading'])
            stats['levels'].add(level)
            # Track usage examples
            if len(stats['word_details']) < 5:
                stats['word_details'].append({
                    'word': word['word'], 'kana': word['kana'],
                    'type': detail['type'], 'reading': detail['reading'],
                    'level': level,
                })
            # Position tracking
            word_kanji = word['word']
            if len(word_kanji) > 1:
                if word_kanji.index(ch) == 0:
                    stats['positions']['start'] += 1
                elif word_kanji.index(ch) == len(word_kanji) - 1:
                    stats['positions']['end'] += 1
                else:
                    stats['positions']['middle'] += 1
            else:
                stats['positions']['alone'] += 1
            # Okurigana extraction
            reading = detail['reading']
            if reading:
                full_kana = word['kana']
                # Find reading position in kana
                idx = full_kana.find(reading)
                if idx >= 0:
                    rest = full_kana[idx + len(reading):]
                    if rest:
                        stats['okurigana_set'].add(rest)

    nodes = []
    for ch, stats in kanji_stats.items():
        db_entry = db_index.get(ch, {})
        total = stats['kun_count'] + stats['on_count']
        nodes.append({
            'id': ch,
            'kun_count': stats['kun_count'],
            'on_count': stats['on_count'],
            'total': total,
            'kun_ratio': stats['kun_count'] / total if total > 0 else 0,
            'kun_readings': sorted(stats['kun_readings']),
            'on_readings': sorted(stats['on_readings']),
            'levels': sorted(stats['levels'], key=lambda l: LEVEL_ORDER.get(l, 0)),
            'radical': db_entry.get('radical', ''),
            'components': list(db_entry.get('comp_set', set())),
            'sem_clusters': db_entry.get('sem_clusters', []),
            'meaning': db_entry.get('meaning', ''),
            'okurigana_set': sorted(stats['okurigana_set']),
            'positions': dict(stats['positions']),
            'word_details': stats['word_details'],
            'is_kun_heavy': stats['kun_count'] >= stats['on_count'] if total > 0 else False,
            'is_multi_kun': stats['kun_count'] >= 3,
        })
    return nodes, db_index


# ─── Phase 2: Edge Construction ──────────────────────────────────────────────

def build_shared_stem_edges(nodes, v9_data):
    """Kanji sharing exact KUN reading stems (from V9 ground truth, NOT on-yomi).
    Filter: 2-40 kanji per stem. Multi-mora stems get higher weight."""
    # Build kun-only stem index from V9 ground truth
    stem_kanji_map = defaultdict(set)
    stem_words = defaultdict(list)
    for word in v9_data['annotated_words']:
        for detail in word.get('gt_details', []):
            if detail['type'] == 'kun' and detail['reading']:
                stem = detail['reading']
                stem_kanji_map[stem].add(detail['kanji'])
                if len(stem_words[stem]) < 3:
                    stem_words[stem].append(f"{word['word']}({word['kana']})")

    node_ids = {n['id'] for n in nodes}
    edges = []
    for stem, kanjis in stem_kanji_map.items():
        jlpt_kanjis = sorted(k for k in kanjis if k in node_ids)
        n = len(jlpt_kanjis)
        if n < 2 or n > 40:
            continue
        weight_mult = 2.0 if len(stem) >= 2 else 1.0
        for k1, k2 in combinations(jlpt_kanjis, 2):
            edges.append({
                'source': k1, 'target': k2, 'type': 'shared_stem',
                'weight': round(min(1.0, n / 20) * weight_mult, 3),
                'stem': stem, 'n_kanji': n,
                'examples': stem_words.get(stem, [])[:3],
            })
    return edges, stem_kanji_map


def build_same_component_edges(nodes, kanji_db_index):
    """Share a non-radical component. Filter: 2-40 kanji per component."""
    node_ids = {n['id'] for n in nodes}
    comp_map = defaultdict(set)
    for n in nodes:
        db = kanji_db_index.get(n['id'], {})
        for comp in db.get('comp_set', set()):
            if comp and len(comp) == 1:
                comp_map[comp].add(n['id'])
    edges = []
    for comp, kanjis in comp_map.items():
        jlpt_kanjis = sorted(k for k in kanjis if k in node_ids)
        n = len(jlpt_kanjis)
        if n < 2 or n > 40:
            continue
        for k1, k2 in combinations(jlpt_kanjis, 2):
            edges.append({
                'source': k1, 'target': k2, 'type': 'same_component',
                'weight': round(min(1.0, n / 20), 3),
                'component': comp, 'n_kanji': n,
            })
    return edges


def build_same_radical_edges(nodes):
    """Share the same radical. Filter: 2-60 kanji per radical."""
    rad_map = defaultdict(set)
    for n in nodes:
        r = n.get('radical', '')
        if r:
            rad_map[r].add(n['id'])
    edges = []
    for rad, kanjis in rad_map.items():
        jlpt_kanjis = sorted(kanjis)
        n = len(jlpt_kanjis)
        if n < 2 or n > 60:
            continue
        for k1, k2 in combinations(jlpt_kanjis, 2):
            edges.append({
                'source': k1, 'target': k2, 'type': 'same_radical',
                'weight': 1.0, 'radical': rad, 'n_kanji': n,
            })
    return edges


def build_same_semantic_edges(nodes):
    """Share semantic domain. Filter: kun-heavy kanji (kun_ratio >= 0.3), max 80 per domain."""
    sem_map = defaultdict(set)
    for n in nodes:
        if n['kun_ratio'] < 0.3:
            continue
        for sc in n.get('sem_clusters', []):
            sem_map[sc].add(n['id'])
    edges = []
    for sem, kanjis in sem_map.items():
        jlpt_kanjis = sorted(kanjis)
        n = len(jlpt_kanjis)
        if n < 2 or n > 80:
            continue
        for k1, k2 in combinations(jlpt_kanjis, 2):
            edges.append({
                'source': k1, 'target': k2, 'type': 'same_semantic',
                'weight': 1.0, 'domain': sem, 'n_kanji': n,
            })
    return edges


def build_shared_okurigana_edges(nodes):
    """Appear with same okurigana suffix. Filter: 2-60 kanji per pattern."""
    oku_map = defaultdict(lambda: defaultdict(set))
    for n in nodes:
        for ok in n.get('okurigana_set', []):
            if ok:
                oku_map[ok[-1]][ok].add(n['id'])
    edges = []
    for last_char, oku_groups in oku_map.items():
        for ok, kanjis in oku_groups.items():
            jlpt_kanjis = sorted(kanjis)
            n = len(jlpt_kanjis)
            if n < 2 or n > 60:
                continue
            for k1, k2 in combinations(jlpt_kanjis, 2):
                edges.append({
                    'source': k1, 'target': k2, 'type': 'shared_okurigana',
                    'weight': round(min(1.0, n / 25), 3),
                    'okurigana': ok, 'n_kanji': n,
                })
    return edges


def build_compound_neighbor_edges(v9_data, nodes):
    """Appear together in compound words. Filter: co-occur >= 2 times."""
    node_ids = {n['id'] for n in nodes}
    pair_count = Counter()
    pair_words = defaultdict(list)
    for word in v9_data['annotated_words']:
        details = word.get('gt_details', [])
        kanjis = [d['kanji'] for d in details if d['kanji'] in node_ids]
        if len(kanjis) >= 2:
            for i in range(len(kanjis)):
                for j in range(i + 1, len(kanjis)):
                    pair = tuple(sorted([kanjis[i], kanjis[j]]))
                    pair_count[pair] += 1
                    if len(pair_words[pair]) < 3:
                        pair_words[pair].append(word['word'])
    edges = []
    for (k1, k2), count in pair_count.items():
        if count >= 2:
            edges.append({
                'source': k1, 'target': k2, 'type': 'compound_neighbor',
                'weight': round(min(1.0, count / 10), 3),
                'co_count': count, 'examples': pair_words[(k1, k2)],
            })
    return edges


def build_transitivity_edges(nodes):
    """Transitivity pairs through stem voicing alternation."""
    unvoiced_to_voiced = {
        'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
        'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
        'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
        'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
    }
    voiced_to_unvoiced = {v: k for k, v in unvoiced_to_voiced.items()}

    node_readings = {n['id']: set(n['kun_readings']) for n in nodes}
    node_ids = {n['id'] for n in nodes}
    edge_set = set()
    edge_stems = {}

    for ch1 in node_ids:
        for r1 in node_readings.get(ch1, set()):
            if not r1:
                continue
            first_mora = r1[0]
            if first_mora in unvoiced_to_voiced:
                voiced_reading = unvoiced_to_voiced[first_mora] + r1[1:]
                for ch2 in node_ids:
                    if ch2 <= ch1:
                        continue
                    if voiced_reading in node_readings.get(ch2, set()):
                        pair = (ch1, ch2)
                        edge_set.add(pair)
                        edge_stems[pair] = f'{r1}/{voiced_reading}'
            if first_mora in voiced_to_unvoiced:
                unvoiced_reading = voiced_to_unvoiced[first_mora] + r1[1:]
                for ch2 in node_ids:
                    if ch2 <= ch1:
                        continue
                    if unvoiced_reading in node_readings.get(ch2, set()):
                        pair = (ch1, ch2)
                        edge_set.add(pair)
                        edge_stems[pair] = f'{r1}/{unvoiced_reading}'

    edges = []
    for k1, k2 in edge_set:
        edges.append({
            'source': k1, 'target': k2, 'type': 'transitivity_pair',
            'weight': 1.0, 'stems': edge_stems.get((k1, k2), ''),
        })
    return edges


def build_same_on_edges(nodes):
    """Share an on-yomi reading. Filter: 2-50 kanji per reading."""
    on_map = defaultdict(set)
    for n in nodes:
        for r in n.get('on_readings', []):
            if r:
                on_map[r].add(n['id'])
    edges = []
    for on_rd, kanjis in on_map.items():
        jlpt_kanjis = sorted(kanjis)
        n = len(jlpt_kanjis)
        if n < 2 or n > 50:
            continue
        for k1, k2 in combinations(jlpt_kanjis, 2):
            edges.append({
                'source': k1, 'target': k2, 'type': 'same_on_reading',
                'weight': round(min(1.0, n / 30), 3),
                'on_reading': on_rd, 'n_kanji': n,
            })
    return edges


def build_co_occurring_stem_edges(nodes, reverse_index):
    """Share >= 3 stem families."""
    stem_index = reverse_index.get('stem_index', {})
    kanji_stems = defaultdict(set)
    for stem, kanjis in stem_index.items():
        for k in kanjis:
            kanji_stems[k].add(stem)

    node_ids = {n['id'] for n in nodes}
    stem_kanji_map = {s: ks for s, ks in
        ((s, set(k for k in kanjis if k in node_ids))
         for s, kanjis in
         ((stem, kanji_stems.get(stem, set()) & node_ids) for stem in stem_index)
         if 2 <= len(set(k for k in kanji_stems.get(stem, set()) & node_ids)) <= 30)
        if 2 <= len(ks) <= 30}

    pairs = defaultdict(int)
    for stem, kanjis in stem_kanji_map.items():
        jlpt_kanjis = sorted(kanjis)
        for k1, k2 in combinations(jlpt_kanjis, 2):
            pairs[(k1, k2)] += 1

    edges = []
    for (k1, k2), count in pairs.items():
        if count >= 3:
            edges.append({
                'source': k1, 'target': k2, 'type': 'co_occurring_stem',
                'weight': round(min(1.0, count / 6), 3),
                'shared_count': count,
            })
    return edges


def build_near_synonym_edges(nodes):
    """Same semantic domain + kun-heavy. Top 15 domains, max 40 per domain."""
    domain_count = Counter()
    for n in nodes:
        for sc in n.get('sem_clusters', []):
            domain_count[sc] += 1
    top_domains = {d for d, _ in domain_count.most_common(15)}

    node_by_domain = defaultdict(list)
    for n in nodes:
        for sc in n.get('sem_clusters', []):
            if sc in top_domains and n['kun_ratio'] > 0.5:
                node_by_domain[sc].append(n)

    edges = []
    for domain, domain_nodes in node_by_domain.items():
        jlpt_nodes = domain_nodes[:40]
        if len(jlpt_nodes) < 2:
            continue
        for i in range(len(jlpt_nodes)):
            for j in range(i + 1, len(jlpt_nodes)):
                n1, n2 = jlpt_nodes[i], jlpt_nodes[j]
                edges.append({
                    'source': n1['id'], 'target': n2['id'], 'type': 'near_synonym',
                    'weight': 1.0, 'domain': domain,
                })
    return edges


def build_radical_wclass_edges(nodes):
    """Same radical with strong word class tendency (>= 70% same direction)."""
    rad_groups = defaultdict(list)
    for n in nodes:
        r = n.get('radical', '')
        if r:
            rad_groups[r].append(n)
    edges = []
    for rad, group in rad_groups.items():
        if len(group) < 3:
            continue
        kun_heavy = sum(1 for n in group if n['kun_ratio'] >= 0.5)
        ratio = kun_heavy / len(group)
        if ratio >= 0.7 or ratio <= 0.3:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    edges.append({
                        'source': group[i]['id'], 'target': group[j]['id'],
                        'type': 'radical_wclass',
                        'weight': round(abs(ratio - 0.5) * 2, 3),
                        'radical': rad, 'ratio': round(ratio, 2),
                    })
    return edges


def build_semantic_stem_edges(nodes):
    """Same stem-final-mora + same okurigana pattern. Filter: 2-30 kanji."""
    stem_oku = defaultdict(lambda: defaultdict(set))
    for n in nodes:
        oku = ','.join(n.get('okurigana_set', [])[:3])
        if not oku:
            continue
        for r in n.get('kun_readings', []):
            if r:
                stem_oku[r[-1]][oku].add(n['id'])

    edges = []
    for last_mora, oku_groups in stem_oku.items():
        for oku, kanjis in oku_groups.items():
            jlpt_k = sorted(kanjis)
            n = len(jlpt_k)
            if n < 2 or n > 30:
                continue
            for i in range(len(jlpt_k)):
                for j in range(i + 1, len(jlpt_k)):
                    edges.append({
                        'source': jlpt_k[i], 'target': jlpt_k[j],
                        'type': 'semantic_stem',
                        'weight': round(min(1.0, n / 10), 3),
                        'last_mora': last_mora, 'okurigana_pattern': oku,
                    })
    return edges


def build_multi_kun_edges(nodes):
    """Both are multi-kun kanji (>= 3 kun readings).
    Only connect if they also share a stem, component, or radical — not a complete clique."""
    multi_kun = [n for n in nodes if n['is_multi_kun']]
    # Build lookup: kanji -> set of stems, components, radical
    mk_info = {}
    for n in multi_kun:
        mk_info[n['id']] = {
            'stems': set(n['kun_readings']),
            'radical': n.get('radical', ''),
            'components': set(n.get('components', [])),
            'kun_count': n['kun_count'],
        }
    edges = []
    for i in range(len(multi_kun)):
        for j in range(i + 1, len(multi_kun)):
            n1, n2 = multi_kun[i], multi_kun[j]
            info1, info2 = mk_info[n1['id']], mk_info[n2['id']]
            # Need at least one shared attribute to connect
            shared_stems = info1['stems'] & info2['stems']
            shared_comps = info1['components'] & info2['components']
            shared_rad = info1['radical'] and info2['radical'] and info1['radical'] == info2['radical']
            if shared_stems or shared_comps or shared_rad:
                reasons = []
                if shared_stems: reasons.append(f'共享词干: {", ".join(sorted(shared_stems)[:3])}')
                if shared_comps: reasons.append(f'共享部件: {", ".join(sorted(shared_comps)[:3])}')
                if shared_rad: reasons.append(f'共享部首: {info1["radical"]}')
                weight = min(1.0, (len(shared_stems) * 0.4 + len(shared_comps) * 0.3 + (0.3 if shared_rad else 0)))
                edges.append({
                    'source': n1['id'], 'target': n2['id'],
                    'type': 'multi_kun_hub',
                    'weight': round(weight, 3),
                    'kun_counts': f'{n1["kun_count"]}/{n2["kun_count"]}',
                    'reasons': reasons,
                })
    return edges


# ─── Phase 3: Graph Analytics ────────────────────────────────────────────────

def compute_graph_stats(nodes, edges):
    """Compute degree, betweenness, and community info."""
    node_ids = {n['id'] for n in nodes}
    adj = defaultdict(set)
    for e in edges:
        u, v = e['source'], e['target']
        if u in node_ids and v in node_ids:
            adj[u].add(v)
            adj[v].add(u)

    # Degree centrality
    max_deg = max((len(adj.get(nid, set())) for nid in node_ids), default=1)
    degrees = {nid: len(adj.get(nid, set())) / max_deg for nid in node_ids}
    raw_degrees = {nid: len(adj.get(nid, set())) for nid in node_ids}

    # Betweenness (sampled)
    betweenness = {nid: 0.0 for nid in node_ids}
    sample_nodes = sorted(node_ids, key=lambda x: len(adj.get(x, set())), reverse=True)[:150]
    for s in sample_nodes:
        dist = {s: 0}
        sigma = defaultdict(float)
        sigma[s] = 1
        delta = defaultdict(float)
        predecessors = defaultdict(list)
        visited = {s}
        queue = [s]
        order = []
        while queue:
            v = queue.pop(0)
            order.append(v)
            for w in adj.get(v, set()):
                if w not in visited:
                    visited.add(w)
                    queue.append(w)
                    dist[w] = dist[v] + 1
                if dist.get(w, float('inf')) == dist.get(v, float('inf')) + 1:
                    sigma[w] += sigma[v]
                    predecessors[w].append(v)
        for w in reversed(order):
            for v in predecessors[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w]) if sigma[w] > 0 else 0
            if w != s:
                betweenness[w] += delta[w]

    max_bet = max(betweenness.values()) if betweenness else 1
    betweenness = {nid: v / max_bet for nid, v in betweenness.items()}
    return degrees, raw_degrees, betweenness, adj


def connected_components(nodes, edges):
    """Find connected components using BFS (more stable than label propagation)."""
    node_ids = {n['id'] for n in nodes}
    adj = defaultdict(set)
    for e in edges:
        u, v = e['source'], e['target']
        if u in node_ids and v in node_ids:
            adj[u].add(v)
            adj[v].add(u)

    visited = set()
    components = {}
    comp_id = 0
    for nid in sorted(node_ids):
        if nid in visited:
            continue
        # BFS
        queue = [nid]
        visited.add(nid)
        members = [nid]
        while queue:
            v = queue.pop(0)
            for w in adj.get(v, set()):
                if w not in visited:
                    visited.add(w)
                    members.append(w)
                    queue.append(w)
        if len(members) >= 3:  # only meaningful clusters
            for m in members:
                components[m] = comp_id
            comp_id += 1

    return components


# ─── Phase 4: Cognitive Map Markdown ─────────────────────────────────────────

def build_kanji_index(nodes):
    """Build a lookup: kanji -> node."""
    return {n['id']: n for n in nodes}


def node_display(n, kidx):
    """Format a kanji node for display."""
    kun_str = ', '.join(n['kun_readings'][:4])
    on_str = ', '.join(n['on_readings'][:3])
    levels = '/'.join(n['levels'])
    meaning = n['meaning'][:20] if n['meaning'] else ''
    words = ', '.join(wd['word'] for wd in n['word_details'][:3])
    return (f"**{n['id']}** ({meaning}) [{levels}] "
            f"训:{kun_str or '—'} 音:{on_str or '—'} "
            f"例:{words}")


def generate_cognitive_map(nodes, all_edges, degrees, raw_degrees, betweenness, adj,
                           stem_kanji_map, kanji_db_index):
    """Generate the comprehensive cognitive map Markdown."""

    kidx = build_kanji_index(nodes)
    node_ids = {n['id'] for n in nodes}

    # ── Compute edge groupings for the map ──

    # Group edges by type
    edges_by_type = defaultdict(list)
    for e in all_edges:
        edges_by_type[e['type']].append(e)

    # ── Shared stem groups (most useful for learners) ──
    stem_groups = defaultdict(list)
    for e in edges_by_type.get('shared_stem', []):
        stem = e.get('stem', '')
        stem_groups[stem].append((e['source'], e['target']))

    # Build stem -> kanji list
    stem_kanji = defaultdict(set)
    for e in edges_by_type.get('shared_stem', []):
        stem = e.get('stem', '')
        stem_kanji[stem].add(e['source'])
        stem_kanji[stem].add(e['target'])

    # Filter to meaningful stems (>= 3 kanji or multi-mora stems with >= 2)
    meaningful_stems = []
    for stem, kanjis in stem_kanji.items():
        n = len(kanjis)
        if n >= 3 or (n >= 2 and len(stem) >= 2):
            meaningful_stems.append((stem, sorted(kanjis), n))
    meaningful_stems.sort(key=lambda x: -x[2])

    # ── Component groups ──
    comp_groups = defaultdict(set)
    for e in edges_by_type.get('same_component', []):
        comp = e.get('component', '')
        comp_groups[comp].add(e['source'])
        comp_groups[comp].add(e['target'])
    meaningful_comps = [(c, sorted(ks), len(ks)) for c, ks in comp_groups.items() if len(ks) >= 3]
    meaningful_comps.sort(key=lambda x: -x[2])

    # ── Radical groups ──
    rad_groups = defaultdict(set)
    for e in edges_by_type.get('same_radical', []):
        rad = e.get('radical', '')
        rad_groups[rad].add(e['source'])
        rad_groups[rad].add(e['target'])

    # Compute radical tendency
    rad_tendency = {}
    for rad, kanjis in rad_groups.items():
        nodes_in_rad = [kidx.get(k) for k in kanjis if k in kidx]
        if not nodes_in_rad:
            continue
        kun_ratio = sum(1 for n in nodes_in_rad if n['kun_ratio'] >= 0.5) / len(nodes_in_rad)
        dominant = '训读' if kun_ratio >= 0.6 else '音读' if kun_ratio <= 0.4 else '混合'
        rad_tendency[rad] = (sorted(kanjis), len(kanjis), round(kun_ratio, 2), dominant)
    meaningful_rads = sorted(rad_tendency.items(), key=lambda x: -x[1][1])

    # ── Semantic domain groups ──
    sem_groups = defaultdict(set)
    for e in edges_by_type.get('same_semantic', []):
        dom = e.get('domain', '')
        sem_groups[dom].add(e['source'])
        sem_groups[dom].add(e['target'])
    meaningful_sems = [(d, sorted(ks), len(ks)) for d, ks in sem_groups.items() if len(ks) >= 3]
    meaningful_sems.sort(key=lambda x: -x[2])

    # ── Okurigana groups ──
    oku_groups = defaultdict(set)
    for e in edges_by_type.get('shared_okurigana', []):
        ok = e.get('okurigana', '')
        oku_groups[ok].add(e['source'])
        oku_groups[ok].add(e['target'])
    meaningful_okus = [(ok, sorted(ks), len(ks)) for ok, ks in oku_groups.items() if len(ks) >= 3]
    meaningful_okus.sort(key=lambda x: -x[2])

    # ── Compound neighbor pairs (frequent co-occurrence) ──
    comp_pairs = []
    for e in edges_by_type.get('compound_neighbor', []):
        count = e.get('co_count', 0)
        if count >= 3:
            comp_pairs.append((e['source'], e['target'], count, e.get('examples', [])))
    comp_pairs.sort(key=lambda x: -x[2])

    # ── Transitivity pairs ──
    trans_pairs = []
    for e in edges_by_type.get('transitivity_pair', []):
        trans_pairs.append((e['source'], e['target'], e.get('stems', '')))
    trans_pairs.sort()

    # ── Top hubs and bridges ──
    top_hubs = sorted(raw_degrees.items(), key=lambda x: -x[1])[:25]
    top_bridges = sorted(betweenness.items(), key=lambda x: -x[1])[:25]

    # ── Multi-kun kanji ──
    multi_kun = sorted(
        [n for n in nodes if n['is_multi_kun']],
        key=lambda n: -n['kun_count']
    )

    # ── Natural Study Groups: Kanji sharing BOTH radical AND semantic domain ──
    # These are the most coherent groups for learning
    rad_sem_groups = defaultdict(list)
    for n in nodes:
        rad = n.get('radical', '')
        for sc in n.get('sem_clusters', []):
            if rad and sc:
                rad_sem_groups[(rad, sc)].append(n)
    study_groups = []
    for (rad, sem), members in rad_sem_groups.items():
        if len(members) >= 3:
            kun_ratio = sum(1 for n in members if n['kun_ratio'] >= 0.5) / len(members)
            study_groups.append({
                'radical': rad, 'semantic': sem, 'size': len(members),
                'kun_ratio': round(kun_ratio, 2),
                'members': [n['id'] for n in members[:12]],
            })
    study_groups.sort(key=lambda x: -x['size'])

    # ── Edge stats ──
    edge_counts = Counter(e['type'] for e in all_edges)

    # ═══════════════════════════════════════════════════════════════
    # Generate the Markdown
    # ═══════════════════════════════════════════════════════════════

    lines = []
    def w(s=''):
        lines.append(s)

    w('# 训读关联网络 · 认知地图')
    w()
    w('> **这不是规则系统，这是一张地图。**')
    w('> ')
    w('> 每个汉字都是一个节点。节点之间通过14种关系相连——')
    w('> 共享词干、共享部件、共享部首、共享语义域、共享送假名、')
    w('> 复合词共现、清浊对应、连浊变体、共享音读、词干家族、')
    w('> 近义邻居、部首词类倾向、语义词干模式、多训字枢纽。')
    w('> ')
    w(f'> {len(nodes)} 个JLPT汉字、{len(all_edges)} 条连接、{len(edge_counts)} 种关系类型。')
    w('> ')
    w('> **使用方式**：按章节阅读，每章展示一种连接方式。遇到不认识的汉字时，')
    w('> 回想它属于哪个"家族"——同词干的、同部件的、同部首的、还是同语义域的——')
    w('> 然后从已知成员推导未知成员。')
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 0: Quick Start — Top 20 Hub Kanji
    # ═══════════════════════════════════════
    w('## 0. 网络枢纽：连接最多的25个汉字')
    w()
    w('这些汉字是整个网络中连接最多的节点。先认识它们，就拥有了最多的"锚点"。')
    w()
    w('| # | 汉字 | 连接度 | 训/音 | JLPT | 核心训读 | 义 |')
    w('|---|------|--------|-------|------|---------|----|')
    for i, (ch, deg) in enumerate(top_hubs, 1):
        n = kidx.get(ch)
        if not n:
            continue
        kun = ', '.join(n['kun_readings'][:4])
        w(f"| {i} | **{ch}** | {deg} | {n['kun_count']}/{n['on_count']} | "
          f"{'/'.join(n['levels'])} | {kun} | {n['meaning'][:15]} |")
    w()

    w('### 桥梁汉字（高介数中心性）')
    w()
    w('这些汉字连接不同的聚类，是"跨界者"。认识它们，就能在不同知识群之间跳转。')
    w()
    w('| # | 汉字 | 介数 | 连接度 | 核心训读 |')
    w('|---|------|------|--------|---------|')
    for i, (ch, bet) in enumerate(top_bridges[:15], 1):
        n = kidx.get(ch)
        if not n:
            continue
        kun = ', '.join(n['kun_readings'][:4])
        w(f"| {i} | **{ch}** | {bet:.3f} | {raw_degrees.get(ch, 0)} | {kun} |")
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 1: Shared Stem Map
    # ═══════════════════════════════════════
    w('## 1. 共享词干地图（Shared Stem）')
    w()
    w(f'> *{EDGE_META["shared_stem"][1]}*')
    w()
    w(f'共 {len(meaningful_stems)} 个词干家族（≥3个JLPT汉字共享，或≥2个多拍词干）。')
    w()
    w('### 核心词干家族（≥4个汉字）')
    w()
    for stem, kanjis, n in meaningful_stems:
        if n < 4:
            break
        w(f'#### 词干 「**{stem}**」 → {n}个字')
        w()
        w('| 汉字 | 所有训读 | 所有音读 | JLPT级别 | 词例 |')
        w('|------|---------|---------|---------|------|')
        for k in kanjis:
            nk = kidx.get(k)
            if not nk:
                continue
            kun = ', '.join(nk['kun_readings'][:4])
            onr = ', '.join(nk['on_readings'][:3])
            words = ', '.join(wd['word'] for wd in nk['word_details'][:3])
            w(f"| **{k}** | {kun} | {onr or '—'} | {'/'.join(nk['levels'])} | {words} |")
        w()

    w('### 中型词干家族（3个汉字）')
    w()
    for stem, kanjis, n in meaningful_stems:
        if n != 3:
            continue
        kun_samples = ', '.join(f'{k}({"/".join(kidx[k]["kun_readings"][:2])})' for k in kanjis if k in kidx)
        w(f'- **{stem}**: {kun_samples}')
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 2: Component Families
    # ═══════════════════════════════════════
    w('## 2. 部件家族（Component Families）')
    w()
    w(f'> *{EDGE_META["same_component"][1]}*')
    w()
    w(f'共 {len(meaningful_comps)} 个部件家族（≥3个JLPT汉字共享同一非部首部件）。')
    w()
    w('### 核心部件家族（≥5个汉字）')
    w()
    for comp, kanjis, n in meaningful_comps:
        if n < 5:
            break
        # Find the common stem these kanji might share
        stems_in_family = Counter()
        for k in kanjis:
            nk = kidx.get(k)
            if nk:
                for r in nk['kun_readings']:
                    stems_in_family[r] += 1
        common_stems = [s for s, c in stems_in_family.most_common(3) if c >= 2]

        w(f'#### 部件 「**{comp}**」 → {n}个字')
        if common_stems:
            w(f'> 可能共享词干: {", ".join(common_stems)}')
        w()
        w('| 汉字 | 训读 | 音读 | JLPT |')
        w('|------|------|------|------|')
        for k in kanjis:
            nk = kidx.get(k)
            if not nk:
                continue
            kun = ', '.join(nk['kun_readings'][:3])
            onr = ', '.join(nk['on_readings'][:3])
            w(f"| **{k}** | {kun or '—'} | {onr or '—'} | {'/'.join(nk['levels'])} |")
        w()

    w('### 小型部件家族（3-4个汉字）')
    w()
    for comp, kanjis, n in meaningful_comps:
        if n >= 5:
            continue
        samples = ', '.join(f'{k}({"/".join(kidx[k]["kun_readings"][:1])})' for k in kanjis if k in kidx)
        w(f'- **{comp}** ({n}): {samples}')
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 3: Radical Clusters
    # ═══════════════════════════════════════
    w('## 3. 部首聚类（Radical Clusters）')
    w()
    w(f'> *{EDGE_META["same_radical"][1]}*')
    w()
    w('### 部首→训读/音读倾向')
    w()
    w('| 部首 | JLPT字数 | 训读比例 | 倾向 | 例字 |')
    w('|------|---------|---------|------|------|')
    for rad, (kanjis, n, kun_ratio, dominant) in meaningful_rads[:40]:
        samples = ', '.join(kanjis[:8])
        w(f"| {rad} | {n} | {kun_ratio:.0%} | **{dominant}** | {samples} |")
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 4: Semantic Domain
    # ═══════════════════════════════════════
    w('## 4. 语义域邻居（Semantic Domain Neighbors）')
    w()
    w(f'> *{EDGE_META["same_semantic"][1]}*')
    w()
    for domain, kanjis, n in meaningful_sems:
        w(f'### {domain}（{n}个训读倾向字）')
        samples = []
        for k in kanjis[:15]:
            nk = kidx.get(k)
            if nk:
                samples.append(f'{k}({"/".join(nk["kun_readings"][:2])})')
        w(', '.join(samples))
        w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 5: Okurigana Patterns
    # ═══════════════════════════════════════
    w('## 5. 送假名密码本（Okurigana Patterns）')
    w()
    w(f'> *{EDGE_META["shared_okurigana"][1]}*')
    w()
    w('### 高频送假名家族')
    w()
    for ok, kanjis, n in meaningful_okus[:25]:
        w(f'#### 送假名「**{ok}**」→ {n}个汉字')
        samples = []
        for k in kanjis[:12]:
            nk = kidx.get(k)
            if nk:
                # Find which reading uses this okurigana
                matching = [wd for wd in nk['word_details'] if ok in wd['kana']]
                readings = ', '.join(set(wd['reading'] for wd in matching[:3]))
                samples.append(f'{k}({readings})')
        w(', '.join(samples))
        w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 6: Compound Co-occurrence
    # ═══════════════════════════════════════
    w('## 6. 复合词共现（Compound Co-occurrence）')
    w()
    w(f'> *{EDGE_META["compound_neighbor"][1]}*')
    w()
    w('以下汉字在JLPT词汇中频繁共同出现（≥3次）：')
    w()
    w('| 汉字A | 汉字B | 共现次数 | 例词 |')
    w('|-------|-------|---------|------|')
    for k1, k2, count, examples in comp_pairs[:40]:
        w(f"| **{k1}** | **{k2}** | {count} | {', '.join(examples[:3])} |")
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 7: Transitivity Pairs
    # ═══════════════════════════════════════
    w('## 7. 清浊自他对应（Transitivity Pairs）')
    w()
    w(f'> *{EDGE_META["transitivity_pair"][1]}*')
    w()
    w('| 清音字 | 浊音字 | 词干对应 |')
    w('|--------|--------|---------|')
    for k1, k2, stems in trans_pairs[:30]:
        n1, n2 = kidx.get(k1), kidx.get(k2)
        k1_words = ', '.join(wd['word'] for wd in n1['word_details'][:2]) if n1 else ''
        k2_words = ', '.join(wd['word'] for wd in n2['word_details'][:2]) if n2 else ''
        w(f"| **{k1}** ({k1_words}) | **{k2}** ({k2_words}) | {stems} |")
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 8: Multi-Kun Hubs
    # ═══════════════════════════════════════
    w('## 8. 多训字枢纽（Multi-Kun Hubs）')
    w()
    w(f'> *{EDGE_META["multi_kun_hub"][1]}*')
    w()
    w(f'JLPT中共有 {len(multi_kun)} 个汉字拥有≥3个训读，占总数的 {len(multi_kun)/max(len(nodes),1)*100:.1f}%。')
    w('这些"怪物汉字"是网络中连接最多的节点——每增加一个训读，就增加了与共享该词干的家族成员的连接。')
    w()
    w('### 顶级多训字（按训读数排序）')
    w()
    w('| 汉字 | 训读数 | 全部训读 | JLPT | 义 |')
    w('|------|--------|---------|------|----|')
    for n in multi_kun[:25]:
        w(f"| **{n['id']}** | {n['kun_count']} | {', '.join(n['kun_readings'][:8])} | "
          f"{'/'.join(n['levels'])} | {n['meaning'][:20]} |")
    w()

    w('### 多训字的训读之间有什么关联？')
    w()
    w('多训字的多个训读不是随机的，它们之间存在规律性关系：')
    w()
    w('1. **自他对应**：止(とまる/とめる)、付(つく/つける)、切(きれる/きる)')
    w('2. **具体/抽象**：上(うえ/あがる)、下(した/さがる)')
    w('3. **名词/动词**：空(そら/あく)、休(やすみ/やすむ)')
    w('4. **清浊对立（连浊来源）**：切(きる/ぎれる)、付(つく/づく)')
    w()
    w('**学习策略**：不要把多训字的多个训读当作孤立的事实去背。理解它们之间的语义/语法关系，')
    w('把一个字的多个读法当作"一个词干家族的变体"来学。')
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 9: Community Map
    # ═══════════════════════════════════════
    w('## 9. 自然学习群：部首 × 语义域')
    w()
    w('这些组合同一个"部首+语义域"的自然学习群——部首提供词类倾向，语义域提供读法模式。')
    w()
    w(f'共发现 {len(study_groups)} 个自然学习群（≥3个成员）。')
    w()
    w('| 部首 | 语义域 | 字数 | 训读比例 | 成员示例 |')
    w('|------|--------|------|---------|---------|')
    for sg in study_groups[:30]:
        members_str = ', '.join(sg['members'][:8])
        tendency = '训' if sg['kun_ratio'] >= 0.6 else '音' if sg['kun_ratio'] <= 0.4 else '混'
        w(f"| {sg['radical']} | {sg['semantic']} | {sg['size']} | "
          f"{sg['kun_ratio']:.0%} ({tendency}) | {members_str} |")
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 10: Edge Type Overview
    # ═══════════════════════════════════════
    w('## 10. 连接类型总览')
    w()
    w('| 连接类型 | 边数 | 学习用途 |')
    w('|---------|------|---------|')
    for etype, (name, desc) in EDGE_META.items():
        count = edge_counts.get(etype, 0)
        w(f"| **{name}** | {count} | {desc} |")
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 11: Learning Pathways
    # ═══════════════════════════════════════
    w('## 11. 基于网络的学习路径建议')
    w()
    w('### 路径1: 从枢纽开始（Top-Down）')
    w()
    w('1. 先记前10个枢纽汉字及其所有训读（本章第0节）')
    w('2. 通过枢纽汉字的"共享词干"边，找到同一词干家族的其他字')
    w('3. 通过"共享部件"边，找到同部件家族')
    w('4. 通过"复合词共现"边，找到常一起出现的搭配')
    w('5. 从每个新发现的字出发，重复步骤2-4')
    w()
    w('### 路径2: 从家族出发（Bottom-Up）')
    w()
    w('1. 挑一个你感兴趣的语义域（如"身体部位"、"自然现象"）——见第4节')
    w('2. 看该域中的所有训读倾向字，注意它们的词干模式')
    w('3. 通过"共享词干"边，扩展到使用相同词干的字')
    w('4. 通过"共享部首"边，扩展到同部首的其他字')
    w()
    w('### 路径3: 从送假名出发（Morphological）')
    w()
    w('1. 看第5节的送假名密码本')
    w('2. 同一个送假名=同一个词类=同一个活用模式')
    w('3. 比如"〜める"的所有汉字都共享他动词下一段活用的读法模式')
    w('4. 学会一个，就能推导同家族的所有字')
    w()
    w('### 路径4: 从多训字出发（Hub-First）')
    w()
    w('1. 看第8节的前25个多训字')
    w('2. 这些字是网络中的"超级连接者"——它们的每一个训读都连接一个家族')
    w('3. 学会一个多训字=拥有多个家族入口')
    w('4. 例如学会"生"(い/う/は/なま/き)，就连接了5个词干家族')
    w()
    w('---')
    w()

    # ═══════════════════════════════════════
    # Chapter 12: Quick Reference
    # ═══════════════════════════════════════
    w('## 12. 速查表：关系类型 × 信号强度')
    w()
    w('| 关系类型 | 信号强度 | 可靠度 | 适用场景 |')
    w('|---------|---------|--------|---------|')
    w('| 共享词干（多拍） | ★★★★★ | 高 | 看到同词干的已知字 → 直接推导读法 |')
    w('| 共享送假名 | ★★★★★ | 极高 | 相同送假名=相同词类=相同活用 |')
    w('| 共享部首+词类倾向 | ★★★★ | 高 | 同部首=同词类（如手部→动词） |')
    w('| 共享语义域 | ★★★★ | 中高 | 同语义域=同读法倾向（训/音） |')
    w('| 清浊自他对应 | ★★★★ | 高 | 知道自动词→直接推他动词 |')
    w('| 共享部件 | ★★★ | 中 | 同部件可能同词干，但不如直接记词干靠谱 |')
    w('| 共享音读 | ★★★ | 中 | 音读相同的字往往训读模式也相似 |')
    w('| 复合词共现 | ★★ | 中 | 帮助记忆词汇组合，不直接帮助读法 |')
    w('| 词干家族共现 | ★★ | 低 | 高级模式，不适合初学者 |')
    w('| 连浊变体 | ★ | 高但窄 | 知道现象即可，不需要记具体配对 |')
    w()
    w('---')
    w()
    w(f'*生成时间：2026-05-07 | 数据基础：46,849汉字DB + 9,572 JLPT词汇 + V9标注 | {len(nodes)}个JLPT汉字*')

    return '\n'.join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading data...")
    v9_data = load_v9_data()
    reverse_index = json.load(open(REVERSE_PATH))
    print(f"  V9: {len(v9_data['annotated_words'])} words")
    print(f"  Reverse index: {len(reverse_index.get('stem_index', {}))} stems")

    print("Loading kanji database...")
    kanji_db = load_kanji_db(KANJI_DB_PATH)
    kanji_db_index = {k['kanji']: k for k in kanji_db}
    print(f"  {len(kanji_db)} kanji total")

    # Phase 1: Nodes
    print("Phase 1: Extracting nodes...")
    nodes, kidx_local = build_nodes(v9_data, kanji_db)
    print(f"  {len(nodes)} JLPT kanji extracted")

    # Phase 2: Edges
    print("Phase 2: Building edges...")
    all_edges = []

    edge_builders = [
        ('shared_stem', lambda: build_shared_stem_edges(nodes, v9_data)),
        ('same_component', lambda: build_same_component_edges(nodes, kanji_db_index)),
        ('same_radical', build_same_radical_edges),
        ('same_semantic', build_same_semantic_edges),
        ('shared_okurigana', build_shared_okurigana_edges),
        ('compound_neighbor', lambda: build_compound_neighbor_edges(v9_data, nodes)),
        ('transitivity_pair', lambda: build_transitivity_edges(nodes)),
    ]
    stem_kanji_map = {}
    for etype, builder in edge_builders:
        result = builder(nodes) if etype in ('same_radical', 'same_semantic', 'shared_okurigana') else builder()
        if etype == 'shared_stem':
            edges, stem_kanji_map = result
        else:
            edges = result
        all_edges.extend(edges)
        print(f"  {etype}: {len(edges)} edges")

    aux_builders = [
        ('same_on_reading', build_same_on_edges),
        ('co_occurring_stem', lambda: build_co_occurring_stem_edges(nodes, reverse_index)),
        ('near_synonym', build_near_synonym_edges),
        ('radical_wclass', build_radical_wclass_edges),
        ('semantic_stem', build_semantic_stem_edges),
        ('multi_kun_hub', build_multi_kun_edges),
    ]
    for etype, builder in aux_builders:
        edges = builder(nodes) if etype in ('same_on_reading', 'near_synonym', 'radical_wclass', 'semantic_stem', 'multi_kun_hub') else builder()
        all_edges.extend(edges)
        print(f"  {etype}: {len(edges)} edges")

    # Deduplicate
    edge_map = {}
    for e in all_edges:
        key = (min(e['source'], e['target']), max(e['source'], e['target']), e['type'])
        if key not in edge_map or e['weight'] > edge_map[key]['weight']:
            edge_map[key] = e
    all_edges = list(edge_map.values())
    print(f"  Total after dedup: {len(all_edges)} edges")

    # Phase 3: Analytics
    print("Phase 3: Computing analytics...")
    degrees, raw_degrees, betweenness, adj = compute_graph_stats(nodes, all_edges)
    # Build stem-based clusters for the cognitive map — these are the "natural study groups"
    stem_clusters = defaultdict(list)
    for e in all_edges:
        if e['type'] == 'shared_stem' and e.get('stem') and len(e.get('stem', '')) >= 2:
            stem_clusters[e['stem']].append((e['source'], e['target']))

    # Phase 4: Output JSON
    print("Phase 4: Generating JSON data...")
    json_nodes = []
    for n in nodes:
        json_nodes.append({
            'id': n['id'], 'kun_count': n['kun_count'], 'on_count': n['on_count'],
            'kun_readings': n['kun_readings'], 'on_readings': n['on_readings'],
            'levels': n['levels'], 'radical': n['radical'],
            'sem_clusters': n['sem_clusters'], 'meaning': n['meaning'],
            'is_multi_kun': n['is_multi_kun'],
            'degree_raw': raw_degrees.get(n['id'], 0),
            'betweenness': round(betweenness.get(n['id'], 0), 4),
            'okurigana': n['okurigana_set'][:5],
            'word_details': n['word_details'],
        })

    with open(OUT_JSON, 'w') as f:
        json.dump({'nodes': json_nodes, 'edges': all_edges,
                    'top_hubs': sorted(raw_degrees.items(), key=lambda x: -x[1])[:50],
                    'top_bridges': sorted(betweenness.items(), key=lambda x: -x[1])[:50]},
                   f, ensure_ascii=False, indent=2)
    print(f"  -> {OUT_JSON}")

    # Phase 5: Generate Cognitive Map
    print("Phase 5: Generating cognitive map Markdown...")
    report = generate_cognitive_map(
        nodes, all_edges, degrees, raw_degrees, betweenness, adj,
        stem_kanji_map, kanji_db_index
    )
    with open(OUT_MAP_MD, 'w') as f:
        f.write(report)
    print(f"  -> {OUT_MAP_MD} ({len(report)} chars)")

    print("\nDone! Open kun_network_map.md for the cognitive map.")


if __name__ == '__main__':
    main()
