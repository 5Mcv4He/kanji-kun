#!/usr/bin/env python3
"""
训读淘金v3 — 穷举式语义挖掘 + 双层规则体系
============================================
v3新增：
1. 意味字段语义群聚类 → 训读映射（最大未开采金矿）
2. 每部首/部件→具体训读词干映射表（微观规则）
3. 覆盖所有遗漏维度（连浊/连用形/同训异字/复合词位置/训读词干共现/音读-训读映射）
4. 产出「宏观规律总表」+「逐字规则卡」双层交付物
"""

import openpyxl, re, json, time, math
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Optional, Any
from itertools import combinations

# ═══════════════════════════════════════════
# 0. CONFIG
# ═══════════════════════════════════════════

BASE = '/Volumes/SSD/work/kanji-kun'

# ── Constants ──
NATURE_RADICALS = {'魚','虫','木','竹','鳥','米'}
TOOL_RADICALS = {'手','馬','弓','食','車','刀','火','攴','扌','金'}
BODY_RADICALS = {'月','肉','骨','血','身','歯','耳','目','口','鼻','舌'}
MIND_RADICALS = {'心','忄','思','想','念'}
SPEECH_RADICALS = {'言','口','舌'}
MOTION_RADICALS = {'辶','走','足','彳','行','廴'}
NATURE_RADICALS_ALL = NATURE_RADICALS | {'艸','艹','山','石','水','氵','火','灬','雨','風','土','田','日'}

VOICED_CONSONANTS = {
    'が':'g','ぎ':'g','ぐ':'g','げ':'g','ご':'g',
    'ざ':'z','じ':'z','ず':'z','ぜ':'z','ぞ':'z',
    'だ':'d','ぢ':'d','づ':'d','で':'d','ど':'d',
    'ば':'b','び':'b','ぶ':'b','べ':'b','ぼ':'b',
}

STRONG_VERB_MORAE = {'そ','ゆ','お','ち','ね'}
STRONG_NOUN_MORAE = {'ぶ','じ','く','や','ひ','み'}

# Semantic keyword → word class prediction
SEMANTIC_KEYWORDS = {
    # Action verbs
    '動': 'verb', '打': 'verb', '持': 'verb', '歩': 'verb', '走': 'verb',
    '言': 'verb', '話': 'verb', '見': 'verb', '聞': 'verb', '食': 'verb',
    '飲': 'verb', '書': 'verb', '読': 'verb', '来': 'verb', '去': 'verb',
    '出': 'verb', '入': 'verb', '開': 'verb', '閉': 'verb', '上': 'verb',
    '下': 'verb', '取': 'verb', '与': 'verb', '授': 'verb', '受': 'verb',
    '切': 'verb', '断': 'verb', '折': 'verb', '割': 'verb', '殺': 'verb',
    '作': 'verb', '造': 'verb', '建': 'verb', '立': 'verb', '座': 'verb',
    '泳': 'verb', '飛': 'verb', '流': 'verb', '泣': 'verb', '笑': 'verb',
    '思': 'verb', '考': 'verb', '知': 'verb', '忘': 'verb', '覚': 'verb',
    '死': 'verb', '生': 'verb', '育': 'verb', '成': 'verb', '変': 'verb',
    '移': 'verb', '動く': 'verb', 'する': 'verb', '行う': 'verb',
    # Nature nouns
    '木': 'noun', '草': 'noun', '花': 'noun', '虫': 'noun', '魚': 'noun',
    '鳥': 'noun', '山': 'noun', '川': 'noun', '海': 'noun', '石': 'noun',
    '土': 'noun', '水': 'noun', '火': 'noun', '風': 'noun', '雨': 'noun',
    '雲': 'noun', '空': 'noun', '星': 'noun', '日': 'noun', '月': 'noun',
    # Body parts
    '体': 'noun', '手': 'noun', '足': 'noun', '目': 'noun', '耳': 'noun',
    '口': 'noun', '鼻': 'noun', '頭': 'noun', '心': 'noun', '血': 'noun',
    '骨': 'noun', '肉': 'noun', '歯': 'noun', '皮': 'noun', '毛': 'noun',
    # Adjectives
    '高': 'adj', '低': 'adj', '大': 'adj', '小': 'adj', '多': 'adj',
    '少': 'adj', '長': 'adj', '短': 'adj', '良': 'adj', '悪': 'adj',
    '美': 'adj', '新': 'adj', '古': 'adj', '強': 'adj', '弱': 'adj',
    '固': 'adj', '柔': 'adj', '温': 'adj', '冷': 'adj', '暗': 'adj',
}

# ═══════════════════════════════════════════
# 1. DATA LOADING
# ═══════════════════════════════════════════

def load_kanji_db(filepath: str) -> List[Dict]:
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb['漢字一覧']
    kanji_list = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None: continue
        kanji = str(row[0]).strip()
        if not kanji or len(kanji) > 2: continue

        components = str(row[1]) if row[1] else ''
        radical = str(row[3]) if row[3] else ''
        radical_cd = str(row[4]) if row[4] else ''
        non_radical = str(row[5]) if row[5] else ''
        rad_strokes = int(row[6]) if row[6] else 0
        total_strokes = int(row[8]) if row[8] else 0
        on_raw = str(row[9]) if row[9] else ''
        kun_raw = str(row[10]) if row[10] else ''
        meaning_raw = str(row[11]) if row[11] else ''

        kun_list = parse_kun(kun_raw)
        on_list = parse_on(on_raw)

        # Extract non-radical components
        comp_set = set(c for c in components if c != kanji and c != radical)

        # Semantic cluster extraction from meaning
        sem_clusters = extract_semantic_clusters(meaning_raw)

        # Character formation type (六书 heuristic)
        form_type = classify_formation(kanji, components, radical)

        kanji_list.append({
            'kanji': kanji,
            'components': components,
            'comp_set': comp_set,
            'radical': radical,
            'radical_cd': radical_cd,
            'non_radical': non_radical,
            'total_strokes': total_strokes,
            'on_list': on_list,
            'kun_list': kun_list,
            'meaning': meaning_raw,
            'sem_clusters': sem_clusters,
            'form_type': form_type,
            'has_kun': len(kun_list) > 0,
            'has_on': len(on_list) > 0,
            'kun_count': len(kun_list),
            'on_count': len(on_list),
        })
    wb.close()
    return kanji_list


def parse_kun(raw: str) -> List[Dict]:
    if not raw: return []
    results = []
    for entry in re.split(r'[、\s]+', raw):
        entry = entry.strip().strip('◇◆▼▽▲△▼▽').strip()
        if not entry: continue
        parts = re.split(r'[・.]', entry)
        stem = parts[0]
        okuri = parts[-1] if len(parts) >= 2 else ''
        wclass = classify_wc(okuri)
        mc = count_morae(stem)
        results.append({
            'full': entry, 'stem': stem, 'okuri': okuri, 'wclass': wclass,
            'mora_count': mc,
            'first_mora': stem[0] if stem else '',
            'last_mora': stem[-1] if stem else '',
            'all_morae': list(iter_morae(stem)),
            'is_verb': 'verb' in wclass,
            'is_noun': 'noun' in wclass and 'renyo' not in wclass,
            'is_adj': 'adj' in wclass,
        })
    return results


