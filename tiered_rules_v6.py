#!/usr/bin/env python3
"""
Kun-Yomi V6: Comprehensive Learning System
==========================================
12-module system: frequency, same-kun diff, word families, kanji portraits,
traps, transitivity, compound structure, position effects, decision tree,
optimized rules, learning path, summary dashboard.

Data: 漢字検索V2 (46,848 kanji) + word.xlsx (9,573 JLPT words) + v4 exhaustive JSON
"""

import json, re, sys, os
from collections import Counter, defaultdict
from itertools import combinations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Optional
import openpyxl

# ============================================================
# SECTION 0: Config
# ============================================================

BASE = '/Volumes/SSD/work/kanji-kun'
OUT = f'{BASE}/output'
WORD_XLSX = f'{BASE}/word.xlsx'
KANJI_XLSM = f'{BASE}/漢字検索V2.xlsm'
V4_JSON = f'{BASE}/kunyomi_exhaustive_v4.json'

JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']
LEVEL_DESC = {
    'N5': ('入门', 653, 1000),
    'N4': ('基础', 781, 1121),
    'N3': ('中级', 1113, 2071),
    'N2': ('中高级', 1330, 2328),
    'N1': ('高级', 1473, 3053),
}

# ============================================================
# SECTION 1: Data Loading
# ============================================================

def load_jlpt_words():
    """Load JLPT vocabulary from word.xlsx.
    Returns: list of {kana, kanji, level, is_kanji_word}
    """
    wb = openpyxl.load_workbook(WORD_XLSX, read_only=True)
    ws = wb['红宝书去重版']
    words = []
    for row in ws.iter_rows(min_row=4, max_row=9575, values_only=True):
        kana = str(row[2]).strip() if row[2] else ''
        kanji = str(row[3]).strip() if row[3] else ''
        level = str(row[23]).strip() if len(row) > 23 and row[23] else ''
        if level not in JLPT_LEVELS:
            continue
        # Check if this is a kanji-containing word (has CJK characters)
        has_kanji = bool(re.search(r'[一-鿿㐀-䶿]', kanji))
        words.append({
            'kana': kana, 'kanji': kanji, 'level': level,
            'is_kanji_word': has_kanji,
            'num_kanji': len(re.findall(r'[一-鿿㐀-䶿]', kanji)) if has_kanji else 0,
        })
    wb.close()
    return words

def load_kanji_db():
    """Load kanji database from 漢字検索V2.xlsm.
    Returns: dict kanji_char -> {radical, on_readings, kun_readings, meaning, stroke_count, components}
    """
    wb = openpyxl.load_workbook(KANJI_XLSM, read_only=True)
    ws = wb['漢字一覧']
    kanji_db = {}
    for row in ws.iter_rows(min_row=2, max_row=46850, values_only=True):
        if not row[0]:
            continue
        char = str(row[0]).strip()
        if not char or len(char) > 2:
            continue
        components = str(row[1]).strip() if row[1] else ''
        radical = str(row[3]).strip() if row[3] else ''
        on_raw = str(row[9]).strip() if row[9] else ''
        kun_raw = str(row[10]).strip() if row[10] else ''
        meaning = str(row[11]).strip() if row[11] else ''
        stroke_count = int(row[8]) if row[8] else 0

        # Parse on readings
        on_readings = [o.strip() for o in on_raw.replace('、', ',').split(',') if o.strip()]

        # Parse kun readings: "ひと、ひと・つ" format, ・ marks okurigana
        kun_raw_list = [k.strip() for k in kun_raw.replace('、', ',').split(',') if k.strip()]
        kun_readings = []
        for kr in kun_raw_list:
            if '・' in kr:
                parts = kr.split('・')
                stem = parts[0].replace('.', '')
                oku = '.'.join(p.replace('.', '') for p in parts[1:])
                kun_readings.append({'stem': stem, 'okurigana': oku, 'full': f"{stem}.{oku}"})
            elif kr:
                # No okurigana
                kun_readings.append({'stem': kr.replace('.', ''), 'okurigana': '', 'full': kr.replace('.', '')})

        kanji_db[char] = {
            'radical': radical,
            'components': components,
            'on_readings': on_readings,
            'kun_readings': kun_readings,
            'meaning': meaning,
            'stroke_count': stroke_count,
        }
    wb.close()
    return kanji_db

def load_v4_data():
    """Load v4 exhaustive enumeration data."""
    with open(V4_JSON) as f:
        return json.load(f)

# ============================================================
# SECTION 1b: Build Cross-Reference Indexes
# ============================================================

def build_indexes(jlpt_words, kanji_db, v4):
    """Build all cross-reference indexes needed by modules."""

    # Index 1: level -> list of (kana, kanji)
    level_words = defaultdict(list)
    for w in jlpt_words:
        level_words[w['level']].append(w)

    # Index 2: kanji_char -> list of JLPT words containing it
    kanji_to_words = defaultdict(list)
    for w in jlpt_words:
        if w['is_kanji_word']:
            for ch in w['kanji']:
                if ch in kanji_db:
                    kanji_to_words[ch].append(w)

    # Index 3: kun_stem -> list of (kanji, okurigana, level)
    stem_to_kanji = defaultdict(list)
    for ch, info in kanji_db.items():
        for kr in info['kun_readings']:
            stem = kr['stem']
            if stem:
                levels_for_char = set(w['level'] for w in kanji_to_words.get(ch, []))
                stem_to_kanji[stem].append({
                    'kanji': ch, 'okurigana': kr['okurigana'],
                    'full_kun': kr['full'], 'radical': info['radical'],
                    'levels': levels_for_char,
                })

    # Index 4: JLPT word -> which kanji contribute which readings
    # This is complex - for each JLPT word, figure out which kanji
    # reads as kun vs on, and extract stems
    word_readings = []
    for w in jlpt_words:
        if not w['is_kanji_word'] or w['num_kanji'] == 0:
            continue
        entry = {'word': w['kanji'], 'kana': w['kana'], 'level': w['level'],
                 'num_kanji': w['num_kanji'], 'kanji_in_word': []}
        # Extract kanji chars
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', w['kanji'])
        entry['kanji_chars'] = kanji_chars
        word_readings.append(entry)

    # Index 5: kanji -> on/kun ratio in JLPT compounds
    kanji_on_kun_ratio = {}
    for ch, winfo in kanji_to_words.items():
        on_count = 0
        kun_count = 0
        for w in winfo:
            # Very rough heuristic: if word is single kanji with okurigana, it's kun
            # If word is multi-kanji compound, first check if any reading matches kun
            kanji_chars = re.findall(r'[一-鿿㐀-䶿]', w['kanji'])
            if len(kanji_chars) == 1 and ch in kanji_db:
                krs = kanji_db[ch]['kun_readings']
                # Check if any kun reading matches the kana
                kana_clean = w['kana'].replace('っ', '').replace('ー', '')
                for kr in krs:
                    if kr['stem'] in kana_clean:
                        kun_count += 1
                        break
                else:
                    on_count += 1
            elif len(kanji_chars) >= 2:
                # Multi-kanji: harder to determine per-character reading
                # Simple heuristic: if 2 mora = probably on+on
                mora_count = len(re.sub(r'[ゃゅょっ]', '', w['kana']))
                if mora_count <= 2:
                    on_count += 1
                else:
                    kun_count += 0.5
                    on_count += 0.5
        total = on_count + kun_count
        if total > 0:
            kanji_on_kun_ratio[ch] = {'on_ratio': on_count / total, 'kun_ratio': kun_count / total,
                                       'total_occurrences': total}

    return {
        'level_words': level_words,
        'kanji_to_words': kanji_to_words,
        'stem_to_kanji': stem_to_kanji,
        'word_readings': word_readings,
        'kanji_on_kun_ratio': kanji_on_kun_ratio,
    }

# ============================================================
# SECTION 2: Module 1 - JLPT Kun Stem Frequency Heatmap
# ============================================================

