#!/usr/bin/env python3
"""
kun_alt_paths.py — Alternative Learning Path Exploration

Explores multiple fundamentally different approaches beyond greedy set-cover:
1. Decision tree (minimum entropy splits) — a genuine learning flow
2. Component→reading correlation — can parts predict readings?
3. Network hubs-first — learn central kanji, propagate to neighbors
4. Transitivity multiplier — learn one, get the other near-free
5. Okurigana-constrained reading candidates — narrow possibilities
6. Compound co-occurrence constraint — known kanji constrains unknown

All analysis is per JLPT level, using V9 ground truth.
"""

import json
import os
import sys
import math
from collections import Counter, defaultdict
from itertools import combinations

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from gold_panning_v3 import load_kanji_db

V9_PATH = f'{BASE}/output/kun_v9_data.json'
KANJI_DB_PATH = f'{BASE}/漢字検索V2.xlsm'
OUT_MD = f'{BASE}/output/kun_alt_paths.md'

LEVEL_ORDER = {'N5': 5, 'N4': 4, 'N3': 3, 'N2': 2, 'N1': 1}


def load_v9():
    with open(V9_PATH) as f:
        return json.load(f)


def build_instances(v9_data, kanji_db):
    """Extract per-kanji instances with features."""
    db_idx = {k['kanji']: k for k in kanji_db}
    instances = defaultdict(list)

    for word in v9_data['annotated_words']:
        level = word['level']
        kanji_chars = [d['kanji'] for d in word['gt_details']]
        n_kanji = len(kanji_chars)
        word_kana = word['kana']

        for i, detail in enumerate(word['gt_details']):
            ch = detail['kanji']
            gt_type = detail['type']
            gt_reading = detail['reading']

            db = db_idx.get(ch, {})
            sem = db.get('sem_clusters', [])
            rad = db.get('radical', '')
            comps = list(db.get('comp_set', set()))
            on_list = db.get('on_list', [])
            kun_list = db.get('kun_list', [])

            if n_kanji == 1:
                pos = 'alone'
            elif i == 0:
                pos = 'start'
            elif i == n_kanji - 1:
                pos = 'end'
            else:
                pos = 'middle'

            okurigana = ''
            has_okuri = False
            if gt_type == 'kun' and gt_reading:
                idx = word_kana.find(gt_reading)
                if idx >= 0:
                    okurigana = word_kana[idx + len(gt_reading):]
                    has_okuri = len(okurigana) > 0

            instances[level].append({
                'kanji': ch, 'gt_type': gt_type, 'gt_reading': gt_reading,
                'word': word['word'], 'kana': word_kana,
                'pos': pos, 'n_kanji': n_kanji,
                'has_okuri': has_okuri, 'okurigana': okurigana,
                'sem': sem, 'radical': rad, 'components': comps,
                'on_list': on_list, 'kun_list': kun_list,
            })

    return instances


# ═══════════════════════════════════════════════════════════════════════════════
# APPROACH 1: Decision Tree (Minimum Entropy)
# ═══════════════════════════════════════════════════════════════════════════════