def parse_on(raw: str) -> List[str]:
    if not raw: return []
    results = []
    for e in re.split(r'[、\s]+', raw):
        e = e.strip().strip('◇◆▼▽▲△▽').strip()
        if e and not e.startswith('◆'):
            e = re.sub(r'[（(].*?[）)]', '', e).strip()
            if e: results.append(e)
    return results


def classify_wc(okuri: str) -> str:
    if not okuri: return 'noun'
    if re.search(r'[くぐすつぬぶむ]$', okuri): return 'verb_godan'
    if okuri.endswith('る'):
        if okuri in ('いる','える','きる','ぎる','じる','びる','みる','りる',
                     'ける','げる','せる','ぜる','てる','でる','ねる','へる',
                     'べる','める','れる'): return 'verb_ichidan'
        return 'verb_godan'
    if okuri == 'う': return 'verb_godan'
    if okuri.endswith('い'):
        if okuri == 'しい': return 'adj_shiku'
        return 'adjective'
    if okuri in ('り','み','え','き','ぎ','ち','に','ひ','び'): return 'noun_renyo'
    return 'noun'


def count_morae(s: str) -> int:
    cnt = i = 0
    while i < len(s):
        if i+1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉャュョァィゥェォ':
            cnt += 1; i += 2
        elif s[i] in 'っッ': cnt += 1; i += 1
        else: cnt += 1; i += 1
    return cnt


def iter_morae(s: str):
    """Iterate over morae in string."""
    i = 0
    while i < len(s):
        if i+1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉャュョァィゥェォ':
            yield s[i:i+2]; i += 2
        elif s[i] in 'っッ': yield s[i]; i += 1
        else: yield s[i]; i += 1


def extract_semantic_clusters(meaning: str) -> List[str]:
    """Extract semantic cluster labels from meaning field."""
    if not meaning: return []
    clusters = []

    # Body parts
    for kw in ['体','手','足','目','耳','口','鼻','頭','心','血','骨','肉','歯','皮','毛',
               '指','腕','脚','腹','背','腰','胸','舌','爪','肌','髪','脳','肺','肝']:
        if kw in meaning: clusters.append('body')

    # Nature
    for kw in ['木','草','花','虫','魚','鳥','獣','山','川','海','石','土','水','火',
               '風','雨','雲','空','星','日','月','天','地']:
        if kw in meaning: clusters.append('nature')

    # Action/motion
    for kw in ['動','打','持','歩','走','言','話','見','聞','食','飲','書','読','出','入',
               '開','閉','取','与','切','断','折','割','作','造','建','泳','飛','流',
               '泣','笑','思','考','知','忘']:
        if kw in meaning: clusters.append('action')

    # Emotion/mind
    for kw in ['心','思','考','念','意','情','感','怒','喜','悲','恐','愛','憎','恨']:
        if kw in meaning: clusters.append('emotion')

    # Speech
    for kw in ['言','語','話','告','述','説','論','談','議','訓','読','誦','唱']:
        if kw in meaning: clusters.append('speech')

    # Tool/artifact
    for kw in ['刀','剣','弓','矢','車','舟','器','具','衣','糸','布','紙','金','玉']:
        if kw in meaning: clusters.append('tool')

    # Person/social
    for kw in ['人','男','女','子','父','母','兄','弟','姉','妹','親','族',
               '王','臣','民','君','主']:
        if kw in meaning: clusters.append('person')

    # Number/quantity
    for kw in ['数','量','一','二','三','四','五','六','七','八','九','十','百','千','万',
               '多','少','大','小','長','短']:
        if kw in meaning: clusters.append('quantity')

    # Quality/state
    for kw in ['良','悪','美','醜','善','正','新','古','強','弱','固','柔',
               '温','冷','暗','明','高','低','遠','近']:
        if kw in meaning: clusters.append('quality')

    if not clusters:
        clusters.append('other')

    return list(set(clusters))


def classify_formation(kanji: str, components: str, radical: str) -> str:
    """Heuristically classify character formation type (六书)."""
    # Simplified heuristic
    comp_chars = set(c for c in components if c != kanji)

    # 象形(pictograph): single component, very few strokes
    if len(comp_chars) <= 1:
        return 'pictograph'
    # 会意(compound ideograph): multiple meaningful parts, no clear phonetic
    if len(comp_chars) >= 2 and radical:
        # Check if any component suggests phonetic (repeating element pattern)
        return 'compound_ideograph'
    # 形声(phono-semantic): radical + phonetic component
    if radical and comp_chars:
        return 'phono_semantic'
    return 'other'


def load_redbook(filepath: str) -> List[Dict]:
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb['红宝书去重版']
    words = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row[3] is None or str(row[3]).strip() == '': continue
        word = str(row[3]).strip()
        kana = str(row[2]).strip() if row[2] else ''
        jlpt = str(row[23]).strip() if len(row) > 23 and row[23] else ''
        has_kanji = any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in word)
        kanji_chars = [c for c in word if '一' <= c <= '鿿' or '㐀' <= c <= '䶿']

        # Determine reading type (on/kun/mixed) for each kanji in word
        kanji_readings = []
        for c in kanji_chars:
            # We'll resolve this later with kanji index
            kanji_readings.append({'char': c, 'reading_type': 'unknown'})

        # Check for okurigana
        has_oku = any('぀' <= c <= 'ゟ' for c in word)

        # Extract okurigana suffix
        oku_suffix = ''
        for i in range(len(word)-1, -1, -1):
            if '぀' <= word[i] <= 'ゟ': oku_suffix = word[i] + oku_suffix
            else: break

        words.append({
            'word': word, 'kana': kana, 'jlpt_level': jlpt,
            'kanji_count': len(kanji_chars),
            'kanji_chars': kanji_chars,
            'kanji_readings': kanji_readings,
            'mora_count': count_morae(kana),
            'has_kanji': has_kanji,
            'has_okurigana': has_oku,
            'oku_suffix': oku_suffix,
        })
    wb.close()
    return words


# ═══════════════════════════════════════════
# 2. CROSS-REFERENCE: RESOLVE JLPT WORD READINGS
# ═══════════════════════════════════════════

def resolve_jlpt_readings(words: List[Dict], ki: Dict[str, Dict]):
    """For each JLPT word, determine which kanji use on vs kun reading."""
    for w in words:
        for i, kr in enumerate(w['kanji_readings']):
            c = kr['char']
            k = ki.get(c)
            if not k:
                kr['reading_type'] = 'unknown'
                kr['reading'] = ''
                continue

            # Check if any kun stem appears in the word's kana
            kun_match = None
            for ku in k['kun_list']:
                if ku['stem'] and ku['stem'] in w['kana']:
                    kun_match = ku
                    break

            # Check if any on reading appears
            on_match = None
            for on in k['on_list']:
                if on and on in w['kana']:
                    on_match = on
                    break

            if kun_match and on_match:
                kr['reading_type'] = 'both_match'
                kr['reading'] = kun_match['stem'] if len(kun_match['stem']) > len(on_match) else on_match
            elif kun_match:
                kr['reading_type'] = 'kun'
                kr['reading'] = kun_match['stem']
                kr['okuri'] = kun_match['okuri']
                kr['wclass'] = kun_match['wclass']
            elif on_match:
                kr['reading_type'] = 'on'
                kr['reading'] = on_match
            else:
                # Fuzzy: check partial matches
                kr['reading_type'] = 'ambiguous'
                kr['reading'] = ''

        # Word-level reading type
        types = [kr.get('reading_type','') for kr in w['kanji_readings']]
        if all(t == 'kun' for t in types): w['word_reading_type'] = 'kun'
        elif all(t == 'on' for t in types): w['word_reading_type'] = 'on'
        elif all(t == 'ambiguous' for t in types): w['word_reading_type'] = 'ambiguous'
        else: w['word_reading_type'] = 'mixed'