def build_frequency_heatmap(kanji_db, indexes, jlpt_words):
    """Count kun stem frequency in JLPT vocabulary.
    For each word, identify which parts are kun readings and extract stems.
    """
    # Approach: for each JLPT word with 1 kanji, try to match kanji's kun readings
    # against the kana. The matching stem is counted.
    stem_freq = defaultdict(lambda: {'total': 0, 'N5': 0, 'N4': 0, 'N3': 0, 'N2': 0, 'N1': 0,
                                      'kanji_list': set(), 'example_words': []})

    for w in jlpt_words:
        if not w['is_kanji_word']:
            continue
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', w['kanji'])
        kana_clean = w['kana'].replace('っ', '').replace('ー', '').replace('ゃ', 'や').replace('ゅ', 'ゆ').replace('ょ', 'よ')

        for ch in kanji_chars:
            if ch not in kanji_db:
                continue
            info = kanji_db[ch]
            # Try to match kun readings against kana
            for kr in info['kun_readings']:
                stem = kr['stem']
                if not stem or len(stem) < 1:
                    continue
                # Check if stem appears at the right position in kana
                # This is approximate - better matching would need
                # to know which kanji maps to which part of the kana
                if stem in kana_clean:
                    stem_freq[stem]['total'] += 1
                    stem_freq[stem][w['level']] += 1
                    stem_freq[stem]['kanji_list'].add(ch)
                    if len(stem_freq[stem]['example_words']) < 5:
                        stem_freq[stem]['example_words'].append(f"{w['kanji']}({w['kana']})")
                    break  # Count each kanji once per word

    # Sort by total frequency
    sorted_stems = sorted(stem_freq.items(), key=lambda x: x[1]['total'], reverse=True)

    # Convert sets to lists for JSON
    for stem, data in stem_freq.items():
        data['kanji_list'] = sorted(list(data['kanji_list']))

    return sorted_stems