def explore_decision_tree(instances_by_level):
    """
    Build a decision tree where each split is a yes/no question about the kanji.
    Goal: minimize expected questions to classify on/kun → narrow readings.

    For on/kun classification (A problem), the existing rules are near-optimal.
    The real question: AFTER deciding it's kun, what's the best branching?
    """
    results = {}
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        kun_insts = [i for i in instances_by_level[level] if i['gt_type'] == 'kun']
        N_all = len(instances_by_level[level])
        N_kun = len(kun_insts)

        # For kun instances, try splitting by:
        # 1. okurigana patterns → which ones most reduce reading entropy?
        # 2. radical → how many readings collapse?
        # 3. semantic domain → reading narrowing?
        # 4. component presence → reading hints?

        # --- Okurigana as reading constraint ---
        # For each common okurigana, how many unique readings does it allow?
        oku_to_readings = defaultdict(set)
        oku_to_count = Counter()
        for inst in kun_insts:
            if inst['has_okuri'] and inst['okurigana']:
                oku = inst['okurigana']
                oku_to_readings[oku].add(inst['gt_reading'])
                oku_to_count[oku] += 1

        # Entropy reduction: if knowing okurigana narrows readings from N_kun to K,
        # information gain = log2(N_kun) - log2(K)
        # But better: just show the reduction ratio
        top_oku = sorted(oku_to_count.items(), key=lambda x: -x[1])[:10]
        oku_analysis = []
        for oku, count in top_oku:
            readings = oku_to_readings[oku]
            if len(readings) <= 5:  # only interesting if it actually narrows
                oku_analysis.append({
                    'okurigana': oku, 'count': count,
                    'unique_readings': len(readings),
                    'readings': sorted(readings)[:10],
                    'coverage_pct': round(count / N_kun * 100, 1),
                    'reduction': f'{N_kun}→{len(readings)} ({count}例)'
                })

        # --- Radical as reading constraint ---
        rad_to_readings = defaultdict(set)
        rad_to_count = Counter()
        for inst in kun_insts:
            if inst['radical']:
                rad_to_readings[inst['radical']].add(inst['gt_reading'])
                rad_to_count[inst['radical']] += 1
        top_rad = sorted(rad_to_count.items(), key=lambda x: -x[1])[:15]
        rad_analysis = []
        for rad, count in top_rad:
            readings = rad_to_readings[rad]
            rad_analysis.append({
                'radical': rad, 'count': count,
                'unique_readings': len(readings),
                'coverage_pct': round(count / N_kun * 100, 1),
                'entropy_per_instance': round(len(readings) / count * 100, 1)
                if count > 0 else 0,
            })

        # --- Semantic domain as reading constraint ---
        sem_to_readings = defaultdict(set)
        sem_to_count = Counter()
        for inst in kun_insts:
            for s in inst['sem']:
                sem_to_readings[s].add(inst['gt_reading'])
                sem_to_count[s] += 1
        sem_analysis = []
        for sem, count in sem_to_count.most_common(10):
            readings = sem_to_readings[sem]
            sem_analysis.append({
                'semantic': sem, 'count': count,
                'unique_readings': len(readings),
                'coverage_pct': round(count / N_kun * 100, 1),
            })

        # --- Component→reading direct mapping ---
        comp_to_readings = defaultdict(set)
        comp_to_count = Counter()
        for inst in kun_insts:
            for comp in inst['components']:
                comp_to_readings[comp].add(inst['gt_reading'])
                comp_to_count[comp] += 1

        # Find components that predict specific readings
        comp_hits = []
        for comp, count in comp_to_count.most_common(100):
            readings = comp_to_readings[comp]
            top_reading = max(readings, key=lambda r: sum(
                1 for i in kun_insts
                if comp in i['components'] and i['gt_reading'] == r
            ))
            top_count = sum(1 for i in kun_insts
                          if comp in i['components'] and i['gt_reading'] == top_reading)
            accuracy = top_count / count
            if count >= 3 and accuracy >= 0.5:
                kanjis_with = sorted(set(
                    i['kanji'] for i in kun_insts
                    if comp in i['components'] and i['gt_reading'] == top_reading
                ))
                comp_hits.append({
                    'component': comp, 'count': count,
                    'top_reading': top_reading, 'top_count': top_count,
                    'accuracy': round(accuracy * 100, 1),
                    'kanjis': kanjis_with,
                })

        comp_hits.sort(key=lambda x: -x['accuracy'] * x['count'])

        results[level] = {
            'N_kun': N_kun, 'N_all': N_all,
            'okurigana_constraints': oku_analysis,
            'radical_constraints': rad_analysis,
            'semantic_constraints': sem_analysis,
            'component_hits': comp_hits[:20],
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# APPROACH 2: Network Hubs-First (Topological Learning Order)
# ═══════════════════════════════════════════════════════════════════════════════

def explore_network_hubs(instances_by_level):
    """
    Instead of rules→stems→rote, build a kanji-level graph.
    Edge = shared stem, shared component, or compound co-occurrence.
    Learn central kanji first → their readings help predict neighbors.

    Cost model: learning kanji X's kun reading costs 1 unit.
    If X shares a stem with Y, learning Y costs 0.5 (similarity discount).
    Goal: find minimum-cost sequence covering all kun instances.
    """
    results = {}
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        all_insts = instances_by_level[level]
        kun_insts = [i for i in all_insts if i['gt_type'] == 'kun']

        # Build kanji→reading map (a kanji may have multiple kun readings)
        kanji_readings = defaultdict(set)
        kanji_instances = defaultdict(list)
        for i, inst in enumerate(kun_insts):
            kanji_readings[inst['kanji']].add(inst['gt_reading'])
            kanji_instances[inst['kanji']].append(i)

        unique_kanji = list(kanji_instances.keys())
        N_kun = len(kun_insts)

        # Build edges between kanji
        # Type 1: shared stem
        stem_kanji = defaultdict(set)
        for inst in kun_insts:
            stem_kanji[inst['gt_reading']].add(inst['kanji'])

        shared_stem_pairs = defaultdict(int)
        for stem, kanjis in stem_kanji.items():
            for k1, k2 in combinations(sorted(kanjis), 2):
                shared_stem_pairs[(k1, k2)] += 1

        # Type 2: co-occur in compound
        compound_pairs = defaultdict(int)
        for word in instances_by_level[level]:
            if word['gt_type'] != 'kun':
                continue
            word_kanjis = [i['kanji'] for i in instances_by_level[level]
                          if i.get('word') == word['word']]
        # Rebuild: group instances by word
        word_to_kanjis = defaultdict(set)
        for inst in all_insts:
            word_to_kanjis[inst['word']].add(inst['kanji'])
        for word, kanjis in word_to_kanjis.items():
            if len(kanjis) >= 2:
                for k1, k2 in combinations(sorted(kanjis), 2):
                    compound_pairs[(k1, k2)] += 1

        # Compute centrality: degree in the shared-stem graph
        degree = Counter()
        for (k1, k2), w in shared_stem_pairs.items():
            degree[k1] += w
            degree[k2] += w

        # Greedy learning order: pick highest-degree kanji, learn it,
        # discount its neighbors
        remaining = {k: set(kanji_readings[k]) for k in unique_kanji}
        learned_readings = {}  # kanji → learned reading
        learning_path = []
        total_cost = 0.0
        covered_instances = set()

        available = set(unique_kanji)
        while available:
            # Score each remaining kanji:
            # value = (uncovered instances) / (learning cost)
            # learning cost = 1.0 if no learned neighbor shares stem,
            #                 0.3 if learned neighbor shares stem
            best_k = None
            best_score = -1
            best_cost = 1.0

            for k in available:
                n_uncovered = sum(1 for idx in kanji_instances[k]
                                if idx not in covered_instances)
                if n_uncovered == 0:
                    continue

                # Check if any learned neighbor shares a stem
                discount = 1.0
                learned_stems = set()
                for lk, lr in learned_readings.items():
                    if (k, lk) in shared_stem_pairs or (lk, k) in shared_stem_pairs:
                        discount = min(discount, 0.3)

                cost = discount
                score = n_uncovered / cost
                if score > best_score:
                    best_score = score
                    best_k = k
                    best_cost = cost

            if best_k is None:
                break

            # "Learn" this kanji
            readings = kanji_readings[best_k]
            primary_reading = max(readings, key=lambda r: sum(
                1 for idx in kanji_instances[best_k]
                if kun_insts[idx]['gt_reading'] == r
            ))
            learned_readings[best_k] = primary_reading
            total_cost += best_cost

            new_covered = set(kanji_instances[best_k]) - covered_instances
            covered_instances |= set(kanji_instances[best_k])

            learning_path.append({
                'kanji': best_k, 'reading': primary_reading,
                'cost': round(best_cost, 1), 'new_instances': len(new_covered),
                'cum_cost': round(total_cost, 1),
                'cum_coverage': round(len(covered_instances) / N_kun * 100, 1),
                'degree': degree.get(best_k, 0),
                'all_readings': sorted(readings),
            })
            available.remove(best_k)

        # How many got the discount?
        discount_count = sum(1 for s in learning_path if s['cost'] < 1.0)
        results[level] = {
            'N_kun': N_kun,
            'N_unique_kanji': len(unique_kanji),
            'shared_stem_edges': len(shared_stem_pairs),
            'compound_edges': len(compound_pairs),
            'path': learning_path[:30],
            'total_cost': round(total_cost, 1),
            'discounted_kanji': discount_count,
            'discount_pct': round(discount_count / len(learning_path) * 100, 1)
            if learning_path else 0,
            'full_coverage_step': next((i for i, s in enumerate(learning_path)
                                       if s['cum_coverage'] >= 90), len(learning_path)),
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# APPROACH 3: Transitivity Pair Multiplier
# ═══════════════════════════════════════════════════════════════════════════════

def explore_transitivity(instances_by_level):
    """
    Transitivity pairs (自他動詞): 始める/始まる, 上げる/上がる, etc.
    If you know one, you can derive the other at ~zero cost.

    How many kun instances participate in transitivity pairs?
    What's the learning savings?
    """
    results = {}
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        kun_insts = [i for i in instances_by_level[level] if i['gt_type'] == 'kun']

        # Group by kanji to find all its readings
        kanji_oku = defaultdict(lambda: defaultdict(list))
        for inst in kun_insts:
            if inst['has_okuri']:
                kanji_oku[inst['kanji']][inst['okurigana']].append(inst)

        # Find transitivity patterns: same kanji with ～る/～れる vs ～す/～せる
        # Or complementary pairs across different kanji
        # Common patterns:
        # - ～まる/～める (高まる/高める)
        # - ～がる/～げる (上がる/上げる)
        # - ～く/～ける (開く/開ける)
        # - ～る/～す (出る/出す)

        trans_patterns = {
            ('まる', 'める'): '自動詞⇔他動詞',
            ('がる', 'げる'): '自動詞⇔他動詞',
            ('がる', 'がる'): '',  # skip same
            ('く', 'ける'): '自動詞⇔他動詞',
            ('る', 'す'): '自動詞⇔他動詞',
            ('れる', 'る'): '自発⇔他動詞',
            ('じる', 'ずる'): '一段⇔サ変',
            ('いる', 'える'): '自動詞⇔他動詞',
            ('まる', 'まる'): '',  # skip same
        }

        # Find ALL kanji where the same kanji appears with different okurigana
        # indicating a transitivity/intransitivity pair
        pairs_found = []
        covered_trans = set()  # kanji instances covered by transitivity logic

        for kanji, oku_map in kanji_oku.items():
            oku_list = sorted(oku_map.keys())
            for o1, o2 in combinations(oku_list, 2):
                for (p1, p2), label in trans_patterns.items():
                    if not label:
                        continue
                    if (o1.endswith(p1) and o2.endswith(p2)) or \
                       (o1.endswith(p2) and o2.endswith(p1)):
                        n1 = len(oku_map[o1])
                        n2 = len(oku_map[o2])
                        pairs_found.append({
                            'kanji': kanji,
                            'oku1': o1, 'oku2': o2,
                            'pattern': f'{p1}↔{p2}',
                            'instances': n1 + n2,
                            'free_savings': min(n1, n2),
                            'words1': [i['word'] for i in oku_map[o1][:3]],
                            'words2': [i['word'] for i in oku_map[o2][:3]],
                        })
                        for inst in oku_map[o1] + oku_map[o2]:
                            covered_trans.add(inst['word'] + inst['kanji'])

        pairs_found.sort(key=lambda p: -p['free_savings'])
        total_trans_instances = len(covered_trans)

        results[level] = {
            'N_kun': len(kun_insts),
            'trans_pairs': pairs_found[:20],
            'n_pairs': len(pairs_found),
            'total_trans_instances': total_trans_instances,
            'coverage_pct': round(total_trans_instances / len(kun_insts) * 100, 1)
            if kun_insts else 0,
            'potential_savings': sum(p['free_savings'] for p in pairs_found),
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# APPROACH 4: Okurigana-constrained Reading Candidates
# ═══════════════════════════════════════════════════════════════════════════════

def explore_okurigana_constraint(instances_by_level):
    """
    When you see a kanji followed by specific okurigana, how much does that
    narrow the candidate readings?

    E.g., if okurigana = 「める」, the reading probably ends in ～め.
    This gives you the vowel pattern even if you don't know the consonant.

    Quantify: for each okurigana suffix, what % of instances share the same
    reading ending?
    """
    results = {}
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        kun_insts = [i for i in instances_by_level[level] if i['gt_type'] == 'kun'
                    and i['has_okuri'] and i['okurigana']]

        # For each okurigana, find the most common reading suffix
        # "Reading suffix" = last 1-2 mora of the gt_reading
        oku_reading_suffix = defaultdict(Counter)
        for inst in kun_insts:
            oku = inst['okurigana']
            r = inst['gt_reading']
            # Get last 1-2 kana as the reading ending
            if len(r) >= 2:
                oku_reading_suffix[oku][r[-2:]] += 1
            oku_reading_suffix[oku][r[-1]] += 1

        # Filter to okurigana with high consistency
        strong_hints = []
        for oku, suffix_counter in oku_reading_suffix.items():
            total = sum(suffix_counter.values())
            if total < 2:
                continue
            top_suffix, top_count = suffix_counter.most_common(1)[0]
            accuracy = top_count / total
            if accuracy >= 0.6 and total >= 3:
                strong_hints.append({
                    'okurigana': oku,
                    'total': total,
                    'predicts_reading_ending': top_suffix,
                    'accuracy': round(accuracy * 100, 1),
                })

        strong_hints.sort(key=lambda h: -h['accuracy'] * h['total'])

        # Aggregate: how many kun instances get useful constraint from okurigana?
        constrained_count = 0
        for inst in instances_by_level[level]:
            if inst['gt_type'] != 'kun' or not inst['has_okuri']:
                continue
            for hint in strong_hints:
                if inst['okurigana'] == hint['okurigana']:
                    constrained_count += 1
                    break

        results[level] = {
            'N_kun': sum(1 for i in instances_by_level[level] if i['gt_type'] == 'kun'),
            'N_with_okuri': len(kun_insts),
            'strong_hints': strong_hints[:15],
            'constrained_count': constrained_count,
            'constrained_pct': round(constrained_count / max(len(kun_insts), 1) * 100, 1),
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# APPROACH 5: Compound Co-occurrence Constraint
# ═══════════════════════════════════════════════════════════════════════════════

def explore_compound_constraint(instances_by_level):
    """
    When a multi-kanji word has BOTH kanji read kun, does knowing one
    constrain the other?

    Key insight from gold_panning: multi-kanji kun words often follow a
    pattern like "noun+verb" or "adj+noun". If you know the first kanji's
    reading class, you can predict the second's.
    """
    results = {}
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        all_insts = instances_by_level[level]

        # Group instances by word
        word_insts = defaultdict(list)
        for i, inst in enumerate(all_insts):
            word_insts[inst['word']].append(i)

        # Find words where multiple kanji have kun readings
        multi_kun_words = []
        for word, idxs in word_insts.items():
            insts_in_word = [all_insts[idx] for idx in idxs]
            kun_in_word = [i for i in insts_in_word if i['gt_type'] == 'kun']
            if len(kun_in_word) >= 2:
                # Check: do any share the same reading?
                readings = [i['gt_reading'] for i in kun_in_word]
                if len(set(readings)) < len(readings):
                    multi_kun_words.append({
                        'word': word,
                        'kanjis': [(i['kanji'], i['gt_reading']) for i in kun_in_word],
                        'shared_readings': [r for r, c in Counter(readings).items() if c > 1],
                        'n_kun': len(kun_in_word),
                    })

        # More interesting: in a 2-kanji kun word, if we know first kanji's reading,
        # does it predict second kanji's reading TYPE?
        cross_constraints = []
        for word, idxs in word_insts.items():
            insts_in_word = [all_insts[idx] for idx in idxs]
            if len(insts_in_word) != 2:
                continue
            k1, k2 = insts_in_word[0], insts_in_word[1]
            if k1['gt_type'] == 'kun' and k2['gt_type'] == 'kun':
                # Both kun — does this happen consistently for certain patterns?
                pass

        # Instead: group 2-kanji words by first kanji's reading type
        # See if that predicts second kanji's reading type
        type_patterns = defaultdict(lambda: {'total': 0, 'on_kun': [0, 0], 'on_on': [0, 0], 'kun_on': [0, 0], 'kun_kun': [0, 0]})
        for word, idxs in word_insts.items():
            insts_in_word = [all_insts[idx] for idx in idxs]
            if len(insts_in_word) != 2:
                continue
            t1, t2 = insts_in_word[0]['gt_type'], insts_in_word[1]['gt_type']
            key = f'{t1}+{t2}'
            for t in type_patterns.values():
                t[key] = t.get(key, 0)

        # Count the 4 combinations
        combo_count = Counter()
        for word, idxs in word_insts.items():
            insts_in_word = [all_insts[idx] for idx in idxs]
            if len(insts_in_word) != 2:
                continue
            t1, t2 = insts_in_word[0]['gt_type'], insts_in_word[1]['gt_type']
            combo_count[f'{t1}+{t2}'] += 1

        total_2kanji = sum(combo_count.values())
        results[level] = {
            'N_all': len(all_insts),
            'multi_kun_words': multi_kun_words[:15],
            'n_multi_kun_words': len(multi_kun_words),
            'combo_counts': dict(combo_count),
            'total_2kanji_words': total_2kanji,
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# APPROACH 6: Reading→Kanji Reverse Index (for listening)
# ═══════════════════════════════════════════════════════════════════════════════

def explore_reverse_index(instances_by_level):
    """
    Instead of "given kanji, predict reading", consider:
    "given reading X, which kanji could it be?"

    This is useful for listening comprehension and for learning: if you
    hear 「かんがえる」, you know the reading. The question is which kanji.
    Group kanji by shared reading → learn them as a cluster.
    """
    results = {}
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        kun_insts = [i for i in instances_by_level[level] if i['gt_type'] == 'kun']

        reading_kanji = defaultdict(lambda: {'kanjis': set(), 'count': 0, 'words': []})
        for inst in kun_insts:
            r = inst['gt_reading']
            reading_kanji[r]['kanjis'].add(inst['kanji'])
            reading_kanji[r]['count'] += 1
            if len(reading_kanji[r]['words']) < 3:
                reading_kanji[r]['words'].append(inst['word'])

        # Readings that map to multiple kanji are "high value" to learn
        # because one reading unlocks multiple kanji (for listening)
        high_value = [
            {'reading': r, 'kanjis': sorted(d['kanjis']), 'count': d['count'],
             'example_words': d['words']}
            for r, d in reading_kanji.items()
            if len(d['kanjis']) >= 2
        ]
        high_value.sort(key=lambda x: -x['count'])

        # Stats
        single_kanji_readings = sum(1 for r, d in reading_kanji.items()
                                    if len(d['kanjis']) == 1)
        multi_kanji_readings = sum(1 for r, d in reading_kanji.items()
                                   if len(d['kanjis']) >= 2)

        results[level] = {
            'N_kun': len(kun_insts),
            'unique_readings': len(reading_kanji),
            'single_kanji_readings': single_kanji_readings,
            'multi_kanji_readings': multi_kanji_readings,
            'multi_pct': round(multi_kanji_readings / len(reading_kanji) * 100, 1),
            'high_value_clusters': high_value[:20],
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_report(dt, net, trans, oku, compound, reverse_idx):
    lines = []
    w = lines.append

    w('# 训读替代学习路径探索')
    w('')
    w('> 探索多种根本不同的学习路径，寻找比贪心集合覆盖更高效的策略。')
    w('')
    w(f'*生成时间：2026-05-07*')
    w('')
    w('---')
    w('')

    # ── 1. Decision Tree ──
    w('## 1. 决策树分支（最小熵）')
    w('')
    w('核心问题：把kun实例区分出来后，什么特征最能"缩小候选读法范围"？')
    w('')
    w('### 1a. 送假名约束力')
    w('')
    w('送假名出现时，把读法可能的数量从几百个缩小到小个位数：')
    w('')

    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = dt[level]
        w(f'**{level}** ({d["N_kun"]} kun实例)')
        w('')
        if d['okurigana_constraints']:
            w('| 送假名 | 出现次数 | 约束后的读法数 | 覆盖kun% | 候选读法 |')
            w('|--------|---------|-------------|---------|---------|')
            for h in d['okurigana_constraints'][:10]:
                readings_str = ', '.join(h['readings'][:5])
                w(f'| {h["okurigana"]} | {h["count"]} | {h["unique_readings"]} | {h["coverage_pct"]}% | {readings_str} |')
        w('')

    w('### 1b. 部首约束力')
    w('')
    w('部首对读法的约束有多强？"每个部首对应平均X个读法"：')
    w('')
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = dt[level]
        if d['radical_constraints']:
            avg_entropy = sum(r['unique_readings'] for r in d['radical_constraints']) / len(d['radical_constraints'])
            avg_count = sum(r['count'] for r in d['radical_constraints']) / len(d['radical_constraints'])
            w(f'**{level}**: {len(d["radical_constraints"])} 个部首，平均每部首 {avg_entropy:.1f} 种读法 / {avg_count:.1f} 个实例。')
            w('')
            w('| 部首 | 实例数 | 读法种类 | 覆盖率 | 效率(读法/实例) |')
            w('|------|--------|---------|--------|---------------|')
            for r in d['radical_constraints'][:8]:
                w(f'| {r["radical"]} | {r["count"]} | {r["unique_readings"]} | {r["coverage_pct"]}% | {r["entropy_per_instance"]}% |')
        w('')

    w('### 1c. 部件→读法直接映射')
    w('')
    w('是否存在"看到某个部件就能猜出读法"的模式？（类似形声字的声旁，但是训读版）')
    w('')
    has_any = False
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = dt[level]
        if d['component_hits']:
            has_any = True
            w(f'**{level}**:')
            w('')
            w('| 部件 | 出现次数 | 预测读法 | 命中数 | 准确率 | 涉及的汉字 |')
            w('|------|---------|---------|--------|--------|-----------|')
            for h in d['component_hits'][:10]:
                w(f'| {h["component"]} | {h["count"]} | {h["top_reading"]} | {h["top_count"]} | {h["accuracy"]}% | {",".join(h["kanjis"][:8])} |')
            w('')
    if not has_any:
        w('*未发现满足条件（count≥3, accuracy≥50%）的部件映射。*')
        w('')

    w('---')
    w('')

    # ── 2. Network Hubs ──
    w('## 2. 网络中心度优先学习')
    w('')
    w('策略：先学"连接最多其他汉字"的核心汉字，利用共享词干的关系以折扣价学会邻居。')
    w('')
    w('折扣规则：如果待学汉字与已学汉字共享词干，学习成本从1降至0.3。')
    w('')
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = net[level]
        w(f'**{level}**: {d["N_unique_kanji"]} 个不同汉字, {d["N_kun"]} kun实例, '
          f'{d["shared_stem_edges"]} 条共享词干边, {d["compound_edges"]} 条复合词共现边')
        w(f'')
        w(f'- 总学习成本: {d["total_cost"]} (vs 全部死记={d["N_unique_kanji"]})')
        w(f'- 获折扣的汉字: {d["discounted_kanji"]} / {len(d.get("path", []))} ({d["discount_pct"]}%)')
        w(f'- 达到90%覆盖的步数: {d["full_coverage_step"]}')
        w('')
        if d.get('path'):
            w('| 顺序 | 汉字 | 读法 | 成本 | 累计成本 | 新增实例 | 累计覆盖 | 中心度 |')
            w('|------|------|------|------|---------|---------|---------|--------|')
            for s in d['path'][:15]:
                w(f'| {d["path"].index(s)+1} | {s["kanji"]} | {s["reading"]} | {s["cost"]} | {s["cum_cost"]} | +{s["new_instances"]} | {s["cum_coverage"]}% | {s["degree"]} |')
        w('')

    w('---')
    w('')

    # ── 3. Transitivity ──
    w('## 3. 自他动词对 — 学一带一')
    w('')
    w('同一个汉字带不同的送假名形成自动词/他动词对。学会一个，另一个几乎免费。')
    w('')
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = trans[level]
        w(f'**{level}**: {d["n_pairs"]} 对, 覆盖 {d["coverage_pct"]}% kun实例, '
          f'潜在节省 {d["potential_savings"]} 个记忆单位')
        w('')
        if d['trans_pairs']:
            w('| 汉字 | 送假名1 | 送假名2 | 模式 | 实例数 | 节省 | 例词 |')
            w('|------|---------|---------|------|--------|------|------|')
            for p in d['trans_pairs'][:10]:
                w(f'| {p["kanji"]} | {p["oku1"]} | {p["oku2"]} | {p["pattern"]} | {p["instances"]} | {p["free_savings"]} | {",".join(p["words1"][:2])} / {",".join(p["words2"][:2])} |')
        w('')

    w('---')
    w('')

    # ── 4. Okurigana Constraint ──
    w('## 4. 送假名作为读法锚点')
    w('')
    w('特定送假名高度预测读法结尾。例如看到「～める」大概率读法以「め」结尾。')
    w('')
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = oku[level]
        w(f'**{level}**: {d["N_with_okuri"]} kun带送假名实例, '
          f'{d["constrained_count"]} ({d["constrained_pct"]}%) 可被强约束')
        w('')
        if d['strong_hints']:
            w('| 送假名 | 出现次数 | 预测读法结尾 | 准确率 |')
            w('|--------|---------|------------|--------|')
            for h in d['strong_hints'][:10]:
                w(f'| {h["okurigana"]} | {h["total"]} | ～{h["predicts_reading_ending"]} | {h["accuracy"]}% |')
        w('')

    w('---')
    w('')

    # ── 5. Compound Constraint ──
    w('## 5. 复合词中的互约束')
    w('')
    w('多汉字词中，已知汉字的音训类型是否约束未知汉字？')
    w('')
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = compound[level]
        if d['total_2kanji_words']:
            combos = d['combo_counts']
            w(f'**{level}**: {d["total_2kanji_words"]} 个二汉字词')
            w('')
            w('| 组合 | 数量 | 占比 |')
            w('|------|------|------|')
            for combo in ['on+on', 'on+kun', 'kun+on', 'kun+kun']:
                count = combos.get(combo, 0)
                pct = round(count / d['total_2kanji_words'] * 100, 1) if d['total_2kanji_words'] else 0
                w(f'| {combo} | {count} | {pct}% |')
            w('')
            w(f'多kun共现词: {d["n_multi_kun_words"]} 个')
            if d['multi_kun_words']:
                w('')
                w('| 词 | 汉字(读法) | 共享读法 |')
                w('|----|-----------|---------|')
                for mw in d['multi_kun_words'][:8]:
                    kanjis_str = ', '.join(f'{k}({r})' for k, r in mw['kanjis'])
                    shared = ', '.join(mw['shared_readings']) if mw['shared_readings'] else '-'
                    w(f'| {mw["word"]} | {kanjis_str} | {shared} |')
        w('')

    w('---')
    w('')

    # ── 6. Reverse Index ──
    w('## 6. 反向索引 — 从读法出发')
    w('')
    w('策略逆转：不是"看到汉字猜读法"，而是"学会一个读法→同时解锁多个汉字"。')
    w('这对应听力场景——听到读音后判断是哪个字。')
    w('')
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = reverse_idx[level]
        w(f'**{level}**: {d["unique_readings"]} 个独特读法, '
          f'{d["multi_kanji_readings"]} ({d["multi_pct"]}%) 对应多个汉字')
        w('')
        if d['high_value_clusters']:
            w('| 读法 | 对应汉字 | 实例数 | 例词 |')
            w('|------|---------|--------|------|')
            for h in d['high_value_clusters'][:12]:
                kanjis_str = ', '.join(h['kanjis'][:6])
                words_str = ', '.join(h['example_words'][:3])
                w(f'| {h["reading"]} | {kanjis_str} | {h["count"]} | {words_str} |')
        w('')

    w('---')
    w('')

    # ── Synthesis ──
    w('## 7. 综合对比：不同路径的性价比')
    w('')
    w('把所有路径放到一张表里对比（以N3为例）：')
    w('')
    level = 'N3'

    # Collect stats
    dt_d = dt[level]
    net_d = net[level]
    trans_d = trans[level]
    oku_d = oku[level]

    w('| 方法 | 覆盖范围 | 覆盖kun% | 前提成本 | 核心优势 | 核心限制 |')
    w('|------|---------|---------|---------|---------|---------|')
    w(f'| **贪心集合覆盖** (原方案) | 音训判断 | 91.5% | 6 | 成本极低，覆盖极高 | 只能判断音vs训 |')
    w(f'| **贪心集合覆盖** (原方案) | 词干推导 | 7.3% | 134 | 能推导具体读法 | 成本极高，覆盖极低 |')
    w(f'| **决策树-送假名约束** | kun读法缩小 | {sum(h["coverage_pct"] for h in dt_d["okurigana_constraints"][:5]):.0f}% | 0 | 把读法候选从几百缩到个位数 | 不能确定唯一读法 |')
    c_hit = sum(h['count'] * h['accuracy'] / 100 for h in dt_d['component_hits'][:10]) if dt_d['component_hits'] else 0
    w(f'| **部件→读法映射** | 特定汉字 | ~{c_hit:.0f}实例 | 低 | 看到部件就能猜读法 | 覆盖面小，准确率不稳定 |')
    w(f'| **网络中心度优先** | 全部kun | {net_d.get("path", [{}])[-1].get("cum_coverage", 0) if net_d.get("path") else 0}% | {net_d.get("total_cost", "?")} | 利用共享词干降低邻居学习成本 | 共享词干比例低 |')
    w(f'| **自他动词对** | 带送假名动词 | {trans_d["coverage_pct"]}% | 0 | 学一带一，接近免费 | 只适用于动词对 |')
    w(f'| **送假名锚点** | kun+送假名 | {oku_d["constrained_pct"]}% | 0 | 缩小读法候选空间 | 不能唯一确定 |')
    w('')

    w('### 关键发现')
    w('')
    w('1. **不存在"读法推导捷径"** — 部件、部首、语义域都无法以高准确率预测具体训读词干。')
    w('   训读的本质是：每个汉字的训读是历史上"硬赋值"的，不是能从属性推导的。')
    w('')
    w('2. **但存在"学习效率杠杆"** — 以下杠杆不预测读法，但降低记忆成本：')
    w('   - 送假名约束（免费，缩小候选空间）')
    w('   - 自他动词对（免费，学一带一）')
    w('   - 网络共享词干（低成本，邻字折扣）')
    w('   - 反向聚类（先学读法对应多字的，减少后续学习成本）')
    w('')
    w('3. **最优路径应该是混合策略**：')
    w('   - **第0层**（零成本，纯观察）：送假名约束 + 自他对识别 → 缩小候选空间')
    w('   - **第1层**（成本1-6，规则）：音训判断 + 词类判断 → 覆盖91%分类')
    w('   - **第2层**（成本1-4，词干家族）：高频共享词干 → 一个读法解锁多字')
    w('   - **第3层**（妥协层，死记）：剩余按反向聚类（多字共享一个读法的优先记）')
    w('')
    w('4. **最被低估的杠杆是反向聚类**：')
    w(f'   以N3为例，{reverse_idx[level]["multi_pct"]}%的训读读法对应≥2个汉字。')
    w('   学会读法「もの」→解锁物,者。学会读法「あ」→解锁上,会,合,揚...')
    w('   这在"听力→书写"方向是真正的免费午餐。')
    w('')

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("Loading data...")
    v9_data = load_v9()
    kanji_db = load_kanji_db(KANJI_DB_PATH)
    print(f"  V9: {len(v9_data['annotated_words'])} words")
    print(f"  DB: {len(kanji_db)} kanji")

    print("Building instances...")
    instances_by_level = build_instances(v9_data, kanji_db)
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        n = len(instances_by_level[level])
        n_kun = sum(1 for i in instances_by_level[level] if i['gt_type'] == 'kun')
        print(f"  {level}: {n} total, {n_kun} kun")

    print("\n=== Approach 1: Decision Tree ===")
    dt_results = explore_decision_tree(instances_by_level)
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = dt_results[level]
        print(f"  {level}: {len(d['okurigana_constraints'])} okurigana constraints, "
              f"{len(d['component_hits'])} component→reading mappings")

    print("\n=== Approach 2: Network Hubs-First ===")
    net_results = explore_network_hubs(instances_by_level)
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = net_results[level]
        print(f"  {level}: {d['N_unique_kanji']} kanji, cost={d['total_cost']}, "
              f"{d['discounted_kanji']} discounted ({d['discount_pct']}%)")

    print("\n=== Approach 3: Transitivity Pairs ===")
    trans_results = explore_transitivity(instances_by_level)
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = trans_results[level]
        print(f"  {level}: {d['n_pairs']} pairs, coverage={d['coverage_pct']}%, "
              f"savings={d['potential_savings']}")

    print("\n=== Approach 4: Okurigana Constraint ===")
    oku_results = explore_okurigana_constraint(instances_by_level)
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = oku_results[level]
        print(f"  {level}: {len(d['strong_hints'])} strong hints, "
              f"constrains {d['constrained_pct']}% of okurigana instances")

    print("\n=== Approach 5: Compound Constraint ===")
    compound_results = explore_compound_constraint(instances_by_level)

    print("\n=== Approach 6: Reverse Index ===")
    reverse_results = explore_reverse_index(instances_by_level)
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        d = reverse_results[level]
        print(f"  {level}: {d['unique_readings']} unique readings, "
              f"{d['multi_pct']}% multi-kanji")

    print("\nGenerating report...")
    report = generate_report(dt_results, net_results, trans_results,
                            oku_results, compound_results, reverse_results)
    with open(OUT_MD, 'w') as f:
        f.write(report)
    print(f"  -> {OUT_MD} ({len(report)} chars)")
    print("\nDone!")


if __name__ == '__main__':
    main()