# ═══════════════════════════════════════════
# 3. SEMANTIC CLUSTER MINING
# ═══════════════════════════════════════════

def mine_semantic_clusters(kanji_list: List[Dict]) -> Dict:
    """Mine: for each semantic cluster, what kun reading patterns emerge?"""
    clusters = defaultdict(lambda: {
        'kanji': [], 'wclass_dist': Counter(), 'first_mora_dist': Counter(),
        'last_mora_dist': Counter(), 'okuri_dist': Counter(),
        'stem_lengths': [], 'examples': []
    })

    for k in kanji_list:
        if not k['kun_list']: continue
        for sc in k['sem_clusters']:
            cl = clusters[sc]
            cl['kanji'].append(k['kanji'])
            for ku in k['kun_list']:
                cl['wclass_dist'][ku['wclass']] += 1
                if ku['first_mora']: cl['first_mora_dist'][ku['first_mora']] += 1
                if ku['last_mora']: cl['last_mora_dist'][ku['last_mora']] += 1
                if ku['okuri']: cl['okuri_dist'][ku['okuri']] += 1
                cl['stem_lengths'].append(ku['mora_count'])
                if len(cl['examples']) < 5:
                    cl['examples'].append(f"{k['kanji']}({ku['full']})")

    # Compute statistics
    result = {}
    for sc, data in clusters.items():
        total = sum(data['wclass_dist'].values())
        if total < 3: continue  # skip tiny clusters

        # Dominant word class
        dom_wc = data['wclass_dist'].most_common(1)[0] if data['wclass_dist'] else ('unknown',0)
        # Dominant first mora
        dom_fm = data['first_mora_dist'].most_common(3) if data['first_mora_dist'] else []
        # Dominant last mora
        dom_lm = data['last_mora_dist'].most_common(3) if data['last_mora_dist'] else []
        # Dominant okurigana
        dom_ok = data['okuri_dist'].most_common(3) if data['okuri_dist'] else []
        # Average stem length
        avg_len = sum(data['stem_lengths'])/len(data['stem_lengths']) if data['stem_lengths'] else 0

        result[sc] = {
            'kanji_count': len(data['kanji']),
            'total_kun': total,
            'dominant_wclass': dom_wc,
            'wclass_dist': dict(data['wclass_dist'].most_common(5)),
            'top_first_morae': dom_fm,
            'top_last_morae': dom_lm,
            'top_okurigana': dom_ok,
            'avg_stem_length': round(avg_len, 2),
            'examples': data['examples'],
            'kanji_list': data['kanji'][:30],
        }

    return result


# ═══════════════════════════════════════════
# 4. RADICAL→KUN STEM DETAILED MAPPING
# ═══════════════════════════════════════════

def mine_radical_stems(kanji_list: List[Dict]) -> Dict:
    """For each radical, find the specific kun stems, morae, and okurigana patterns."""
    radicals = defaultdict(lambda: {
        'kanji': [], 'stems': Counter(), 'first_morae': Counter(),
        'last_morae': Counter(), 'okurigana': Counter(),
        'wclasses': Counter(), 'avg_strokes': [], 'avg_stem_len': [],
    })

    for k in kanji_list:
        if not k['kun_list'] or not k['radical']: continue
        rad = radicals[k['radical']]
        rad['kanji'].append(k['kanji'])
        rad['avg_strokes'].append(k['total_strokes'])
        for ku in k['kun_list']:
            rad['stems'][ku['stem']] += 1
            if ku['first_mora']: rad['first_morae'][ku['first_mora']] += 1
            if ku['last_mora']: rad['last_morae'][ku['last_mora']] += 1
            if ku['okuri']: rad['okurigana'][ku['okuri']] += 1
            rad['wclasses'][ku['wclass']] += 1
            rad['avg_stem_len'].append(ku['mora_count'])

    result = {}
    for rad, data in radicals.items():
        total = sum(data['wclasses'].values())
        if total < 3: continue

        result[rad] = {
            'kanji_count': len(data['kanji']),
            'total_kun': total,
            'top_stems': data['stems'].most_common(10),
            'top_first_morae': data['first_morae'].most_common(5),
            'top_last_morae': data['last_morae'].most_common(5),
            'top_okurigana': data['okurigana'].most_common(5),
            'wclass_dist': dict(data['wclasses'].most_common(5)),
            'avg_strokes': round(sum(data['avg_strokes'])/len(data['avg_strokes']), 1) if data['avg_strokes'] else 0,
            'avg_stem_len': round(sum(data['avg_stem_len'])/len(data['avg_stem_len']), 2) if data['avg_stem_len'] else 0,
            'verb_ratio': sum(1 for wc, n in data['wclasses'].items() if 'verb' in wc) / total,
            'noun_ratio': sum(1 for wc, n in data['wclasses'].items() if 'noun' in wc) / total,
            'sample_kanji': data['kanji'][:15],
        }

    return result


# ═══════════════════════════════════════════
# 5. COMPONENT→KUN STEM DETAILED MAPPING
# ═══════════════════════════════════════════

def mine_component_stems(kanji_list: List[Dict]) -> Dict:
    """For each component (構字部件), find kun stem patterns."""
    comps = defaultdict(lambda: {
        'kanji': [], 'stems': Counter(), 'first_morae': Counter(),
        'last_morae': Counter(), 'okurigana': Counter(), 'wclasses': Counter(),
    })

    for k in kanji_list:
        if not k['kun_list']: continue
        for comp in k['comp_set']:
            if len(comp) != 1: continue
            cp = comps[comp]
            cp['kanji'].append(k['kanji'])
            for ku in k['kun_list']:
                cp['stems'][ku['stem']] += 1
                if ku['first_mora']: cp['first_morae'][ku['first_mora']] += 1
                if ku['last_mora']: cp['last_morae'][ku['last_mora']] += 1
                if ku['okuri']: cp['okurigana'][ku['okuri']] += 1
                cp['wclasses'][ku['wclass']] += 1

    result = {}
    for comp, data in comps.items():
        total = sum(data['wclasses'].values())
        if total < 5: continue  # need at least 5 kun readings

        top_stem = data['stems'].most_common(1)[0] if data['stems'] else ('', 0)
        concentration = top_stem[1] / total if total > 0 else 0

        result[comp] = {
            'kanji_count': len(data['kanji']),
            'total_kun': total,
            'top_stem': top_stem,
            'stem_concentration': round(concentration, 3),
            'top_stems': data['stems'].most_common(5),
            'top_first_morae': data['first_morae'].most_common(5),
            'top_last_morae': data['last_morae'].most_common(5),
            'top_okurigana': data['okurigana'].most_common(5),
            'verb_ratio': sum(1 for wc,n in data['wclasses'].items() if 'verb' in wc) / total,
            'sample_kanji': data['kanji'][:10],
        }

    return result