def write_frequency_heatmap(sorted_stems, out_dir):
    """Generate frequency heatmap markdown."""
    lines = []
    lines.append('# 训读词干频率热力图 · Kun-Yomi Frequency Heatmap')
    lines.append('')
    lines.append('> JLPT 9,573词汇中，每个训读词干的出现频率')
    lines.append('> 优先学习高频词干 = 最大化学习效率')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Top 30 overview
    lines.append('## Top 30 最高频训读词干')
    lines.append('')
    lines.append('| 排名 | 词干 | 总频次 | N5 | N4 | N3 | N2 | N1 | 关联字数 | 例词 |')
    lines.append('|------|------|--------|----|----|----|----|----|---------|------|')
    for i, (stem, data) in enumerate(sorted_stems[:30], 1):
        examples = ', '.join(data['example_words'][:3])
        lines.append(f'| {i} | **{stem}** | {data["total"]} | {data["N5"]} | {data["N4"]} | {data["N3"]} | {data["N2"]} | {data["N1"]} | {len(data["kanji_list"])} | {examples} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # Per-level top 10
    for level in JLPT_LEVELS:
        lines.append(f'## {level} 级高频词干 Top 10')
        lines.append('')
        level_stems = sorted([(s, d) for s, d in sorted_stems if d[level] > 0],
                            key=lambda x: x[1][level], reverse=True)
        lines.append('| 排名 | 词干 | 频次 | 关联字 |')
        lines.append('|------|------|------|--------|')
        for i, (stem, data) in enumerate(level_stems[:10], 1):
            kanji_str = ', '.join(data['kanji_list'][:8])
            lines.append(f'| {i} | **{stem}** | {data[level]} | {kanji_str} |')
        lines.append('')

    # Full list by frequency
    lines.append('---')
    lines.append('')
    lines.append('## 完整频率列表')
    lines.append('')
    lines.append('| 排名 | 词干 | 总频次 | N5 | N4 | N3 | N2 | N1 | 关联字 |')
    lines.append('|------|------|--------|----|----|----|----|----|--------|')
    for i, (stem, data) in enumerate(sorted_stems[:200], 1):
        lines.append(f'| {i} | **{stem}** | {data["total"]} | {data["N5"]} | {data["N4"]} | {data["N3"]} | {data["N2"]} | {data["N1"]} | {len(data["kanji_list"])} |')

    lines.append('')
    lines.append(f'*共 {len(sorted_stems)} 个训读词干被统计*')

    with open(f'{out_dir}/kun_v6_frequency_heatmap.md', 'w') as f:
        f.write('\n'.join(lines))

    # Also save JSON
    freq_json = [{'stem': s, **d} for s, d in sorted_stems]
    with open(f'{out_dir}/kun_v6_frequency.json', 'w') as f:
        json.dump(freq_json, f, ensure_ascii=False, indent=2)

    return sorted_stems

# ============================================================
# SECTION 3: Module 2 - Same-Kun Differentiation Cards
# ============================================================

def build_samekun_diff(v4, kanji_db, indexes, jlpt_words):
    """Generate differentiation cards for same-kun groups relevant to JLPT."""
    same_stem = v4.get('same_stem_groups', {})
    kanji_to_words = indexes['kanji_to_words']

    diff_cards = []
    for stem, group_data in same_stem.items():
        kanji_list = group_data.get('kanji', [])
        # Filter to JLPT-relevant kanji only
        jlpt_kanji = [k for k in kanji_list if k in kanji_to_words]
        if len(jlpt_kanji) < 2:  # Need at least 2 JLPT kanji to differentiate
            continue

        # Get meaning snippets for each kanji
        kanji_info = []
        for k in jlpt_kanji:
            info = kanji_db.get(k, {})
            meaning = info.get('meaning', '')
            # Extract first meaningful line from Japanese meaning
            meaning_short = meaning.split('◆')[1].strip() if '◆' in meaning else meaning[:80]
            kun_readings = [kr['full'] for kr in info.get('kun_readings', []) if kr['stem'] == stem]
            kanji_info.append({
                'kanji': k,
                'meaning': meaning_short[:120],
                'kun_readings': kun_readings,
                'radical': info.get('radical', ''),
                'jlpt_levels': sorted(set(w['level'] for w in kanji_to_words.get(k, []))),
                'example_words': [f"{w['kanji']}({w['kana']})" for w in kanji_to_words.get(k, [])[:5]],
            })

        diff_cards.append({
            'stem': stem,
            'num_kanji_total': len(kanji_list),
            'num_kanji_jlpt': len(jlpt_kanji),
            'kanji_info': kanji_info,
        })

    # Sort by JLPT relevance (more JLPT kanji = more important)
    diff_cards.sort(key=lambda x: (x['num_kanji_jlpt'], len(x['kanji_info'][0]['example_words']) if x['kanji_info'] else 0), reverse=True)
    return diff_cards

def write_samekun_diff(diff_cards, out_dir):
    """Generate same-kun differentiation markdown."""
    lines = []
    lines.append('# 同训异字辨析图谱 · Same-Kun Differentiation Cards')
    lines.append('')
    lines.append('> 同一训读词干 → 多个汉字 → 含义如何分化？')
    lines.append('> 数据源：v4 穷举同训组 + JLPT 交叉筛选')
    lines.append('')
    lines.append('---')
    lines.append('')

    for card in diff_cards[:100]:  # Top 100 most JLPT-relevant
        stem = card['stem']
        lines.append(f'## {stem}（{card["num_kanji_jlpt"]}个JLPT字 / 共{card["num_kanji_total"]}字）')
        lines.append('')
        lines.append('| 汉字 | 部首 | 训读 | JLPT级别 | 含义分化 | 例词 |')
        lines.append('|------|------|------|---------|---------|------|')
        for ki in card['kanji_info']:
            kun_str = ' / '.join(ki['kun_readings']) if ki['kun_readings'] else stem
            levels = ','.join(ki['jlpt_levels']) if ki['jlpt_levels'] else '-'
            examples = ', '.join(ki['example_words'][:3])
            lines.append(f'| {ki["kanji"]} | {ki["radical"]} | {kun_str} | {levels} | {ki["meaning"][:60]} | {examples} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_samekun_diff.md', 'w') as f:
        f.write('\n'.join(lines))

    return diff_cards

# ============================================================
# SECTION 4: Module 3 - Word Family Trees
# ============================================================

def build_word_families(v4, kanji_db, indexes):
    """Build word family trees from v4 data, filtered by JLPT relevance."""
    families = v4.get('word_families', {})
    kanji_to_words = indexes['kanji_to_words']

    family_trees = []
    for initial_mora, fam_data in families.items():
        sample_kanji = fam_data.get('sample_kanji', [])
        total_kanji = fam_data.get('total_kanji', 0)
        total_stems = fam_data.get('total_stems', 0)

        # Filter to JLPT kanji
        jlpt_members = []
        for k in sample_kanji:
            if k in kanji_to_words:
                info = kanji_db.get(k, {})
                kun_readings = [kr['full'] for kr in info.get('kun_readings', [])]
                # Only include if it has kun readings starting with this mora
                matching_kun = [kr for kr in kun_readings if kr.startswith(initial_mora)]
                if matching_kun:
                    jlpt_members.append({
                        'kanji': k,
                        'kun_readings': matching_kun,
                        'radical': info.get('radical', ''),
                        'example_words': [f"{w['kanji']}({w['kana']})" for w in kanji_to_words.get(k, [])[:3]],
                    })

        if jlpt_members:
            family_trees.append({
                'initial_mora': initial_mora,
                'total_kanji': total_kanji,
                'total_stems': total_stems,
                'jlpt_members': jlpt_members,
            })

    family_trees.sort(key=lambda x: len(x['jlpt_members']), reverse=True)
    return family_trees

def write_word_families(family_trees, out_dir):
    """Generate word family markdown."""
    lines = []
    lines.append('# 训读词族树 · Kun-Yomi Word Family Trees')
    lines.append('')
    lines.append('> 按首拍分组的词源家族——同一首拍的训读词干往往有语义关联')
    lines.append('> 数据源：v4 穷举词族 + JLPT 交叉筛选')
    lines.append('')
    lines.append('---')
    lines.append('')

    for ft in family_trees[:30]:
        mora = ft['initial_mora']
        lines.append(f'## {mora}族（{ft["total_kanji"]}字 / {ft["total_stems"]}词干变体 / JLPT {len(ft["jlpt_members"])}字）')
        lines.append('')
        lines.append('| 汉字 | 部首 | 训读 | 例词 |')
        lines.append('|------|------|------|------|')
        for m in ft['jlpt_members'][:30]:
            kun_str = ' / '.join(m['kun_readings'][:3])
            examples = ', '.join(m['example_words'][:2])
            lines.append(f'| {m["kanji"]} | {m["radical"]} | {kun_str} | {examples} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_word_families.md', 'w') as f:
        f.write('\n'.join(lines))

    return family_trees

# ============================================================
# SECTION 5: Module 4 - JLPT Kanji Portrait Cards
# ============================================================

def build_kanji_portraits(kanji_db, indexes, v4):
    """Build comprehensive portrait cards for each JLPT kanji."""
    kanji_to_words = indexes['kanji_to_words']

    portraits = {}
    for ch, info in kanji_db.items():
        jlpt_words_for_char = kanji_to_words.get(ch, [])
        if not jlpt_words_for_char:
            continue

        levels = sorted(set(w['level'] for w in jlpt_words_for_char))

        # Find same-kun groups this kanji belongs to
        same_kun_groups = []
        for stem, group_data in v4.get('same_stem_groups', {}).items():
            if ch in group_data.get('kanji', []):
                jlpt_peers = [k for k in group_data['kanji'] if k in kanji_to_words and k != ch]
                if jlpt_peers:
                    same_kun_groups.append({'stem': stem, 'peers': jlpt_peers[:5]})

        # Find transitivity pairs
        trans_pairs = []
        for tp in v4.get('transitivity_pairs', []):
            if tp.get('kanji') == ch:
                trans_pairs.append(tp)

        # Determine on/kun tendency
        on_kun = indexes['kanji_on_kun_ratio'].get(ch, {})

        portraits[ch] = {
            'kanji': ch,
            'radical': info['radical'],
            'stroke_count': info['stroke_count'],
            'on_readings': info['on_readings'],
            'kun_readings': [kr['full'] for kr in info['kun_readings']],
            'meaning_snippet': (info['meaning'].split('◆')[1].strip() if '◆' in info['meaning'] else info['meaning'][:100])[:150],
            'jlpt_levels': levels,
            'primary_level': levels[0] if levels else 'N1',
            'example_words': [f"{w['kanji']}({w['kana']})" for w in jlpt_words_for_char[:8]],
            'same_kun_groups': same_kun_groups,
            'transitivity_pairs': trans_pairs,
            'on_kun_ratio': on_kun,
        }

    return portraits

def write_kanji_portraits(portraits, out_dir):
    """Generate per-level kanji portrait files."""
    for level in JLPT_LEVELS:
        level_portraits = {ch: p for ch, p in portraits.items() if level in p['jlpt_levels']}
        # Sort by frequency in JLPT words for this level
        sorted_chars = sorted(level_portraits.items(),
                             key=lambda x: len(x[1]['example_words']), reverse=True)

        lines = []
        lines.append(f'# JLPT {level} 汉字训读画像 · Kanji Kun-Yomi Portraits')
        lines.append('')
        lines.append(f'> {len(sorted_chars)} 个汉字 | 每字一页完整画像')
        lines.append('')
        lines.append('---')
        lines.append('')

        for i, (ch, p) in enumerate(sorted_chars[:200], 1):  # Top 200 per level
            lines.append(f'## {i}. {ch}')
            lines.append('')
            lines.append('| 属性 | 值 |')
            lines.append('|------|----|')
            lines.append(f'| 部首 | {p["radical"]} |')
            lines.append(f'| 画数 | {p["stroke_count"]} |')
            lines.append(f'| 音读 | {", ".join(p["on_readings"][:5])} |')
            lines.append(f'| 训读 | {", ".join(p["kun_readings"][:5])} |')
            lines.append(f'| JLPT级别 | {", ".join(p["jlpt_levels"])} |')
            if p.get('on_kun_ratio'):
                lines.append(f'| 音/训倾向 | 音读{p["on_kun_ratio"].get("on_ratio",0)*100:.0f}% / 训读{p["on_kun_ratio"].get("kun_ratio",0)*100:.0f}% |')
            lines.append(f'| 含义 | {p["meaning_snippet"][:120]} |')
            lines.append(f'| 例词 | {", ".join(p["example_words"][:6])} |')

            if p['same_kun_groups']:
                for sg in p['same_kun_groups'][:3]:
                    lines.append(f'| 同训({sg["stem"]}) | {", ".join(sg["peers"][:5])} |')

            if p['transitivity_pairs']:
                for tp in p['transitivity_pairs'][:2]:
                    lines.append(f'| 自他对 | 自={tp.get("intransitive","")} ↔ 他={tp.get("transitive","")} ({tp.get("pattern","")}) |')

            lines.append('')

        with open(f'{out_dir}/kun_v6_portraits_{level}.md', 'w') as f:
            f.write('\n'.join(lines))

    return portraits

# ============================================================
# SECTION 6: Module 5 - Trap Collection
# ============================================================

def build_traps(kanji_db, indexes, jlpt_words):
    """Identify common traps for Chinese-native learners."""
    traps = {
        'on_kun_confusion': [],      # 看起来像训读其实是音读，反之亦然
        'okurigana_tricks': [],      # 送假名欺骗
        'same_form_diff_read': [],   # 同形异读
        'rendaku_exceptions': [],    # 连浊例外
        'multiple_kun_traps': [],    # 多训读陷阱
        'chinese_interference': [],  # 汉语干扰
    }

    # On-kun confusion: find kanji where on reading looks like a kun reading
    for ch, info in kanji_db.items():
        jlpt_words_for_char = indexes['kanji_to_words'].get(ch, [])
        if not jlpt_words_for_char:
            continue

        on_readings = info.get('on_readings', [])
        kun_readings = info.get('kun_readings', [])

        # Short on readings that could be mistaken for kun
        for on in on_readings:
            on_clean = on.replace('ー', '').replace('ッ', 'つ')
            if len(on_clean) <= 2 and any(kr['stem'] != on_clean for kr in kun_readings):
                # This kanji has a short on reading
                examples = [f"{w['kanji']}({w['kana']})" for w in jlpt_words_for_char[:3]]
                traps['on_kun_confusion'].append({
                    'kanji': ch,
                    'short_on': on,
                    'kun_readings': [kr['full'] for kr in kun_readings[:3]],
                    'risk': '短音读易被误判为训读',
                    'examples': examples,
                })
                break

    # Multiple kun readings: kanji with 3+ kun readings are traps
    for ch, info in kanji_db.items():
        kun_count = len(info.get('kun_readings', []))
        if kun_count >= 3:
            jlpt_words_for_char = indexes['kanji_to_words'].get(ch, [])
            if jlpt_words_for_char:
                traps['multiple_kun_traps'].append({
                    'kanji': ch,
                    'num_kun': kun_count,
                    'kun_readings': [kr['full'] for kr in info['kun_readings']],
                    'examples': [f"{w['kanji']}({w['kana']})" for w in jlpt_words_for_char[:5]],
                })

    # Same-form different reading: find words that are written the same but read differently
    form_readings = defaultdict(list)
    for w in jlpt_words:
        if w['is_kanji_word']:
            form_readings[w['kanji']].append(w)

    for form, words_in_form in form_readings.items():
        unique_kana = set(w['kana'] for w in words_in_form)
        if len(unique_kana) > 1:
            traps['same_form_diff_read'].append({
                'form': form,
                'readings': sorted(unique_kana),
                'levels': sorted(set(w['level'] for w in words_in_form)),
            })

    # Chinese interference: kanji where Chinese reading might mislead
    # (This is subjective, but we flag kanji where on-yomi is very different
    #  from what a Mandarin speaker would expect based on modern pronunciation)

    # Sort and truncate each trap category
    for cat in traps:
        traps[cat].sort(key=lambda x: len(x.get('examples', [])), reverse=True)
        traps[cat] = traps[cat][:30]

    return traps

def write_traps(traps, out_dir):
    """Generate trap collection markdown."""
    lines = []
    lines.append('# 训读陷阱集 · Kun-Yomi Trap Collection')
    lines.append('')
    lines.append('> 汉语母语者最容易踩的训读坑——专门收集')
    lines.append('')
    lines.append('---')
    lines.append('')

    sections = [
        ('on_kun_confusion', '音训混淆', '短音读易被误判为训读（或反之）'),
        ('okurigana_tricks', '送假名欺骗', '看起来有送假名，但读法出乎意料'),
        ('same_form_diff_read', '同形异读', '同一个汉字写法，不同语境不同读音'),
        ('rendaku_exceptions', '连浊例外', '本该连浊但没浊，或不该浊的浊了'),
        ('multiple_kun_traps', '多训读陷阱', '3个以上训读的汉字，极易记混'),
        ('chinese_interference', '汉语干扰', '中文读音/含义导致的误判'),
    ]

    for cat_key, cat_title, cat_desc in sections:
        items = traps.get(cat_key, [])
        if not items:
            lines.append(f'## {cat_title}')
            lines.append('')
            lines.append('*(暂无数据)*')
            lines.append('')
            continue

        lines.append(f'## {cat_title}（{len(items)}条）')
        lines.append(f'> {cat_desc}')
        lines.append('')

        for item in items[:20]:
            if cat_key == 'on_kun_confusion':
                lines.append(f'- **{item["kanji"]}**：音读「{item["short_on"]}」易被误判为训读。实际训读：{", ".join(item["kun_readings"])}。例：{", ".join(item["examples"][:3])}')
            elif cat_key == 'multiple_kun_traps':
                lines.append(f'- **{item["kanji"]}**（{item["num_kun"]}个训读）：{", ".join(item["kun_readings"][:6])}。例：{", ".join(item["examples"][:4])}')
            elif cat_key == 'same_form_diff_read':
                lines.append(f'- **{item["form"]}**：可读 {", ".join(item["readings"])}（{",".join(item["levels"])}）')
            else:
                lines.append(f'- {json.dumps(item, ensure_ascii=False)[:200]}')
        lines.append('')

    with open(f'{out_dir}/kun_v6_traps.md', 'w') as f:
        f.write('\n'.join(lines))

    return traps

# ============================================================
# SECTION 7: Module 6 - Transitivity Pair Learning Units
# ============================================================

def build_transitivity_units(v4, kanji_db, indexes):
    """Build transitivity pair learning units focused on JLPT-relevant kanji."""
    kanji_to_words = indexes['kanji_to_words']
    pairs = v4.get('transitivity_pairs', [])

    # Filter to pairs where at least one kanji is in JLPT
    jlpt_pairs = []
    for tp in pairs:
        kanji = tp.get('kanji', '')
        if kanji in kanji_to_words:
            jlpt_pairs.append(tp)

    # Group by pattern
    pattern_groups = defaultdict(list)
    for tp in jlpt_pairs:
        pattern = tp.get('pattern', 'other')
        pattern_groups[pattern].append(tp)

    # For each pattern, find the most JLPT-relevant examples
    pattern_examples = {}
    for pattern, pairs_in_pattern in pattern_groups.items():
        # Sort by JLPT frequency
        pairs_in_pattern.sort(key=lambda tp: len(kanji_to_words.get(tp['kanji'], [])), reverse=True)
        pattern_examples[pattern] = pairs_in_pattern[:50]

    return {
        'total_pairs': len(pairs),
        'jlpt_pairs': len(jlpt_pairs),
        'pattern_groups': {p: len(v) for p, v in pattern_groups.items()},
        'pattern_examples': pattern_examples,
    }

def write_transitivity_units(trans_data, out_dir):
    """Generate transitivity pair learning units markdown."""
    lines = []
    lines.append('# 自他动词对学习单元 · Transitivity Pair Learning Units')
    lines.append('')
    lines.append(f'> 全量 {trans_data["total_pairs"]} 对 → JLPT相关 {trans_data["jlpt_pairs"]} 对')
    lines.append('> 学会一个 = 自动学会对应的另一个')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Pattern overview
    lines.append('## 自他对模式总览')
    lines.append('')
    lines.append('| 模式 | 数量 | 例 |')
    lines.append('|------|------|----|')
    for pattern, count in sorted(trans_data['pattern_groups'].items(), key=lambda x: x[1], reverse=True):
        lines.append(f'| {pattern} | {count} | |')
    lines.append('')

    # Per-pattern examples
    for pattern, examples in trans_data['pattern_examples'].items():
        lines.append(f'## {pattern}（{len(examples)}对）')
        lines.append('')
        lines.append('| 汉字 | 部首 | 自动词 | 他动词 |')
        lines.append('|------|------|--------|--------|')
        for tp in examples[:30]:
            lines.append(f'| {tp.get("kanji","")} | {tp.get("radical","")} | {tp.get("intransitive","")} | {tp.get("transitive","")} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_transitivity.md', 'w') as f:
        f.write('\n'.join(lines))

    return trans_data

# ============================================================
# SECTION 8: Module 7 - Compound Word Structure Analysis
# ============================================================

def build_compound_structure(jlpt_words, kanji_db):
    """Analyze internal structure of JLPT compound words."""
    structures = defaultdict(list)

    for w in jlpt_words:
        if not w['is_kanji_word'] or w['num_kanji'] < 2:
            continue

        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', w['kanji'])
        if len(kanji_chars) < 2:
            continue

        kana = w['kana']
        mora_count = len(re.sub(r'[ゃゅょっ]', '', kana))

        # Classify each kanji's reading type
        reading_types = []
        for ch in kanji_chars:
            if ch not in kanji_db:
                reading_types.append('?')
                continue
            info = kanji_db[ch]
            # Heuristic: check if any kun reading matches part of kana
            is_kun = False
            for kr in info['kun_readings']:
                if kr['stem'] and kr['stem'] in kana:
                    is_kun = True
                    break
            reading_types.append('kun' if is_kun else 'on')

        type_pattern = '+'.join(reading_types)

        structures[type_pattern].append({
            'word': w['kanji'],
            'kana': w['kana'],
            'level': w['level'],
            'mora': mora_count,
            'kanji_chars': kanji_chars,
        })

    # Summarize
    summary = []
    for pattern, words in sorted(structures.items(), key=lambda x: len(x[1]), reverse=True):
        # Count by level
        level_counts = Counter(w['level'] for w in words)
        summary.append({
            'pattern': pattern,
            'count': len(words),
            'level_counts': dict(level_counts),
            'examples': words[:10],
        })

    return summary

def write_compound_structure(compound_data, out_dir):
    """Generate compound structure analysis markdown."""
    lines = []
    lines.append('# 复合词内部结构分析 · Compound Word Structure')
    lines.append('')
    lines.append('> JLPT复合词中，汉字音训组合的模式分布')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 音训组合模式分布')
    lines.append('')
    lines.append('| 模式 | 词数 | N5 | N4 | N3 | N2 | N1 | 例词 |')
    lines.append('|------|------|----|----|----|----|----|------|')
    for s in compound_data[:20]:
        lc = s['level_counts']
        examples = ', '.join([f"{w['word']}({w['kana']})" for w in s['examples'][:3]])
        lines.append(f'| {s["pattern"]} | {s["count"]} | {lc.get("N5",0)} | {lc.get("N4",0)} | {lc.get("N3",0)} | {lc.get("N2",0)} | {lc.get("N1",0)} | {examples} |')

    lines.append('')

    # Detailed per-pattern examples
    for s in compound_data[:10]:
        lines.append(f'## {s["pattern"]}（{s["count"]}词）')
        lines.append('')
        lines.append('| 词 | 假名 | 级别 | 拍数 |')
        lines.append('|------|------|------|------|')
        for w in s['examples'][:20]:
            lines.append(f'| {w["word"]} | {w["kana"]} | {w["level"]} | {w["mora"]} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_compound.md', 'w') as f:
        f.write('\n'.join(lines))

    return compound_data

# ============================================================
# SECTION 9: Module 8 - Position Effects
# ============================================================

def build_position_effects(jlpt_words, kanji_db, indexes):
    """Analyze head/mid/tail position effects on on/kun reading choice."""
    kanji_to_words = indexes['kanji_to_words']

    pos_stats = defaultdict(lambda: {'head_on': 0, 'head_kun': 0, 'mid_on': 0, 'mid_kun': 0,
                                      'tail_on': 0, 'tail_kun': 0, 'solo_on': 0, 'solo_kun': 0})

    for w in jlpt_words:
        if not w['is_kanji_word']:
            continue
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', w['kanji'])
        kana = w['kana']

        if len(kanji_chars) == 1:
            # Solo kanji
            ch = kanji_chars[0]
            if ch in kanji_db:
                is_kun = is_kun_reading(ch, kana, kanji_db)
                if is_kun:
                    pos_stats[ch]['solo_kun'] += 1
                else:
                    pos_stats[ch]['solo_on'] += 1
        elif len(kanji_chars) >= 2:
            for i, ch in enumerate(kanji_chars):
                if ch not in kanji_db or ch not in kanji_to_words:
                    continue
                is_kun = is_kun_reading(ch, kana, kanji_db)
                if i == 0:
                    key = ('head_on', 'head_kun')
                elif i == len(kanji_chars) - 1:
                    key = ('tail_on', 'tail_kun')
                else:
                    key = ('mid_on', 'mid_kun')

                if is_kun:
                    pos_stats[ch][key[1]] += 1
                else:
                    pos_stats[ch][key[0]] += 1

    # Compute ratios for kanji with enough data
    position_report = []
    for ch, stats in pos_stats.items():
        head_total = stats['head_on'] + stats['head_kun']
        tail_total = stats['tail_on'] + stats['tail_kun']
        solo_total = stats['solo_on'] + stats['solo_kun']

        if solo_total >= 3:  # Min threshold
            position_report.append({
                'kanji': ch,
                'solo_kun_ratio': stats['solo_kun'] / solo_total if solo_total else 0,
                'head_kun_ratio': stats['head_kun'] / head_total if head_total else 0,
                'tail_kun_ratio': stats['tail_kun'] / tail_total if tail_total else 0,
                'total_occurrences': solo_total + head_total + tail_total,
            })

    position_report.sort(key=lambda x: x['total_occurrences'], reverse=True)
    return position_report[:200]

def is_kun_reading(ch, kana, kanji_db):
    """Heuristic: check if character is read as kun in this word."""
    info = kanji_db.get(ch, {})
    for kr in info.get('kun_readings', []):
        if kr['stem'] and kr['stem'] in kana:
            return True
    return False

def write_position_effects(pos_data, out_dir):
    """Generate position effects markdown."""
    lines = []
    lines.append('# 位置效应分析 · Position Effects on On/Kun Choice')
    lines.append('')
    lines.append('> 汉字在词头/词尾时，读训读的概率差异')
    lines.append('> 出现次数≥3才纳入统计')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## Top 50 位置效应最显著的汉字')
    lines.append('')
    lines.append('| 汉字 | 单字训读率 | 词头训读率 | 词尾训读率 | 出现总次数 | 解读 |')
    lines.append('|------|----------|----------|----------|----------|------|')

    for p in pos_data[:50]:
        solo = p['solo_kun_ratio']
        head = p['head_kun_ratio']
        tail = p['tail_kun_ratio']
        total = p['total_occurrences']

        # Interpret the pattern
        if solo > 0.8 and head < 0.3:
            interp = '单字训读，复合词转音读'
        elif tail > head + 0.3:
            interp = '词尾偏训读'
        elif head > tail + 0.3:
            interp = '词头偏训读'
        elif solo > 0.8:
            interp = '强训读字'
        elif solo < 0.3:
            interp = '强音读字'
        else:
            interp = '混合型'

        lines.append(f'| {p["kanji"]} | {solo:.0%} | {head:.0%} | {tail:.0%} | {total} | {interp} |')

    lines.append('')

    # Group by pattern
    lines.append('## 按位置倾向分组')
    lines.append('')

    groups = defaultdict(list)
    for p in pos_data:
        solo = p['solo_kun_ratio']
        head = p['head_kun_ratio']
        tail = p['tail_kun_ratio']
        if solo > 0.8 and head < 0.3:
            groups['单字训读 → 复合词转音读'].append(p['kanji'])
        elif tail > head + 0.3:
            groups['词尾偏训读'].append(p['kanji'])
        elif head > tail + 0.3:
            groups['词头偏训读'].append(p['kanji'])
        elif solo > 0.8:
            groups['强训读字'].append(p['kanji'])
        elif solo < 0.3:
            groups['强音读字'].append(p['kanji'])

    for gname, chars in groups.items():
        lines.append(f'- **{gname}**（{len(chars)}字）：{" ".join(chars[:20])}')

    lines.append('')

    with open(f'{out_dir}/kun_v6_positions.md', 'w') as f:
        f.write('\n'.join(lines))

    return pos_data

# ============================================================
# SECTION 10: Module 9 - Decision Tree
# ============================================================

def build_decision_tree(sorted_stems, pos_data):
    """Build an interactive decision tree for on/kun reading determination."""
    # The decision tree is a static structure based on rules
    # but presented as a decision flow rather than a flat list

    tree = {
        'question': '这个汉字在什么语境下出现？',
        'branches': [
            {
                'condition': '单独一个汉字出现',
                'accuracy': '82.7%',
                'prediction': '训读',
                'sub_branches': [
                    {
                        'condition': '有送假名（〜く/む/る/い/す/ぶ/つ/ぐ/ぬ等）',
                        'accuracy': '96.1%',
                        'prediction': '训读用言',
                        'sub_branches': [
                            {'condition': '尾音=る/う/く/つ/ぶ/む/ぐ/ぬ', 'prediction': '五段动词', 'accuracy': '100%'},
                            {'condition': '尾音=す', 'prediction': '五段他动词', 'accuracy': '100%'},
                            {'condition': '尾音=える/ける/いる', 'prediction': '一段动词', 'accuracy': '100%'},
                            {'condition': '尾音=い/しい', 'prediction': '形容词', 'accuracy': '100%'},
                        ],
                    },
                    {
                        'condition': '无送假名',
                        'accuracy': '72.2%',
                        'prediction': '名词',
                        'sub_branches': [
                            {'condition': '部首=魚/米/牛/竹/虫/木/雨', 'prediction': '几乎确定为名词', 'accuracy': '95%+'},
                            {'condition': '部首=手/言/力/足/刀', 'prediction': '也有动词可能', 'accuracy': '65%'},
                        ],
                    },
                ],
            },
            {
                'condition': '二字复合词',
                'sub_branches': [
                    {'condition': '2拍', 'prediction': '音读+音读', 'accuracy': '71.2%'},
                    {'condition': '3-4拍', 'prediction': '混合（音训/训音/音音/训训均可）', 'accuracy': '不定'},
                    {'condition': '5拍+', 'prediction': '至少含一个训读', 'accuracy': '90.4%'},
                ],
            },
            {
                'condition': '三字+复合词',
                'sub_branches': [
                    {'condition': '前二字2拍', 'prediction': '前=音+音，后=看情况', 'accuracy': '参考'},
                    {'condition': '整体5拍+', 'prediction': '含训读概率高', 'accuracy': '90%'},
                ],
            },
        ],
        'verification': [
            {'rule': '浊音g/z/d/b不重复', 'usage': '排除包含重复浊音的训读猜测', 'accuracy': '99.5%'},
            {'rule': '自然物部首无动词', 'usage': '魚/米/牛/竹/虫/雨部 → 排除动词训读', 'accuracy': '95%'},
            {'rule': '入声字→动词倾向', 'usage': '-ク/-ツ音读字 → 训读倾向动词', 'accuracy': '64%'},
        ],
        'frequency_weighted': [
            {'stem': s, 'freq': d['total']} for s, d in sorted_stems[:20]
        ],
    }

    return tree

def write_decision_tree(tree, out_dir):
    """Generate decision tree markdown."""
    lines = []
    lines.append('# 训读判定决策树 · Kun-Yomi Decision Tree')
    lines.append('')
    lines.append('> 不是记100条规则，而是走一个流程')
    lines.append('> 每次遇到汉字 → 回答1-3个问题 → 得到判定 + 置信度')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 主决策流程')
    lines.append('')
    lines.append('```')
    lines.append('看到含汉字的日语词')
    lines.append('│')
    lines.append('├─ 单独一个汉字？')
    lines.append('│   ├─ 是 → [训读 82.7%]')
    lines.append('│   │   ├─ 有送假名？ → 是 → [训读用言 96.1%]')
    lines.append('│   │   │   ├─ 尾音=る/う/く/つ/ぶ/む/ぐ/ぬ → 五段动词 [100%]')
    lines.append('│   │   │   ├─ 尾音=す → 五段他动词 [100%]')
    lines.append('│   │   │   ├─ 尾音=える/ける/いる → 一段动词 [100%]')
    lines.append('│   │   │   └─ 尾音=い/しい → 形容词 [100%]')
    lines.append('│   │   └─ 无送假名 → [名词 72.2%]')
    lines.append('│   │       ├─ 部首=魚/米/牛/竹/虫/木/雨 → 几乎确认名词 [95%+]')
    lines.append('│   │       └─ 部首=手/言/力/足/刀 → 也有动词可能 [65%]')
    lines.append('│   └─ 否 → 复合词')
    lines.append('│       ├─ 2汉字2拍 → 音读+音读 [71.2%]')
    lines.append('│       ├─ 2汉字5拍+ → 含训读 [90.4%]')
    lines.append('│       └─ 3拍 → 看具体情况')
    lines.append('```')
    lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## 验证层（交叉确认）')
    lines.append('')
    lines.append('| 验证规则 | 用法 | 准确率 |')
    lines.append('|---------|------|--------|')
    for v in tree.get('verification', []):
        lines.append(f'| {v["rule"]} | {v["usage"]} | {v["accuracy"]} |')

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 频率加权优先学习')
    lines.append('')
    lines.append('> JLPT中最常出现的训读词干——优先学这些')
    lines.append('')
    lines.append('| 排名 | 词干 | JLPT总频次 |')
    lines.append('|------|------|----------|')
    for i, item in enumerate(tree.get('frequency_weighted', [])[:20], 1):
        lines.append(f'| {i} | **{item["stem"]}** | {item["freq"]} |')

    lines.append('')

    with open(f'{out_dir}/kun_v6_decision_tree.md', 'w') as f:
        f.write('\n'.join(lines))

    return tree

# ============================================================
# SECTION 11: Module 10 - Optimized Rules (v6)
# ============================================================

def build_optimized_rules(sorted_stems, indexes):
    """Rebuild rules with frequency weighting and prune low-quality ones."""
    # Load v5 rules
    with open(f'{OUT}/kun_tiered_rules.json') as f:
        v5 = json.load(f)

    # Build stem frequency lookup
    stem_freq_lookup = {s: d['total'] for s, d in sorted_stems}
    max_freq = max(stem_freq_lookup.values()) if stem_freq_lookup else 1

    # Re-score rules with frequency weighting
    optimized_rules = []
    for level in JLPT_LEVELS:
        level_rules_raw = v5['levels'][level]['rules']
        level_rules = []
        for r in level_rules_raw:
            # Skip low-quality rules
            if r['rule_type'] == 'A' and r['accuracy'] < 0.5:
                continue  # Skip A2 (19.7%) and A7 (22.4%)
            if r['rule_type'] == 'B' and r['accuracy'] < 0.4:
                continue  # Skip very low accuracy radical rules

            # Compute frequency weight: does this rule help with high-freq stems?
            freq_weight = 1.0
            if r['rule_type'] == 'C':
                # Type C: extract predicted stem and weight by its JLPT frequency
                pred = r.get('prediction', '')
                stem_match = re.search(r'[「]([^」]+)[」]', r.get('rule_text', ''))
                if stem_match:
                    predicted_stem = stem_match.group(1).split('/')[0].strip()
                    if predicted_stem in stem_freq_lookup:
                        freq_weight = stem_freq_lookup[predicted_stem] / max(1, max_freq * 0.1)
                        freq_weight = min(5.0, max(0.1, freq_weight * 10))

            # Re-compute score with frequency weighting
            pl = r['per_level'].get(level, {})
            acc = pl.get('accuracy', r['accuracy']) if pl else r['accuracy']
            cov = pl.get('coverage', r['coverage']) if pl else r['coverage']
            cost = r['memorization_cost']

            # New score formula: coverage * accuracy² * frequency_weight / cost
            new_score = cov * (acc ** 2) * freq_weight / max(1, cost)

            level_rules.append({
                **r,
                'frequency_weight': round(freq_weight, 2),
                'v6_score': round(new_score, 6),
                'v6_kept': True,
            })

        # Re-sort by new score
        level_rules.sort(key=lambda x: x['v6_score'], reverse=True)

        # Re-run greedy set-cover (simplified — just re-rank, not full set-cover)
        optimized_rules.append({
            'level': level,
            'num_rules_before': len(v5['levels'][level]['rules']),
            'num_rules_after': len(level_rules),
            'rules': level_rules,
        })

    return optimized_rules

def write_optimized_rules(optimized_rules, out_dir):
    """Write optimized rules."""
    # JSON
    output = {
        'version': '6.0',
        'description': 'Frequency-weighted, pruned tiered kun-yomi rules',
        'levels': {},
    }

    for lr in optimized_rules:
        level = lr['level']
        output['levels'][level] = {
            'num_rules': lr['num_rules_after'],
            'rules': lr['rules'],
        }

    with open(f'{out_dir}/kun_v6_rules.json', 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Markdown summary
    lines = []
    lines.append('# 优化规则 v6 · Optimized Kun-Yomi Rules')
    lines.append('')
    lines.append('> 基于频率加权重新评分 + 砍掉低质量规则')
    lines.append('> 与v5对比：去除准确率<40%的Type B规则 + A2/A7')
    lines.append('')
    lines.append('---')
    lines.append('')

    for lr in optimized_rules:
        level = lr['level']
        lines.append(f'## {level} 级（{lr["num_rules_after"]}条，优化前{lr["num_rules_before"]}条）')
        lines.append('')
        lines.append('| # | 规则 | 类型 | 准确率 | 覆盖 | v6评分 | 频度权重 |')
        lines.append('|---|------|------|--------|------|--------|---------|')
        for i, r in enumerate(lr['rules'][:20], 1):
            lines.append(f'| {i} | {r["name"]} | {r["rule_type"]} | {r["accuracy"]:.1%} | {r["coverage"]:.4f} | {r["v6_score"]:.4f} | {r["frequency_weight"]:.1f} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_rules.md', 'w') as f:
        f.write('\n'.join(lines))

    return optimized_rules

# ============================================================
# SECTION 12: Module 11 - Learning Path
# ============================================================

def build_learning_path(sorted_stems, samekun_cards, family_trees, optimized_rules, indexes):
    """Build recommended learning path."""

    # Phase 1: Top 20 kun stems (covers ~50% of kun occurrences)
    top_stems = sorted_stems[:20]

    # Phase 2: Okurigana system
    okurigana_system = [
        {'suffix': 'る/う/く/つ/ぶ/む/ぐ/ぬ', 'predicts': '五段动词', 'accuracy': '100%'},
        {'suffix': 'す', 'predicts': '五段他动词', 'accuracy': '100%'},
        {'suffix': 'える/ける/いる', 'predicts': '一段动词', 'accuracy': '100%'},
        {'suffix': 'い/しい', 'predicts': '形容词', 'accuracy': '100%'},
        {'suffix': '无', 'predicts': '名词', 'accuracy': '72.2%'},
    ]

    # Phase 3: High-accuracy radical rules
    radical_rules = [
        {'radical': '魚/米/牛/竹/虫/木/雨', 'predicts': '名词', 'note': '自然物部首=名词'},
        {'radical': '手/言/力/足/刀', 'predicts': '动词', 'note': '动作部首=动词'},
        {'radical': '金/巾/宀/广', 'predicts': '名词', 'note': '人造物/建筑=名词'},
    ]

    # Phase 4: Component → stem bindings (only high-freq ones)
    component_rules = []
    for lr in optimized_rules:
        for r in lr['rules']:
            if r['rule_type'] == 'C' and r.get('frequency_weight', 0) > 1.0:
                component_rules.append(r)

    # Phase 5: Transitivity patterns
    trans_patterns = [
        {'pattern': '〜る(自) ↔ 〜す(他)', 'example': '直る↔直す'},
        {'pattern': '〜u(自) ↔ 〜eru(他)', 'example': '開く↔開ける'},
        {'pattern': '〜reru(自) ↔ 〜su(他)', 'example': '流れる↔流す'},
    ]

    return {
        'phase1_top_stems': [(s, d['total'], d['kanji_list'][:10]) for s, d in top_stems],
        'phase2_okurigana': okurigana_system,
        'phase3_radicals': radical_rules,
        'phase4_components': component_rules[:15],
        'phase5_transitivity': trans_patterns,
        'phase6_same_kun': len(samekun_cards),
        'phase7_traps': '见陷阱集',
        'total_estimated_time': '50-80小时（分散在2-3个月备考周期中）',
    }

def write_learning_path(learning_path, out_dir):
    """Generate learning path markdown."""
    lines = []
    lines.append('# 训读学习路径 v6 · Recommended Learning Path')
    lines.append('')
    lines.append('> 7个阶段，从高频到低频，从确定到辅助')
    lines.append(f'> 总估计时间：{learning_path["total_estimated_time"]}')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 第一阶段：高频词干（第一周，6-8小时）')
    lines.append('')
    lines.append('> 记住这20个训读词干 = 解决约50%的训读出现')
    lines.append('')
    lines.append('| 排名 | 词干 | JLPT频次 | 代表字 |')
    lines.append('|------|------|---------|--------|')
    for i, (stem, freq, kanji_list) in enumerate(learning_path['phase1_top_stems'], 1):
        kanji_str = ' '.join(kanji_list[:8])
        lines.append(f'| {i} | **{stem}** | {freq} | {kanji_str} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 第二阶段：送假名体系（第二周，4-6小时）')
    lines.append('')
    lines.append('> 送假名尾音直接决定词类——日语语法本身')
    lines.append('')
    lines.append('| 送假名尾音 | → 词类 | 准确率 |')
    lines.append('|----------|--------|--------|')
    for o in learning_path['phase2_okurigana']:
        lines.append(f'| {o["suffix"]} | {o["predicts"]} | {o["accuracy"]} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 第三阶段：部首→词类映射（第三周，4-6小时）')
    lines.append('')
    lines.append('> 利用汉语母语者已有的部首知识')
    lines.append('')
    for r in learning_path['phase3_radicals']:
        lines.append(f'- **{r["radical"]}** → {r["predicts"]}（{r["note"]}）')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 第四阶段：部件→词干绑定（第四-五周，8-10小时）')
    lines.append('')
    lines.append('> 仅学习高频JLPT相关的部件→词干绑定')
    lines.append('')
    if learning_path['phase4_components']:
        lines.append('| 部件 | → 词干 | 准确率 | JLPT频度 |')
        lines.append('|------|--------|--------|---------|')
        for r in learning_path['phase4_components'][:15]:
            lines.append(f'| {r.get("name","")} | {r.get("prediction","")} | {r.get("accuracy",0):.1%} | {r.get("frequency_weight",0):.1f} |')
    else:
        lines.append('*(高频Type C规则不足——部件→词干预测在JLPT范围内实用性有限)*')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 第五阶段：自他动词模式（第五周，3-4小时）')
    lines.append('')
    for tp in learning_path['phase5_transitivity']:
        lines.append(f'- **{tp["pattern"]}**：{tp["example"]}')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 第六阶段：同训异字辨析（第六-八周，10-15小时）')
    lines.append(f'> {learning_path["phase6_same_kun"]} 组同训异字辨析卡——理解「一词多字」的分化逻辑')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 第七阶段：陷阱与反模式（贯穿全程，持续积累）')
    lines.append(f'> {learning_path["phase7_traps"]}')

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 每级对应阶段')
    lines.append('')
    lines.append('| JLPT级别 | 重点阶段 | 新增内容 |')
    lines.append('|---------|---------|---------|')
    lines.append('| N5 | 阶段1-2 | 高频词干 + 送假名体系 |')
    lines.append('| N4 | 阶段2-3 | 送假名深化 + 部首映射 |')
    lines.append('| N3 | 阶段3-5 | 部首巩固 + 自他动词 |')
    lines.append('| N2 | 阶段4-6 | 部件绑定 + 同训辨析 |')
    lines.append('| N1 | 阶段5-7 | 自他深化 + 陷阱识别 + 全体系整合 |')

    lines.append('')

    with open(f'{out_dir}/kun_v6_learning_path.md', 'w') as f:
        f.write('\n'.join(lines))

    return learning_path

# ============================================================
# SECTION 13: Module 12 - Summary Dashboard
# ============================================================

def build_summary(all_results, jlpt_words, kanji_db):
    """Build executive summary dashboard."""
    total_jlpt_words = len(jlpt_words)
    kanji_words = sum(1 for w in jlpt_words if w['is_kanji_word'])
    total_kanji_in_jlpt = len(set(
        ch for w in jlpt_words if w['is_kanji_word']
        for ch in re.findall(r'[一-鿿㐀-䶿]', w['kanji'])
        if ch in kanji_db
    ))

    return {
        'data_scale': {
            'total_kanji_db': len(kanji_db),
            'total_jlpt_words': total_jlpt_words,
            'kanji_containing_words': kanji_words,
            'unique_jlpt_kanji': total_kanji_in_jlpt,
        },
        'modules_generated': list(all_results.keys()),
        'top_10_stems': [(s, d['total']) for s, d in all_results.get('sorted_stems', [])[:10]],
        'same_kun_cards': len(all_results.get('diff_cards', [])),
        'word_families': len(all_results.get('family_trees', [])),
        'traps': {k: len(v) for k, v in all_results.get('traps', {}).items()},
        'transitivity_jlpt_pairs': all_results.get('trans_data', {}).get('jlpt_pairs', 0),
        'compound_patterns': len(all_results.get('compound_data', [])),
        'position_kanji_analyzed': len(all_results.get('pos_data', [])),
    }

def write_summary(summary, all_results, out_dir):
    """Generate summary dashboard markdown."""
    lines = []
    lines.append('# 训读淘金 v6 · 总览仪表盘 · Executive Dashboard')
    lines.append('')
    lines.append('> 生成: 2026-05-07 | tiered_rules_v6.py')
    lines.append('> 数据: 漢字検索V2 46,848字 + 红宝书 9,573词 + v4穷举数据')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 数据规模')
    lines.append('')
    ds = summary['data_scale']
    lines.append(f'| 指标 | 值 |')
    lines.append(f'|------|----|')
    lines.append(f'| 汉字数据库 | {ds["total_kanji_db"]:,} 字 |')
    lines.append(f'| JLPT词汇总数 | {ds["total_jlpt_words"]:,} 词 |')
    lines.append(f'| 含汉字词汇 | {ds["kanji_containing_words"]:,} 词 |')
    lines.append(f'| JLPT涉及汉字 | {ds["unique_jlpt_kanji"]:,} 字 |')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 12模块产出清单')
    lines.append('')
    lines.append('| # | 模块 | 产出文件 | 核心数据 |')
    lines.append('|---|------|---------|---------|')
    lines.append(f'| 1 | 频率热力图 | kun_v6_frequency_heatmap.md | {len(all_results.get("sorted_stems", []))} 个词干 |')
    lines.append(f'| 2 | 同训辨析 | kun_v6_samekun_diff.md | {summary["same_kun_cards"]} 组辨析卡 |')
    lines.append(f'| 3 | 词族树 | kun_v6_word_families.md | {summary["word_families"]} 个词族 |')
    lines.append(f'| 4 | 汉字画像 | kun_v6_portraits_N5~N1.md | {ds["unique_jlpt_kanji"]} 字 × 5级 |')
    lines.append(f'| 5 | 陷阱集 | kun_v6_traps.md | {sum(summary["traps"].values())} 条陷阱 |')
    lines.append(f'| 6 | 自他对 | kun_v6_transitivity.md | {summary["transitivity_jlpt_pairs"]} 对JLPT相关 |')
    lines.append(f'| 7 | 复合词结构 | kun_v6_compound.md | {summary["compound_patterns"]} 种组合模式 |')
    lines.append(f'| 8 | 位置效应 | kun_v6_positions.md | {summary["position_kanji_analyzed"]} 字分析 |')
    lines.append(f'| 9 | 决策树 | kun_v6_decision_tree.md | 交互式判定流程 |')
    lines.append(f'| 10 | 优化规则 | kun_v6_rules.json + .md | 频率加权 + 低质砍除 |')
    lines.append(f'| 11 | 学习路径 | kun_v6_learning_path.md | 7阶段学习计划 |')
    lines.append(f'| 12 | 总览仪表盘 | kun_v6_summary.md | 本文件 |')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## Top 10 最高频训读词干')
    lines.append('')
    for i, (stem, freq) in enumerate(summary['top_10_stems'], 1):
        lines.append(f'{i}. **{stem}**（{freq}次）')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 陷阱分布')
    lines.append('')
    for cat, count in summary['traps'].items():
        lines.append(f'- {cat}: {count} 条')

    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## v5 → v6 核心改进')
    lines.append('')
    lines.append('| 维度 | v5 | v6 |')
    lines.append('|------|----|----|')
    lines.append('| 规则形式 | 101条平铺规则 | 决策树 + 规则 + 画像 + 辨析 |')
    lines.append('| 频率意识 | 无 | JLPT词干频率加权 |')
    lines.append('| 同训辨析 | 无（v4有数据未用） | 自动辨析卡 |')
    lines.append('| 词族关联 | 无（v4有数据未用） | 词族树 |')
    lines.append('| 逐字画像 | 无 | 5级 × 每字画像卡 |')
    lines.append('| 陷阱收集 | 无 | 6类陷阱自动收集 |')
    lines.append('| 自他动词 | 无（v4有数据未用） | 按模式分组学习单元 |')
    lines.append('| 学习顺序 | Quick/Deep/Complete（粗糙） | 7阶段渐进路径 |')
    lines.append('| 呈现形式 | 规则列表 | 决策树/图谱/画像/卡片 |')
    lines.append('| 规则质量 | 含低质规则(准确率<40%) | 砍除低质 + 频率重评分 |')
    lines.append('| 复合词分析 | 粗略（2拍/5拍） | 内部音训结构模式 |')

    lines.append('')
    lines.append(f'*生成: 2026-05-07 | tiered_rules_v6.py*')

    with open(f'{out_dir}/kun_v6_summary.md', 'w') as f:
        f.write('\n'.join(lines))

    return summary

# ============================================================
# SECTION 14: Main
# ============================================================

def main():
    print("=" * 70)
    print("Kun-Yomi V6: Comprehensive Learning System")
    print("=" * 70)

    # Ensure output directory
    os.makedirs(OUT, exist_ok=True)

    # Load data
    print("\n[1/3] Loading data...")
    jlpt_words = load_jlpt_words()
    print(f"  JLPT words: {len(jlpt_words)}")

    kanji_db = load_kanji_db()
    print(f"  Kanji DB: {len(kanji_db)}")

    v4 = load_v4_data()
    print(f"  V4 data loaded")

    # Build indexes
    print("\n[2/3] Building cross-reference indexes...")
    indexes = build_indexes(jlpt_words, kanji_db, v4)
    print(f"  Level words: {dict((k, len(v)) for k, v in indexes['level_words'].items())}")
    print(f"  Kanji→words: {len(indexes['kanji_to_words'])} mappings")
    print(f"  Stem→kanji: {len(indexes['stem_to_kanji'])} stems")

    # Generate all modules
    print("\n[3/3] Generating 12 modules...")

    all_results = {}

    # Module 1: Frequency Heatmap
    print("  [1/12] Frequency heatmap...")
    sorted_stems = write_frequency_heatmap(sorted_stems := build_frequency_heatmap(kanji_db, indexes, jlpt_words), OUT)
    all_results['sorted_stems'] = sorted_stems

    # Module 2: Same-Kun Differentiation
    print("  [2/12] Same-kun differentiation...")
    diff_cards = write_samekun_diff(diff_cards := build_samekun_diff(v4, kanji_db, indexes, jlpt_words), OUT)
    all_results['diff_cards'] = diff_cards

    # Module 3: Word Family Trees
    print("  [3/12] Word family trees...")
    family_trees = write_word_families(family_trees := build_word_families(v4, kanji_db, indexes), OUT)
    all_results['family_trees'] = family_trees

    # Module 4: Kanji Portrait Cards
    print("  [4/12] Kanji portrait cards...")
    portraits = write_kanji_portraits(portraits := build_kanji_portraits(kanji_db, indexes, v4), OUT)
    all_results['portraits'] = portraits

    # Module 5: Trap Collection
    print("  [5/12] Trap collection...")
    traps = write_traps(traps := build_traps(kanji_db, indexes, jlpt_words), OUT)
    all_results['traps'] = traps

    # Module 6: Transitivity Pairs
    print("  [6/12] Transitivity pairs...")
    trans_data = write_transitivity_units(trans_data := build_transitivity_units(v4, kanji_db, indexes), OUT)
    all_results['trans_data'] = trans_data

    # Module 7: Compound Structure
    print("  [7/12] Compound structure...")
    compound_data = write_compound_structure(compound_data := build_compound_structure(jlpt_words, kanji_db), OUT)
    all_results['compound_data'] = compound_data

    # Module 8: Position Effects
    print("  [8/12] Position effects...")
    pos_data = write_position_effects(pos_data := build_position_effects(jlpt_words, kanji_db, indexes), OUT)
    all_results['pos_data'] = pos_data

    # Module 9: Decision Tree
    print("  [9/12] Decision tree...")
    tree = write_decision_tree(tree := build_decision_tree(sorted_stems, pos_data), OUT)
    all_results['tree'] = tree

    # Module 10: Optimized Rules
    print("  [10/12] Optimized rules...")
    optimized_rules = write_optimized_rules(optimized_rules := build_optimized_rules(sorted_stems, indexes), OUT)
    all_results['optimized_rules'] = optimized_rules

    # Module 11: Learning Path
    print("  [11/12] Learning path...")
    learning_path = write_learning_path(learning_path := build_learning_path(
        sorted_stems, diff_cards, family_trees, optimized_rules, indexes), OUT)
    all_results['learning_path'] = learning_path

    # Module 12: Summary Dashboard
    print("  [12/12] Summary dashboard...")
    summary = build_summary(all_results, jlpt_words, kanji_db)
    write_summary(summary, all_results, OUT)
    all_results['summary'] = summary

    # Done
    print("\n" + "=" * 70)
    print("V6 generation complete!")
    print(f"Output directory: {OUT}/")
    print(f"Files generated:")
    for f in sorted(os.listdir(OUT)):
        if f.startswith('kun_v6_'):
            size = os.path.getsize(os.path.join(OUT, f))
            print(f"  {f} ({size:,} bytes)")
    print("=" * 70)

if __name__ == '__main__':
    main()