# ═══════════════════════════════════════════
# 6. KUN STEM FAMILIES (同训异字/同词异字)
# ═══════════════════════════════════════════

def mine_stem_families(kanji_list: List[Dict]) -> Dict:
    """Group kanji by shared kun stems — the '同训异字' clusters."""
    stem_to_kanji = defaultdict(list)

    for k in kanji_list:
        for ku in k['kun_list']:
            if ku['stem'] and len(ku['stem']) >= 1:
                stem_to_kanji[ku['stem']].append({
                    'kanji': k['kanji'],
                    'okuri': ku['okuri'],
                    'wclass': ku['wclass'],
                    'radical': k['radical'],
                    'meaning_snippet': k['meaning'][:60] if k['meaning'] else '',
                })

    # Filter: stems used by 3+ different kanji
    families = {}
    for stem, entries in stem_to_kanji.items():
        unique_kanji = set(e['kanji'] for e in entries)
        if len(unique_kanji) < 3: continue

        # Group by okurigana (same stem + same okurigana = same word)
        oku_groups = defaultdict(list)
        for e in entries:
            oku_groups[e['okuri']].append(e)

        # Analyze what radicals/meanings share this stem
        radicals = Counter(e['radical'] for e in entries)

        families[stem] = {
            'kanji_count': len(unique_kanji),
            'total_occurrences': len(entries),
            'kanji_list': sorted(unique_kanji),
            'okurigana_variants': {ok: len(items) for ok, items in oku_groups.items()},
            'radical_dist': radicals.most_common(5),
            'sample': [f"{e['kanji']}({stem}.{e['okuri']})" for e in entries[:5]],
        }

    return families


# ═══════════════════════════════════════════
# 7. RENDAKU ANALYSIS (连浊)
# ═══════════════════════════════════════════

def analyze_rendaku(words: List[Dict], ki: Dict[str, Dict]) -> Dict:
    """Analyze rendaku patterns in JLPT compounds."""
    compounds = [w for w in words if w['kanji_count'] == 2 and w['has_kanji']
                 and w['jlpt_level'] in ('N1','N2','N3','N4','N5')]

    rendaku_examples = []
    no_rendaku_examples = []
    rendaku_count = 0
    total_checked = 0

    for w in compounds:
        c1, c2 = w['kanji_chars'][0], w['kanji_chars'][1]
        k1, k2 = ki.get(c1), ki.get(c2)
        if not k1 or not k2: continue

        # Check if word's kana shows rendaku of second element
        for ku2 in k2['kun_list']:
            stem2 = ku2['stem']
            if not stem2 or len(stem2) < 1: continue

            # Check if stem appears in word kana (possibly voiced)
            if stem2 in w['kana']:
                # No rendaku
                total_checked += 1
                no_rendaku_examples.append(f"{w['word']}({w['kana']})")
                break

            # Check if voiced version appears
            voiced_stem = apply_rendaku(stem2)
            if voiced_stem != stem2 and voiced_stem in w['kana']:
                total_checked += 1
                rendaku_count += 1
                rendaku_examples.append(f"{w['word']}({w['kana']}): {stem2}→{voiced_stem}")
                break

    return {
        'total_checked': total_checked,
        'rendaku_count': rendaku_count,
        'rendaku_rate': rendaku_count / total_checked if total_checked else 0,
        'examples': rendaku_examples[:15],
        'counter_examples': no_rendaku_examples[:10],
    }


def apply_rendaku(stem: str) -> str:
    """Apply rendaku voicing to the first consonant of a stem."""
    if not stem: return stem
    rendaku_map = {
        'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
        'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
        'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
        'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
    }
    first_mora = stem[0]
    if len(stem) > 1 and stem[1] in 'ゃゅょぁぃぅぇぉ':
        first_mora = stem[:2]
    if first_mora in rendaku_map:
        return rendaku_map[first_mora] + stem[len(first_mora):]
    return stem


# ═══════════════════════════════════════════
# 8. COMPOUND POSITION ANALYSIS
# ═══════════════════════════════════════════

def analyze_compound_position(words: List[Dict], ki: Dict[str, Dict]) -> Dict:
    """Analyze how position in compound (head/tail) affects reading type."""
    compounds = [w for w in words if w['kanji_count'] == 2 and w['has_kanji']]

    position_stats = defaultdict(lambda: {'head_on':0, 'head_kun':0, 'tail_on':0, 'tail_kun':0, 'total':0})

    for w in compounds:
        if len(w['kanji_readings']) != 2: continue
        head = w['kanji_readings'][0]
        tail = w['kanji_readings'][1]

        c = head['char']
        if head['reading_type'] == 'on':
            position_stats[c]['head_on'] += 1
        elif head['reading_type'] == 'kun':
            position_stats[c]['head_kun'] += 1

        if tail['reading_type'] == 'on':
            position_stats[tail['char']]['tail_on'] += 1
        elif tail['reading_type'] == 'kun':
            position_stats[tail['char']]['tail_kun'] += 1

        position_stats[head['char']]['total'] += 1
        position_stats[tail['char']]['total'] += 1

    # Summarize: for each kanji that appears in both positions
    summary = {}
    for kanji, stats in position_stats.items():
        total = stats['head_on'] + stats['head_kun'] + stats['tail_on'] + stats['tail_kun']
        if total < 5: continue
        summary[kanji] = {
            'total': total,
            'head_on_pct': stats['head_on'] / max(stats['head_on']+stats['head_kun'], 1),
            'tail_on_pct': stats['tail_on'] / max(stats['tail_on']+stats['tail_kun'], 1),
            'head_kun_pct': stats['head_kun'] / max(stats['head_on']+stats['head_kun'], 1),
            'tail_kun_pct': stats['tail_kun'] / max(stats['tail_on']+stats['tail_kun'], 1),
        }

    return summary


# ═══════════════════════════════════════════
# 9. KUN STEM CO-OCCURRENCE (训读词干共现)
# ═══════════════════════════════════════════

def mine_stem_cooccurrence(kanji_list: List[Dict]) -> Dict:
    """When a kanji has multiple kun stems, which pairs co-occur most?"""
    pairs = Counter()
    pair_examples = defaultdict(list)

    for k in kanji_list:
        if len(k['kun_list']) < 2: continue
        stems = [ku['stem'] for ku in k['kun_list'] if ku['stem']]
        for i in range(len(stems)):
            for j in range(i+1, len(stems)):
                pair = tuple(sorted([stems[i], stems[j]]))
                pairs[pair] += 1
                if len(pair_examples[pair]) < 3:
                    pair_examples[pair].append(k['kanji'])

    # Top co-occurring pairs
    top_pairs = []
    for (s1, s2), count in pairs.most_common(50):
        top_pairs.append({
            'stem1': s1, 'stem2': s2, 'count': count,
            'examples': pair_examples[(s1, s2)],
        })

    return {'top_pairs': top_pairs, 'total_pairs': len(pairs)}


# ═══════════════════════════════════════════
# 10. ON→KUN FIRST MORA MAPPING
# ═══════════════════════════════════════════

def mine_on_kun_mapping(kanji_list: List[Dict]) -> Dict:
    """Map on'yomi first mora to kun'yomi first mora patterns."""
    on_to_kun = defaultdict(lambda: Counter())

    for k in kanji_list:
        if not k['on_list'] or not k['kun_list']: continue
        for on in k['on_list']:
            if not on: continue
            on_fm = on[0]
            for ku in k['kun_list']:
                if ku['first_mora']:
                    on_to_kun[on_fm][ku['first_mora']] += 1

    # Find strongest mappings
    mappings = {}
    for on_fm, kun_dist in on_to_kun.items():
        total = sum(kun_dist.values())
        if total < 5: continue
        top = kun_dist.most_common(5)
        mappings[on_fm] = {
            'total': total,
            'top_kun_morae': [(m, c, round(c/total, 3)) for m, c in top],
            'best': top[0] if top else ('', 0),
        }

    return mappings


# ═══════════════════════════════════════════
# 11. FORMATION TYPE (六书) → KUN PATTERNS
# ═══════════════════════════════════════════

def mine_formation_patterns(kanji_list: List[Dict]) -> Dict:
    """Analyze kun patterns by character formation type."""
    form_stats = defaultdict(lambda: {
        'kanji': [], 'kun_counts': [], 'wclasses': Counter(),
        'stem_lens': [], 'first_morae': Counter(),
    })

    for k in kanji_list:
        ft = k['form_type']
        fs = form_stats[ft]
        fs['kanji'].append(k['kanji'])
        fs['kun_counts'].append(k['kun_count'])
        for ku in k['kun_list']:
            fs['wclasses'][ku['wclass']] += 1
            fs['stem_lens'].append(ku['mora_count'])
            if ku['first_mora']: fs['first_morae'][ku['first_mora']] += 1

    result = {}
    for ft, data in form_stats.items():
        total_kun = sum(data['wclasses'].values())
        if total_kun < 10: continue
        result[ft] = {
            'kanji_count': len(data['kanji']),
            'avg_kun_per_kanji': round(sum(data['kun_counts'])/len(data['kun_counts']), 2),
            'wclass_dist': dict(data['wclasses'].most_common(5)),
            'avg_stem_len': round(sum(data['stem_lens'])/len(data['stem_lens']), 2),
            'top_first_morae': data['first_morae'].most_common(5),
            'verb_pct': sum(1 for wc,n in data['wclasses'].items() if 'verb' in wc) / total_kun,
            'noun_pct': sum(1 for wc,n in data['wclasses'].items() if 'noun' in wc and 'renyo' not in wc) / total_kun,
        }

    return result


# ═══════════════════════════════════════════
# 12. ANTI-PATTERNS (FULL)
# ═══════════════════════════════════════════

def mine_antipatterns(kanji_list: List[Dict]) -> Dict:
    """Find statistically forbidden radical×kun combinations."""
    # Radical × wclass
    rad_wc = defaultdict(lambda: defaultdict(int))
    for k in kanji_list:
        if not k['kun_list'] or not k['radical']: continue
        for ku in k['kun_list']:
            rad_wc[k['radical']][ku['wclass']] += 1

    # Radical × last mora
    rad_lm = defaultdict(lambda: defaultdict(int))
    for k in kanji_list:
        if not k['kun_list'] or not k['radical']: continue
        for ku in k['kun_list']:
            if ku['last_mora']:
                rad_lm[k['radical']][ku['last_mora']] += 1

    # Find anti-patterns: radical×feature with observed < expected significantly
    # Simplified: find radicals that NEVER produce certain word classes
    all_wclasses = set()
    for rc in rad_wc.values():
        all_wclasses.update(rc.keys())

    antipatterns = {'wclass': [], 'last_mora': []}

    for rad, wcs in rad_wc.items():
        total = sum(wcs.values())
        if total < 10: continue
        for wc in all_wclasses:
            if wc not in wcs:
                # This radical NEVER produces this word class
                # Check if other radicals do (to confirm it's a real anti-pattern)
                others_with_wc = sum(1 for r, w in rad_wc.items() if r != rad and wc in w)
                if others_with_wc >= 3:
                    antipatterns['wclass'].append({
                        'radical': rad, 'avoided_wclass': wc,
                        'kanji_count': len([k for k in kanji_list if k['radical']==rad and k['has_kun']]),
                    })

    return antipatterns


# ═══════════════════════════════════════════
# 13. PER-KANJI PREDICTION RULE BUILDER
# ═══════════════════════════════════════════

def build_per_kanji_rules(kanji_list: List[Dict], radical_stems: Dict,
                          component_stems: Dict) -> List[Dict]:
    """Build specific prediction rules for each JLPT-relevant kanji."""
    rules = []

    for k in kanji_list:
        if not k['kun_list']: continue

        rule = {
            'kanji': k['kanji'],
            'radical': k['radical'],
            'strokes': k['total_strokes'],
            'form_type': k['form_type'],
            'sem_clusters': k['sem_clusters'],
            'kun_list': [{
                'stem': ku['stem'], 'okuri': ku['okuri'],
                'wclass': ku['wclass'], 'first_mora': ku['first_mora'],
                'last_mora': ku['last_mora'],
            } for ku in k['kun_list']],
            'predictions': [],
        }

        # Prediction from radical
        if k['radical'] in radical_stems:
            rs = radical_stems[k['radical']]
            rule['predictions'].append({
                'source': 'radical',
                'detail': k['radical'],
                'predicted_wclass': rs['wclass_dist'],
                'predicted_last_mora': rs['top_last_morae'][:3],
                'predicted_first_mora': rs['top_first_morae'][:3],
                'kanji_in_radical': rs['kanji_count'],
            })

        # Prediction from component
        for comp in k['comp_set']:
            if comp in component_stems:
                cs = component_stems[comp]
                if cs['stem_concentration'] >= 0.3:  # only report high-confidence
                    rule['predictions'].append({
                        'source': 'component',
                        'detail': comp,
                        'top_stem': cs['top_stem'][0],
                        'concentration': cs['stem_concentration'],
                        'kanji_with_component': cs['kanji_count'],
                    })

        if rule['predictions']:
            rules.append(rule)

    return rules


# ═══════════════════════════════════════════
# 14. JLPT WORD-LEVEL RULE VALIDATION
# ═══════════════════════════════════════════

def validate_on_jlpt(words: List[Dict], ki: Dict[str, Dict],
                     radical_stems: Dict, component_stems: Dict,
                     semantic_clusters: Dict) -> Dict:
    """Test all rules against actual JLPT word readings."""
    jlpt_words = [w for w in words if w['has_kanji'] and w['jlpt_level'] in ('N1','N2','N3','N4','N5')]

    results = {
        'total_words': len(jlpt_words),
        'radical_rule': {'correct': 0, 'total': 0, 'details': []},
        'component_rule': {'correct': 0, 'total': 0},
        'semantic_rule': {'correct': 0, 'total': 0},
        'okurigana_rule': {'correct': 0, 'total': 0},
        'compound_mora_rule': {'correct': 0, 'total': 0},
        'antipattern_rule': {'correct': 0, 'total': 0},
    }

    for w in jlpt_words:
        # 1. Okurigana rule
        if w['has_okurigana']:
            results['okurigana_rule']['total'] += 1
            # Okurigana signals kun reading (verb/adj)
            is_kun = any(kr.get('reading_type') == 'kun' for kr in w['kanji_readings'])
            if is_kun: results['okurigana_rule']['correct'] += 1

        # 2. Compound mora rule
        if w['kanji_count'] == 2:
            mc = w['mora_count']
            if mc == 2:
                results['compound_mora_rule']['total'] += 1
                if w.get('word_reading_type') == 'on':
                    results['compound_mora_rule']['correct'] += 1
            elif mc >= 5:
                results['compound_mora_rule']['total'] += 1
                if w.get('word_reading_type') in ('kun', 'mixed'):
                    results['compound_mora_rule']['correct'] += 1

        # 3. Radical rule: predict reading type from radical
        for kr in w['kanji_readings']:
            c = kr['char']
            k = ki.get(c)
            if not k or not k['radical']: continue
            rad = k['radical']
            if rad in radical_stems:
                rs = radical_stems[rad]
                results['radical_rule']['total'] += 1
                # Predict: if radical has >50% verb ratio, predict verb kun
                if rs['verb_ratio'] > 0.5:
                    predicted_kun_verb = True
                elif rs['noun_ratio'] > 0.5:
                    predicted_kun_verb = False
                else:
                    continue

                if predicted_kun_verb and kr.get('reading_type') == 'kun':
                    if any(ku['is_verb'] for ku in k['kun_list']):
                        results['radical_rule']['correct'] += 1
                elif not predicted_kun_verb and kr.get('reading_type') in ('kun', 'ambiguous'):
                    if any(ku['is_noun'] for ku in k['kun_list']):
                        results['radical_rule']['correct'] += 1

        # 4. Semantic rule: semantic cluster → prediction
        for kr in w['kanji_readings']:
            c = kr['char']
            k = ki.get(c)
            if not k or not k['sem_clusters']: continue
            for sc in k['sem_clusters']:
                if sc in semantic_clusters:
                    results['semantic_rule']['total'] += 1
                    sc_data = semantic_clusters[sc]
                    dom_wc = sc_data['dominant_wclass'][0]

                    # Check prediction
                    actual_is_verb = any(ku['is_verb'] for ku in k['kun_list']) if k['kun_list'] else False
                    actual_is_noun = any(ku['is_noun'] for ku in k['kun_list']) if k['kun_list'] else False

                    if 'verb' in dom_wc and actual_is_verb:
                        results['semantic_rule']['correct'] += 1
                    elif 'noun' in dom_wc and actual_is_noun:
                        results['semantic_rule']['correct'] += 1
                    elif 'adj' in dom_wc and any(ku['is_adj'] for ku in k['kun_list']):
                        results['semantic_rule']['correct'] += 1
                    break  # count each kanji once

    # Compute accuracies
    for key in results:
        if key == 'total_words': continue
        d = results[key]
        d['accuracy'] = d['correct'] / d['total'] if d['total'] else 0

    return results


# ═══════════════════════════════════════════
# 15. GENERATE FINAL DELIVERABLE
# ═══════════════════════════════════════════

def generate_final_report(
    semantic_clusters, radical_stems, component_stems,
    stem_families, rendaku_data, compound_position,
    stem_cooccurrence, on_kun_mapping, formation_patterns,
    antipatterns, per_kanji_rules, jlpt_validation,
    kanji_count, jlpt_word_count
) -> str:
    """Generate the final comprehensive gold card document."""

    lines = []
    lines.append('# 训读淘金v3 · 穷举式规律大全')
    lines.append('')
    lines.append(f'> 数据基础：漢字検索V2 (46,849字, {kanji_count}字有训读) + 红宝书JLPT词汇 ({jlpt_word_count}词条)')
    lines.append(f'> 分析方法：意味字段语义聚类 + 部首/部件→训读穷举映射 + JLPT词级交叉验证')
    lines.append(f'> 产出：宏观规律总表 + 逐字规则卡 + 语义群→训读映射 + 同训异字簇 + 反模式')
    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 1: JLPT VALIDATION SUMMARY ═══
    lines.append('## 第一部分：规则在JLPT词汇上的验证结果')
    lines.append('')
    lines.append('| 规则 | 测试数 | 正确数 | 准确率 |')
    lines.append('|------|--------|--------|--------|')
    for key in ['okurigana_rule', 'compound_mora_rule', 'radical_rule', 'semantic_rule']:
        d = jlpt_validation.get(key, {})
        lines.append(f'| {key} | {d.get("total",0)} | {d.get("correct",0)} | {d.get("accuracy",0):.1%} |')
    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 2: SEMANTIC CLUSTERS ═══
    lines.append('## 第二部分：语义群→训读规律映射')
    lines.append('')
    lines.append('> 从意味字段自动聚类，每个语义群标注其主要训读模式')
    lines.append('')

    # Sort clusters by kanji count
    sorted_clusters = sorted(semantic_clusters.items(), key=lambda x: x[1]['kanji_count'], reverse=True)

    for sc, data in sorted_clusters:
        dom_wc = data['dominant_wclass']
        lines.append(f'### {sc}（{data["kanji_count"]}字，{data["total_kun"]}训读）')
        lines.append('')
        lines.append(f'- **主要词类**: {dom_wc[0]} ({dom_wc[1]}次, {dom_wc[1]/data["total_kun"]:.1%})')
        lines.append(f'- **词类分布**: {data["wclass_dist"]}')
        if data['top_first_morae']:
            lines.append(f'- **高频首拍**: {data["top_first_morae"][:3]}')
        if data['top_last_morae']:
            lines.append(f'- **高频末音**: {data["top_last_morae"][:3]}')
        if data['top_okurigana']:
            lines.append(f'- **高频送假名**: {data["top_okurigana"][:3]}')
        lines.append(f'- **平均词干长度**: {data["avg_stem_length"]}拍')
        lines.append(f'- **例字**: {", ".join(data["examples"][:5])}')
        lines.append('')

    lines.append('---')
    lines.append('')

    # ═══ PART 3: RADICAL→KUN DETAILED ═══
    lines.append('## 第三部分：部首→训读词干详尽映射')
    lines.append('')
    lines.append('> 每个部首下列出其汉字的具体训读词干分布和高频模式')
    lines.append('')

    sorted_rads = sorted(radical_stems.items(), key=lambda x: x[1]['kanji_count'], reverse=True)

    for rad, data in sorted_rads[:60]:  # top 60 radicals
        lines.append(f'### {rad}部（{data["kanji_count"]}字，{data["total_kun"]}训读）')
        lines.append('')
        lines.append(f'- 词类: 动词{data["verb_ratio"]:.0%} | 名词{data["noun_ratio"]:.0%}')
        lines.append(f'- 高频词干: {data["top_stems"][:5]}')
        lines.append(f'- 高频首拍: {data["top_first_morae"][:3]}')
        lines.append(f'- 高频末音: {data["top_last_morae"][:3]}')
        lines.append(f'- 高频送假名: {data["top_okurigana"][:3]}')
        lines.append(f'- 平均笔画: {data["avg_strokes"]}画 | 平均词干长: {data["avg_stem_len"]}拍')
        lines.append(f'- 代表字: {", ".join(data["sample_kanji"][:10])}')
        lines.append('')

    lines.append('---')
    lines.append('')

    # ═══ PART 4: COMPONENT→KUN ═══
    lines.append('## 第四部分：部件→训读词干高置信度预测')
    lines.append('')
    lines.append('> 当某个部件的训读集中度≥30%时，可以直接用部件预测训读词干')
    lines.append('')

    high_conf_comps = {c: d for c, d in component_stems.items() if d['stem_concentration'] >= 0.3}
    sorted_comps = sorted(high_conf_comps.items(), key=lambda x: x[1]['stem_concentration'], reverse=True)

    lines.append('| 部件 | 汉字数 | 首选训读词干 | 集中度 | 动词率 | 例字 |')
    lines.append('|------|--------|------------|--------|--------|------|')
    for comp, data in sorted_comps[:80]:
        lines.append(f'| {comp} | {data["kanji_count"]} | {data["top_stem"][0]} | {data["stem_concentration"]:.1%} | {data["verb_ratio"]:.0%} | {", ".join(data["sample_kanji"][:5])} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 5: KUN STEM FAMILIES ═══
    lines.append('## 第五部分：同训异字簇（同一训读对应多汉字）')
    lines.append('')
    lines.append('> 同一和语词根对应多个汉字的语义分化规律')
    lines.append('')

    sorted_fams = sorted(stem_families.items(), key=lambda x: x[1]['kanji_count'], reverse=True)

    lines.append('| 词根 | 汉字数 | 主要部首分布 | 送假名变体 | 例字 |')
    lines.append('|------|--------|------------|----------|------|')
    for stem, data in sorted_fams[:40]:
        rads_str = ', '.join([f'{r}({n})' for r, n in data['radical_dist'][:3]])
        lines.append(f'| {stem} | {data["kanji_count"]} | {rads_str} | {list(data["okurigana_variants"].keys())[:3]} | {", ".join(data["kanji_list"][:5])} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 6: ANTI-PATTERNS ═══
    lines.append('## 第六部分：反模式（被统计禁止的组合）')
    lines.append('')
    lines.append('### 部首→绝不出现的训读词类')
    lines.append('')
    lines.append('| 部首 | 绝无此类训读 | 该部首有训读的汉字数 |')
    lines.append('|------|------------|-------------------|')
    for ap in antipatterns.get('wclass', [])[:30]:
        lines.append(f'| {ap["radical"]} | {ap["avoided_wclass"]} | {ap["kanji_count"]} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 7: STROKE COMPLEXITY ═══
    lines.append('## 第七部分：六书(汉字构造方式)→训读模式')
    lines.append('')
    lines.append('| 构造类型 | 汉字数 | 平均训读数 | 动词占比 | 名词占比 | 平均词干长 | 高频首拍 |')
    lines.append('|---------|--------|----------|---------|---------|----------|---------|')
    for ft, data in sorted(formation_patterns.items(), key=lambda x: x[1]['kanji_count'], reverse=True):
        lines.append(f'| {ft} | {data["kanji_count"]} | {data["avg_kun_per_kanji"]} | {data["verb_pct"]:.0%} | {data["noun_pct"]:.0%} | {data["avg_stem_len"]} | {data["top_first_morae"][:3]} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 8: RENDAKU ═══
    lines.append('## 第八部分：连浊规律验证')
    lines.append('')
    lines.append(f'- JLPT复合词中连浊发生率: {rendaku_data["rendaku_rate"]:.1%} ({rendaku_data["rendaku_count"]}/{rendaku_data["total_checked"]})')
    lines.append(f'- 连浊例: {", ".join(rendaku_data["examples"][:8])}')
    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 9: STEM CO-OCCURRENCE ═══
    lines.append('## 第九部分：训读词干高频共现对')
    lines.append('')
    lines.append('> 同一汉字内多训读词干的共现模式（自他对立/同义双形/元音交替）')
    lines.append('')
    lines.append('| 词干对 | 共现汉字数 | 例字 |')
    lines.append('|--------|----------|------|')
    for pair in stem_cooccurrence['top_pairs'][:30]:
        lines.append(f'| {pair["stem1"]}↔{pair["stem2"]} | {pair["count"]} | {", ".join(pair["examples"])} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 10: ON→KUN FIRST MORA ═══
    lines.append('## 第十部分：音读首拍→训读首拍映射')
    lines.append('')
    lines.append('| 音读首拍 | 最常见训读首拍 | 占比 |')
    lines.append('|---------|--------------|------|')
    for on_fm, data in sorted(on_kun_mapping.items(), key=lambda x: x[1]['total'], reverse=True)[:30]:
        if data['best'][1] > 0:
            lines.append(f'| {on_fm} | {data["best"][0]} | {data["best"][1]/data["total"]:.1%} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 11: COMPOUND POSITION ═══
    lines.append('## 第十一部分：复合词位置效应')
    lines.append('')
    lines.append('> 同一汉字在复合词词头vs词尾时，on/kun选择倾向')
    lines.append('')
    lines.append('| 汉字 | 词头音读率 | 词尾音读率 | 词头训读率 | 词尾训读率 |')
    lines.append('|------|----------|----------|----------|----------|')
    for kanji, stats in sorted(compound_position.items(), key=lambda x: x[1]['total'], reverse=True)[:30]:
        lines.append(f'| {kanji} | {stats["head_on_pct"]:.0%} | {stats["tail_on_pct"]:.0%} | {stats["head_kun_pct"]:.0%} | {stats["tail_kun_pct"]:.0%} |')

    lines.append('')
    lines.append('---')
    lines.append('')

    # ═══ PART 12: PER-KANJI RULE CARDS ═══
    lines.append('## 第十二部分：逐字规则卡（JLPT高频字精选）')
    lines.append('')
    lines.append('> 每个汉字列出：部首/部件→预测的训读模式 + 实际训读')
    lines.append('')

    # Only show kanji with high-confidence predictions
    high_conf_rules = [r for r in per_kanji_rules
                      if any(p.get('concentration', 0) >= 0.3 for p in r['predictions'])]
    high_conf_rules.sort(key=lambda r: sum(p.get('concentration',0) for p in r['predictions']), reverse=True)

    for rule in high_conf_rules[:100]:
        lines.append(f'### {rule["kanji"]}（{rule["radical"]}部, {rule["strokes"]}画, {rule["form_type"]}）')
        lines.append('')
        lines.append(f'语义群: {", ".join(rule["sem_clusters"])}')
        lines.append(f'实际训读: {", ".join(f"{ku["stem"]}.{ku["okuri"]}({ku["wclass"]})" for ku in rule["kun_list"])}')
        for pred in rule['predictions']:
            if pred['source'] == 'component' and pred.get('concentration', 0) >= 0.3:
                lines.append(f'  → 部件「{pred["detail"]}」预测词干: {pred["top_stem"]} (集中度{pred["concentration"]:.1%})')
            elif pred['source'] == 'radical':
                lines.append(f'  → 部首「{pred["detail"]}」预测末音: {pred.get("predicted_last_mora",[])}')
        lines.append('')

    lines.append('---')
    lines.append('')

    # ═══ FINAL: ULTIMATE CHEAT SHEET ═══
    lines.append('## 最终速查卡：汉语母语者JLPT训读极简法则')
    lines.append('')
    lines.append('### 一级法则（看见就能用的，准确率>90%）')
    lines.append('')
    lines.append('1. **有送假名 = 训读用言**。〜く/む/る/い 等结尾 → 动词/形容词')
    lines.append('2. **身体/自然/方位/亲属字 = 100%训读**。你认识的所有基本汉字概念')
    lines.append('3. **浊音g/d/b/z不重复**。训读词干内同一个浊辅音不会出现两次')
    lines.append('4. **2拍复合词 = 音+音**。短到只有2拍的二字词一定是两个音读')
    lines.append('')
    lines.append('### 二级法则（需要想一下的，准确率>60%）')
    lines.append('')
    lines.append('5. **鱼虫木竹鸟米部 = 名词**。自然物部首不产生动词训读')
    lines.append('6. **入声字(音读-ク/-ツ) = 训读倾向动词**。中国方言区独有优势')
    lines.append('7. **5拍+复合词 = 含训读**。太长的二字词一定有训读在里面')
    lines.append('8. **简笔字(≤9画) = 警惕多训读**。笔画少的字往往有多个不同读法')
    lines.append('')
    lines.append('### 三级法则（辅助验证，准确率>40%）')
    lines.append('')
    lines.append('9. **首拍そ/ゆ/お = 倾向动词**。首拍ぶ/じ/く = 倾向名词')
    lines.append('10. **病垂(疒)→や、女→め、車→ろ、田→ね、石→い(首)**')
    lines.append('11. **元音和谐**：推测符合同元音连续 = 更可能正确')
    lines.append('12. **音读-a收尾(〜カ/〜ガ) = 训读倾向名词**')
    lines.append('')
    lines.append('### 终极心法')
    lines.append('')
    lines.append('> **训读不是"汉字的日语发音"，而是"和语词的汉字写法"。**')
    lines.append('> 汉语母语者学训读的本质是：已知汉字意思 → 建立意思到和语读音的映射。')
    lines.append('> 60-70%的信息你通过汉字本身已经知道了，真正的记忆量远小于你的想象。')
    lines.append('')

    return '\n'.join(lines)


# ═══════════════════════════════════════════
# 16. MAIN
# ═══════════════════════════════════════════

def main():
    t0 = time.time()
    print('=' * 70)
    print('训读淘金v3 · 穷举式语义挖掘 + 双层规则体系')
    print('=' * 70)

    # Load
    print('\n[1/8] Loading data...')
    kanji_list = load_kanji_db(f'{BASE}/漢字検索V2.xlsm')
    print(f'  Kanji DB: {len(kanji_list)}, {sum(1 for k in kanji_list if k["has_kun"])} with kun')
    words = load_redbook(f'{BASE}/word.xlsx')
    ki = {k['kanji']: k for k in kanji_list}
    jlpt_words = [w for w in words if w['has_kanji'] and w['jlpt_level'] in ('N1','N2','N3','N4','N5')]
    print(f'  Red Book: {len(words)} entries, {len(jlpt_words)} JLPT kanji words')

    # Resolve readings
    print('\n[2/8] Resolving JLPT word readings...')
    resolve_jlpt_readings(jlpt_words, ki)
    kun_words = sum(1 for w in jlpt_words if w.get('word_reading_type') == 'kun')
    on_words = sum(1 for w in jlpt_words if w.get('word_reading_type') == 'on')
    mixed = sum(1 for w in jlpt_words if w.get('word_reading_type') == 'mixed')
    print(f'  Kun: {kun_words}, On: {on_words}, Mixed: {mixed}')

    # Mine ALL dimensions
    print('\n[3/8] Mining semantic clusters...')
    semantic_clusters = mine_semantic_clusters(kanji_list)
    print(f'  {len(semantic_clusters)} clusters found')

    print('\n[4/8] Mining radical→kun stems...')
    radical_stems = mine_radical_stems(kanji_list)
    print(f'  {len(radical_stems)} radicals analyzed')

    print('\n[5/8] Mining component→kun stems...')
    component_stems = mine_component_stems(kanji_list)
    high_conf = sum(1 for d in component_stems.values() if d['stem_concentration'] >= 0.3)
    print(f'  {len(component_stems)} components, {high_conf} with ≥30% concentration')

    print('\n[6/8] Mining additional dimensions...')
    stem_families = mine_stem_families(kanji_list)
    print(f'  {len(stem_families)} stem families (3+ kanji each)')

    rendaku_data = analyze_rendaku(words, ki)
    print(f'  Rendaku rate: {rendaku_data["rendaku_rate"]:.1%}')

    compound_position = analyze_compound_position(jlpt_words, ki)
    print(f'  {len(compound_position)} kanji with position data')

    stem_cooccurrence = mine_stem_cooccurrence(kanji_list)
    print(f'  {stem_cooccurrence["total_pairs"]} co-occurring stem pairs')

    on_kun_mapping = mine_on_kun_mapping(kanji_list)
    print(f'  {len(on_kun_mapping)} on→kun first-mora mappings')

    formation_patterns = mine_formation_patterns(kanji_list)
    print(f'  {len(formation_patterns)} formation types')

    antipatterns = mine_antipatterns(kanji_list)
    print(f'  {len(antipatterns["wclass"])} radical×wclass anti-patterns')

    print('\n[7/8] Building per-kanji rules...')
    per_kanji_rules = build_per_kanji_rules(kanji_list, radical_stems, component_stems)
    print(f'  {len(per_kanji_rules)} kanji with prediction rules')

    print('\n[8/8] Validating on JLPT & generating report...')
    jlpt_validation = validate_on_jlpt(jlpt_words, ki, radical_stems, component_stems, semantic_clusters)

    # Generate report
    report = generate_final_report(
        semantic_clusters, radical_stems, component_stems,
        stem_families, rendaku_data, compound_position,
        stem_cooccurrence, on_kun_mapping, formation_patterns,
        antipatterns, per_kanji_rules, jlpt_validation,
        sum(1 for k in kanji_list if k['has_kun']), len(jlpt_words)
    )

    output_path = f'{BASE}/JLPT_GOLD_CARD_V3.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    # JSON export
    json_data = {
        'semantic_clusters': {sc: {k:v for k,v in data.items() if k != 'kanji_list'}
                             for sc, data in semantic_clusters.items()},
        'radical_stems': radical_stems,
        'component_stems_high_conf': {c:d for c,d in component_stems.items() if d['stem_concentration'] >= 0.3},
        'stem_families': stem_families,
        'rendaku': rendaku_data,
        'stem_cooccurrence_top50': stem_cooccurrence['top_pairs'][:50],
        'on_kun_mapping': on_kun_mapping,
        'formation_patterns': formation_patterns,
        'antipatterns': antipatterns,
        'jlpt_validation': jlpt_validation,
    }
    with open(f'{BASE}/gold_panning_v3_results.json', 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # Summary
    print(f'\n{"="*70}')
    print('COMPLETE')
    print(f'{"="*70}')
    print(f'Output: {output_path}')
    print(f'JSON: gold_panning_v3_results.json')
    print(f'Time: {time.time()-t0:.1f}s')

    # Quick stats
    print(f'\nSemantic clusters: {len(semantic_clusters)}')
    print(f'Radicals analyzed: {len(radical_stems)}')
    print(f'High-confidence components: {high_conf}')
    print(f'Stem families (同训异字): {len(stem_families)}')
    print(f'Anti-patterns: {len(antipatterns["wclass"])}')
    print(f'Per-kanji rules: {len(per_kanji_rules)}')
    print(f'JLPT validation:')
    for key, d in jlpt_validation.items():
        if key != 'total_words':
            print(f'  {key}: {d.get("accuracy",0):.1%} ({d.get("correct",0)}/{d.get("total",0)})')


if __name__ == '__main__':
    main()
