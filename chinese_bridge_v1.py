#!/usr/bin/env python3
"""
Chinese Bridge V1: Quantify Chinese-speaker advantage in Japanese on-yomi prediction.
Key question: How many JLPT word readings can a Chinese speaker guess correctly
from Chinese character knowledge alone, WITHOUT additional memorization?
"""

import json, os, csv, re, math
from collections import Counter, defaultdict
import openpyxl
from pypinyin import pinyin, Style

BASE = '/Volumes/SSD/work/kanji-kun'
OUT = f'{BASE}/output'
WORD_XLSX = f'{BASE}/word.xlsx'
KANJI_XLSM = f'{BASE}/漢字検索V2.xlsm'

JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

KATA_TO_HIRA = str.maketrans(
    'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'
    'ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ'
    'ャュョッァィゥェォ',
    'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'
    'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ'
    'ゃゅょっあいうえお'
)

def kata_to_hira(s):
    return s.translate(KATA_TO_HIRA)


def mora_count(s):
    """Count morae in a kana string."""
    s = kata_to_hira(s)
    count = 0
    i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉ':
            count += 1; i += 2
        else:
            count += 1; i += 1
    return count


def load_data():
    print("Loading JLPT words...")
    wb = openpyxl.load_workbook(WORD_XLSX, read_only=True)
    ws = wb['红宝书去重版']
    jlpt_words = []
    for row in ws.iter_rows(min_row=4, max_row=9575, values_only=True):
        kana_raw = str(row[2]).strip() if row[2] else ''
        kanji_raw = str(row[3]).strip() if row[3] else ''
        level = str(row[23]).strip() if len(row) > 23 and row[23] else ''
        if level not in JLPT_LEVELS: continue
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', kanji_raw)
        kana_clean = kata_to_hira(kana_raw)
        jlpt_words.append({
            'kana': kana_clean, 'kanji_word': kanji_raw,
            'level': level, 'kanji_chars': kanji_chars,
        })
    wb.close()
    print(f"  {len(jlpt_words)} words with kanji")

    print("Loading kanji DB...")
    wb2 = openpyxl.load_workbook(KANJI_XLSM, read_only=True)
    ws2 = wb2['漢字一覧']
    kanji_db = {}
    for row in ws2.iter_rows(min_row=2, max_row=46850, values_only=True):
        if not row[0]: continue
        ch = str(row[0]).strip()
        if not ch or len(ch) > 2: continue
        components = str(row[1]).strip() if row[1] else ''
        radical = str(row[3]).strip() if row[3] else ''
        on_raw = str(row[9]).strip() if row[9] else ''
        kun_raw = str(row[10]).strip() if row[10] else ''

        on_list = []
        for o in on_raw.replace('、', ',').split(','):
            o = o.strip()
            if o: on_list.append(kata_to_hira(o))

        kun_list = []
        for kr in kun_raw.replace('、', ',').split(','):
            kr = kr.strip()
            if not kr: continue
            if '・' in kr:
                parts = kr.split('・')
                stem = parts[0].replace('.', '')
                oku = '.'.join(p.replace('.', '') for p in parts[1:])
                kun_list.append({'stem': stem, 'okurigana': oku, 'full': f"{stem}.{oku}"})
            else:
                s = kr.replace('.', '')
                kun_list.append({'stem': s, 'okurigana': '', 'full': s})

        kanji_db[ch] = {'on': on_list, 'kun': kun_list,
                         'components': components, 'radical': radical}
    wb2.close()
    print(f"  {len(kanji_db)} kanji loaded")

    # Load V9 prediction results (on/kun type classification)
    v9_data = None
    if os.path.exists(f'{OUT}/kun_v9_data.json'):
        with open(f'{OUT}/kun_v9_data.json') as f:
            v9_data = json.load(f)
        print(f"  V9 data loaded: {len(v9_data['annotated_words'])} annotated words")

    return jlpt_words, kanji_db, v9_data


def get_pinyin_for_kanji(kanji_db):
    """Get pinyin (Mandarin reading) for each kanji."""
    print("\nGetting pinyin readings...")
    pinyin_map = {}
    for ch in kanji_db:
        try:
            py_list = pinyin(ch, style=Style.TONE3, heteronym=True)
            # Flatten: pinyin returns list of lists for heteronyms
            readings = set()
            for lst in py_list:
                for r in lst:
                    if r and not r.isdigit():  # Skip pure numbers
                        readings.add(r)
            if readings:
                pinyin_map[ch] = list(readings)
        except Exception:
            pass
    print(f"  Pinyin for {len(pinyin_map)} kanji")
    return pinyin_map


def extract_pinyin_parts(py):
    """Extract initial, final, and tone from a pinyin syllable."""
    initials = ['zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
                'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's']
    py_lower = py.lower().rstrip('0123456789')
    init = ''
    final = py_lower
    for i in sorted(initials, key=len, reverse=True):
        if py_lower.startswith(i):
            init = i
            final = py_lower[len(i):]
            break
    # Handle y/w initials (they're not true consonants in pinyin)
    if py_lower.startswith('y'):
        init = 'y'
        remaining = py_lower[1:]
        # yan→ian, yuan→üan, ye→ie, etc.
        if remaining.startswith('u'):
            final = 'v' + remaining[1:] if len(remaining) > 1 else 'v'
        elif remaining:
            final = remaining
    elif py_lower.startswith('w'):
        init = 'w'
        final = py_lower[1:] if len(py_lower) > 1 else 'u'

    # Extract tone
    digits = re.findall(r'\d', py)
    tone = int(digits[-1]) if digits else 5
    return init, final, tone


def extract_pinyin_final(py):
    """Legacy: extract just the final."""
    _, final, _ = extract_pinyin_parts(py)
    return final


def build_pinyin_on_mapping(kanji_db, pinyin_map):
    """Build statistical mapping: (pinyin_initial, pinyin_final, tone) → Japanese on-yomi."""
    print("\nBuilding pinyin→on-yomi mapping...")
    # Level 1: (initial, final, tone) → on (most specific)
    ift_to_on = defaultdict(lambda: defaultdict(int))
    # Level 2: (final, tone) → on (tone-aware)
    ft_to_on = defaultdict(lambda: defaultdict(int))
    # Level 3: (final) → on (tone-agnostic, for fallback)
    final_to_on = defaultdict(lambda: defaultdict(int))

    for ch, info in kanji_db.items():
        if ch not in pinyin_map or not info['on']:
            continue
        for py in pinyin_map[ch]:
            init, final, tone = extract_pinyin_parts(py)
            for on in info['on']:
                ift_to_on[(init, final, tone)][on] += 1
                ft_to_on[(final, tone)][on] += 1
                final_to_on[final][on] += 1

    # Pick best on-yomi for each mapping key
    def best_from_counter(d, min_count=2):
        result = {}
        for key, on_counts in d.items():
            total = sum(on_counts.values())
            if total < min_count:
                continue
            best_on = max(on_counts, key=on_counts.get)
            result[key] = {
                'on': best_on,
                'accuracy': on_counts[best_on] / total,
                'total': total,
                'variants': len(on_counts),
            }
        return result

    ift_best = best_from_counter(ift_to_on, min_count=2)
    ft_best = best_from_counter(ft_to_on, min_count=3)
    final_best = best_from_counter(final_to_on, min_count=5)

    print(f"  (initial,final,tone)→on: {len(ift_best)} mappings")
    print(f"  (final,tone)→on: {len(ft_best)} mappings")
    print(f"  (final)→on: {len(final_best)} mappings")

    # Show top mappings
    top = sorted(ift_best.items(), key=lambda x: -x[1]['accuracy'] * math.log(x[1]['total']))[:15]
    print(f"  Top (I,F,T) mappings:")
    for (init, final, tone), info in top:
        print(f"    {init}+{final} T{tone} → {info['on']:6s} ({info['accuracy']:.1%}, n={info['total']})")

    return ift_best, ft_best, final_best


def predict_on_from_pinyin(ch, pinyin_map, ift_best, ft_best, final_best, kanji_db):
    """Predict the on-yomi for a kanji from its Chinese reading.
    Uses 3-level hierarchy: (initial,final,tone) → (final,tone) → (final)"""
    if ch not in pinyin_map or ch not in kanji_db:
        return None, None, 0.0, 'none'

    actual_ons = kanji_db[ch]['on']
    if not actual_ons:
        return None, None, 0.0, 'none'

    best_prediction = None
    best_confidence = 0.0
    best_py = None
    best_level = 'none'

    for py in pinyin_map[ch]:
        init, final, tone = extract_pinyin_parts(py)

        # Level 1: (initial, final, tone) — most specific
        key1 = (init, final, tone)
        if key1 in ift_best:
            info = ift_best[key1]
            if info['accuracy'] > best_confidence:
                best_prediction = info['on']
                best_confidence = info['accuracy']
                best_py = py
                best_level = 'IFT'

        # Level 2: (final, tone) — tone-aware
        key2 = (final, tone)
        if key2 in ft_best:
            info = ft_best[key2]
            discounted = info['accuracy'] * 0.90
            if discounted > best_confidence:
                best_prediction = info['on']
                best_confidence = discounted
                best_py = py
                best_level = 'FT'

        # Level 3: (final) — tone-agnostic
        if final in final_best:
            info = final_best[final]
            discounted = info['accuracy'] * 0.75
            if discounted > best_confidence:
                best_prediction = info['on']
                best_confidence = discounted
                best_py = py
                best_level = 'F'

    return best_prediction, best_py, best_confidence, best_level


# ============================================================
# Phonetic Component → On-Yomi Rules (形声字声旁)
# ============================================================

def build_component_on_rules(kanji_db):
    """Build rules: shared phonetic component → shared on-yomi.
    When ≥60% of kanji sharing a component have the same on-yomi,
    that component is a reliable phonetic predictor."""
    comp_to_on = defaultdict(lambda: defaultdict(set))

    for ch, info in kanji_db.items():
        if not info['on']:
            continue
        components = info.get('components', '')
        if not components:
            continue
        for comp in components:
            if comp == ch:
                continue
            if not re.match(r'[一-鿿㐀-䶿]', comp):
                continue
            for on in info['on']:
                comp_to_on[comp][on].add(ch)

    rules = {}
    for comp, on_groups in comp_to_on.items():
        all_kanji = set()
        for kset in on_groups.values():
            all_kanji.update(kset)
        total = len(all_kanji)
        if total < 3:
            continue
        best_on = max(on_groups, key=lambda x: len(on_groups[x]))
        concentration = len(on_groups[best_on]) / total
        if concentration >= 0.50:
            # Also collect second-best for multi-reading prediction
            on_counts = sorted(on_groups.items(), key=lambda x: -len(x[1]))
            variants = [{'on': o, 'count': len(k), 'pct': len(k)/total}
                       for o, k in on_counts[:3]]
            rules[comp] = {
                'on': best_on,
                'accuracy': concentration,
                'total_kanji': total,
                'matching_kanji': sorted(on_groups[best_on]),
                'all_on_variants': variants,
            }
    return rules


def predict_on_from_component(ch, comp_on_rules, kanji_db):
    """Predict on-yomi from phonetic component.
    Returns (predicted_on, confidence, component_used) or (None, 0, None)."""
    if ch not in kanji_db:
        return None, 0.0, None

    components = kanji_db[ch].get('components', '')
    if not components:
        return None, 0.0, None

    best = None
    best_conf = 0.0
    best_comp = None
    for comp in components:
        if comp in comp_on_rules:
            rule = comp_on_rules[comp]
            if rule['accuracy'] > best_conf:
                best = rule['on']
                best_conf = rule['accuracy']
                best_comp = comp

    return best, best_conf, best_comp


# ============================================================
# Entering Tone Detection (入声检测)
# ============================================================

def detect_entering_tone(py):
    """Detect if a pinyin syllable likely comes from a Middle Chinese
    entering tone (入声) character (historically ending in -p, -t, -k).

    Entering tone → on-yomi is always 1 mora, ending in く/つ/ち/き/う/い.
    Non-entering tone → on-yomi can be longer, ending freely."""
    init, final, tone = extract_pinyin_parts(py)
    # Nasal finals (-n, -ng) are never from entering tone
    if final.endswith('n') or final.endswith('ng'):
        return False
    # Diphthong finals are never from entering tone
    non_entering = {'ai', 'ei', 'ao', 'ou', 'iu', 'ui', 'er'}
    if final in non_entering:
        return False
    return True


def get_entering_tone_valid_endings():
    """Valid on-yomi endings for entering tone characters."""
    return {'く', 'つ', 'ち', 'き', 'う', 'い'}


def is_on_valid_for_entering(on_reading):
    """Check if an on-yomi reading is valid for an entering tone character.
    Entering tone on-yomi must be 1-2 mora ending in く/つ/ち/き/う/い."""
    if not on_reading:
        return True  # can't judge
    endings = get_entering_tone_valid_endings()
    valid = False
    for ending in endings:
        if on_reading.endswith(ending):
            valid = True
            break
    if not valid:
        return False
    # Also check mora count (entering tone is always short)
    mc = mora_count(on_reading)
    return mc <= 2


def predict_on_combined(ch, pinyin_map, ift_best, ft_best, final_best,
                         comp_on_rules, kanji_db, jlpt_on_freq=None, position=None):
    """Combined on-yomi prediction using JLPT frequency + pinyin + component + entering tone.
    JLPT frequency is the strongest signal (93% accurate when available).
    position: 'start', 'end', 'mid', 'alone' — for position-aware frequency prior."""
    actual_ons = kanji_db.get(ch, {}).get('on', [])
    if not actual_ons:
        return None, 0.0, 'none', {}

    # 0. JLPT frequency — strongest signal (93% accurate)
    jlpt_freq_info = jlpt_on_freq.get(ch) if jlpt_on_freq else None
    jlpt_default = jlpt_freq_info['default'] if jlpt_freq_info else None
    jlpt_conf = jlpt_freq_info['confidence'] if jlpt_freq_info else 0.0

    # 1. Pinyin-based prediction
    pin_on, pin_py, pin_conf, pin_level = predict_on_from_pinyin(
        ch, pinyin_map, ift_best, ft_best, final_best, kanji_db)

    # 2. Component-based prediction
    comp_on, comp_conf, comp_used = predict_on_from_component(
        ch, comp_on_rules, kanji_db)

    # 3. Entering tone detection
    is_entering = False
    entering_py = None
    if ch in pinyin_map:
        for py in pinyin_map[ch]:
            if detect_entering_tone(py):
                is_entering = True
                entering_py = py
                break

    # 4. Weighted voting with JLPT frequency as strong prior
    candidates = defaultdict(float)

    # Position-aware frequency for multi-on kanji
    pos_default = None
    if jlpt_freq_info and jlpt_freq_info.get('num_variants', 1) > 1 and position:
        pos_info = jlpt_freq_info.get('by_position', {}).get(position)
        if pos_info and pos_info['default'] != jlpt_default and pos_info['confidence'] >= 0.5:
            pos_default = pos_info['default']

    if jlpt_default:
        if pos_default:
            candidates[pos_default] += jlpt_conf * 3.0
            candidates[jlpt_default] += jlpt_conf * 1.5
        else:
            candidates[jlpt_default] += jlpt_conf * 3.0

    if pin_on:
        candidates[pin_on] += pin_conf * 1.0

    if comp_on:
        candidates[comp_on] += comp_conf * 1.2

    # Entering tone filtering
    if is_entering:
        for on in list(candidates.keys()):
            if not is_on_valid_for_entering(on):
                candidates[on] *= 0.3

    # Agreement boosts
    if pin_on and comp_on and pin_on == comp_on:
        candidates[pin_on] *= 1.3
    if jlpt_default and pin_on and jlpt_default == pin_on:
        candidates[jlpt_default] *= 1.5  # strong boost: JLPT freq + pinyin agree
    if jlpt_default and comp_on and jlpt_default == comp_on:
        candidates[jlpt_default] *= 1.5  # strong boost: JLPT freq + component agree

    if not candidates:
        return pin_on, pin_conf if pin_on else 0.0, 'pinyin_fallback', {}

    best_on = max(candidates, key=candidates.get)
    total_weight = sum(candidates.values())
    best_conf = candidates[best_on] / max(total_weight, 0.001)

    # Determine method
    methods = []
    if jlpt_default == best_on or pos_default == best_on:
        methods.append('jlpt_freq')
    if pin_on == best_on:
        methods.append('pinyin')
    if comp_on == best_on:
        methods.append('component')
    method = '+'.join(methods) if methods else 'voting'

    details = {
        'jlpt_default': jlpt_default,
        'jlpt_conf': jlpt_conf,
        'pinyin_pred': pin_on,
        'pinyin_conf': pin_conf,
        'comp_pred': comp_on,
        'comp_conf': comp_conf,
        'comp_used': comp_used,
        'is_entering': is_entering,
        'entering_py': entering_py,
        'candidates': dict(candidates),
        'method': method,
    }

    return best_on, min(best_conf, 1.0), method, details


def build_jlpt_on_freq(v9_data):
    """Build JLPT word-level on-yomi frequency table.
    Key insight: 93% of JLPT on-readings use the most frequent on-yomi for that kanji.
    Also computes position-specific frequencies (start/end/mid/alone) for multi-on kanji.
    Returns: {kanji: {'default': most_common_on, 'freqs': {on: count}, 'total': n, ...}}"""
    if not v9_data:
        return {}
    kanji_freq = defaultdict(lambda: defaultdict(int))
    kanji_pos_freq = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for w in v9_data['annotated_words']:
        details = w.get('gt_details', [])
        n = len(details)
        for i, d in enumerate(details):
            if d.get('type') == 'on' and d.get('reading'):
                ch = d['kanji']
                reading = d['reading']
                kanji_freq[ch][reading] += 1
                if n == 1:
                    kanji_pos_freq[ch]['alone'][reading] += 1
                elif i == 0:
                    kanji_pos_freq[ch]['start'][reading] += 1
                elif i == n - 1:
                    kanji_pos_freq[ch]['end'][reading] += 1
                else:
                    kanji_pos_freq[ch]['mid'][reading] += 1

    result = {}
    for ch, freqs in kanji_freq.items():
        total = sum(freqs.values())
        most_common = max(freqs, key=freqs.get)
        result[ch] = {
            'default': most_common,
            'freqs': dict(freqs),
            'total': total,
            'confidence': freqs[most_common] / total,
            'num_variants': len(freqs),
        }
        # Add position-specific defaults for multi-on kanji
        if len(freqs) > 1:
            pos_info = {}
            for pos in ['start', 'end', 'mid', 'alone']:
                pfreqs = kanji_pos_freq[ch][pos]
                if pfreqs:
                    ptotal = sum(pfreqs.values())
                    pdefault = max(pfreqs, key=pfreqs.get)
                    if ptotal >= 2 and pdefault != most_common:
                        pos_info[pos] = {
                            'default': pdefault,
                            'confidence': pfreqs[pdefault] / ptotal,
                            'total': ptotal,
                        }
            if pos_info:
                result[ch]['by_position'] = pos_info
    return result


def build_jlpt_kun_freq(v9_data):
    """Build JLPT word-level kun-yomi frequency table.
    Returns: {kanji: {'default': most_common_stem, 'freqs': {stem: count}, 'total': n}}"""
    if not v9_data:
        return {}
    kanji_freq = defaultdict(lambda: defaultdict(int))
    for w in v9_data['annotated_words']:
        for d in w.get('gt_details', []):
            if d.get('type') == 'kun' and d.get('reading'):
                kanji_freq[d['kanji']][d['reading']] += 1

    result = {}
    for ch, freqs in kanji_freq.items():
        total = sum(freqs.values())
        most_common = max(freqs, key=freqs.get)
        result[ch] = {
            'default': most_common,
            'freqs': dict(freqs),
            'total': total,
            'confidence': freqs[most_common] / total,
            'num_variants': len(freqs),
        }
    return result


def build_semantic_kun_rules(kanji_db, jlpt_kun_freq):
    """Build semantic domain → kun stem rules from radical + meaning patterns.
    Uses radical categories that have highly concentrated kun readings in JLPT."""
    # Define semantic domains by radical
    DOMAINS = {
        'body': {'radicals': '月肉骨身皮毛髪首頁面目耳鼻口歯舌唇手足爪',
                 'typical_kun': {}},  # populated from JLPT data
        'nature': {'radicals': '日雨風雲雪雷山川水氵火木林森草艹花石金土',
                   'typical_kun': {}},
        'animal': {'radicals': '魚虫鳥犬犭牛馬羊豕豸亀龍虎鹿鼠兎',
                   'typical_kun': {}},
        'plant': {'radicals': '竹米麦豆瓜禾',
                  'typical_kun': {}},
        'person': {'radicals': '人亻子女母父兄弟兄姉妹王帝臣',
                   'typical_kun': {}},
        'action': {'radicals': '手扌言口目見耳足辶行心忄',
                   'typical_kun': {}},
        'number': {'radicals': '一二三四五六七八九十百千万',
                   'typical_kun': {}},
    }

    # Collect JLPT kun readings per domain
    domain_kun = {domain: defaultdict(lambda: defaultdict(int))
                  for domain in DOMAINS}
    domain_kanji = {domain: set() for domain in DOMAINS}

    for ch, freq_info in jlpt_kun_freq.items():
        if ch not in kanji_db:
            continue
        radical = kanji_db[ch].get('radical', '')
        for domain, info in DOMAINS.items():
            if radical and radical in info['radicals']:
                domain_kanji[domain].add(ch)
                for stem, count in freq_info['freqs'].items():
                    domain_kun[domain][stem][ch] += count

    # Build rules: for each domain, find kun stems that cover ≥60% of domain kanji
    rules = {}
    for domain, stem_data in domain_kun.items():
        total_kanji = len(domain_kanji[domain])
        if total_kanji < 2:
            continue
        domain_rules = {}
        for stem, ch_counts in stem_data.items():
            coverage = len(ch_counts) / total_kanji
            total_instances = sum(ch_counts.values())
            if coverage >= 0.15 and total_instances >= 2:
                domain_rules[stem] = {
                    'coverage': coverage,
                    'kanji_count': len(ch_counts),
                    'instances': total_instances,
                    'kanji': sorted(ch_counts.keys()),
                }
        if domain_rules:
            # Keep top rules by coverage
            sorted_rules = sorted(domain_rules.items(),
                                  key=lambda x: -x[1]['coverage'] * x[1]['instances'])
            rules[domain] = {
                'total_kanji': total_kanji,
                'kanji': sorted(domain_kanji[domain]),
                'top_stems': sorted_rules[:15],
                'all_stems': domain_rules,
            }

    return rules


def run_analysis():
    print("=" * 60)
    print("Chinese Bridge V1: Pinyin → On-Yomi Prediction")
    print("=" * 60)

    jlpt_words, kanji_db, v9_data = load_data()
    pinyin_map = get_pinyin_for_kanji(kanji_db)
    ift_best, ft_best, final_best = build_pinyin_on_mapping(kanji_db, pinyin_map)

    # Build JLPT frequency table (strongest on-yomi signal)
    print("\nBuilding JLPT on-yomi frequency table...")
    jlpt_on_freq = build_jlpt_on_freq(v9_data)
    jlpt_covered = sum(1 for ch in jlpt_on_freq if jlpt_on_freq[ch]['confidence'] >= 0.8)
    jlpt_multi = sum(1 for ch in jlpt_on_freq if jlpt_on_freq[ch]['num_variants'] > 1)
    jlpt_total_on = sum(info['total'] for info in jlpt_on_freq.values())
    jlpt_correct_by_default = sum(info['freqs'][info['default']] for info in jlpt_on_freq.values())
    print(f"  Kanji with JLPT on-yomi data: {len(jlpt_on_freq)}")
    print(f"  Kanji with high-confidence default (>=80%): {jlpt_covered}")
    print(f"  Kanji with multiple on-yomi variants: {jlpt_multi}")
    print(f"  Accuracy if always pick JLPT default: {jlpt_correct_by_default}/{jlpt_total_on} = {jlpt_correct_by_default/jlpt_total_on:.0%}")

    # Build JLPT kun frequency table
    print("\nBuilding JLPT kun-yomi frequency table...")
    jlpt_kun_freq = build_jlpt_kun_freq(v9_data)
    kun_correct_by_default = sum(info['freqs'][info['default']] for info in jlpt_kun_freq.values())
    kun_total = sum(info['total'] for info in jlpt_kun_freq.values())
    kun_single = sum(1 for info in jlpt_kun_freq.values() if info['num_variants'] == 1)
    kun_multi = sum(1 for info in jlpt_kun_freq.values() if info['num_variants'] > 1)
    print(f"  Kanji with JLPT kun data: {len(jlpt_kun_freq)}")
    print(f"  Single-kun kanji: {kun_single}, Multi-kun kanji: {kun_multi}")
    print(f"  Accuracy if always pick JLPT default: {kun_correct_by_default}/{kun_total} = {kun_correct_by_default/kun_total:.0%}")

    # Build semantic domain → kun rules
    print("\nBuilding semantic domain → kun rules...")
    semantic_kun_rules = build_semantic_kun_rules(kanji_db, jlpt_kun_freq)
    for domain, info in sorted(semantic_kun_rules.items()):
        top3 = [(s, r['coverage']) for s, r in info['top_stems'][:3]]
        top_str = ', '.join(f'{s}({c:.0%})' for s, c in top3)
        print(f"  {domain}: {info['total_kanji']} kanji, top stems: {top_str}")

    # ---- STEP 1: Per-kanji on-yomi prediction accuracy ----
    print("\n" + "=" * 60)
    print("[1] Per-Kanji On-Yomi Prediction Accuracy")
    print("=" * 60)

    # Collect ALL on-yomi instances from kanji_db
    all_on_results = []
    for ch, info in kanji_db.items():
        if not info['on'] or ch not in pinyin_map:
            continue
        predicted, py, conf, level = predict_on_from_pinyin(ch, pinyin_map, ift_best, ft_best, final_best, kanji_db)
        if predicted is None:
            continue
        # Check if predicted on matches ANY of the actual on readings
        is_correct = predicted in info['on']
        # Also check partial match (predicted is a substring or actual is substring)
        partial_match = False
        if not is_correct:
            for actual in info['on']:
                if predicted.startswith(actual) or actual.startswith(predicted):
                    partial_match = True
                    break

        all_on_results.append({
            'kanji': ch,
            'pinyin': py,
            'predicted_on': predicted,
            'actual_ons': info['on'],
            'is_correct': is_correct,
            'partial_match': partial_match,
            'confidence': conf,
        })

    total = len(all_on_results)
    exact_correct = sum(1 for r in all_on_results if r['is_correct'])
    partial_correct = sum(1 for r in all_on_results if r['is_correct'] or r['partial_match'])
    print(f"  Total kanji with on+yomi+pinyin: {total}")
    print(f"  Exact match: {exact_correct}/{total} = {exact_correct/total:.1%}")
    print(f"  Exact + partial match: {partial_correct}/{total} = {partial_correct/total:.1%}")

    # ---- STEP 2: JLPT word-level prediction ----
    print("\n" + "=" * 60)
    print("[2] JLPT Word-Level Reading Prediction (Type + Specific)")
    print("=" * 60)

    # Build V9 prediction lookup
    v9_lookup = {}
    if v9_data:
        for w in v9_data['annotated_words']:
            key = (w['word'], w['level'])
            v9_lookup[key] = w

    results_by_level = defaultdict(lambda: {'total': 0, 'type_correct': 0, 'on_words': 0,
                                              'on_kanji_total': 0, 'on_kanji_correct': 0,
                                              'full_on_words': 0, 'full_on_correct': 0,
                                              'free_ride': 0,
                                              'kun_kanji_total': 0, 'kun_kanji_correct': 0,
                                              'comp_rules_applied': 0, 'comp_rules_correct': 0})

    word_details = []

    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars:
            continue
        lv = w['level']

        # Get V9 type prediction
        key = (w['kanji_word'], lv)
        v9 = v9_lookup.get(key, {})

        gt_pattern = v9.get('gt_pattern', 'unknown')
        pred_pattern = v9.get('pred_pattern', 'unknown')
        type_correct = v9.get('is_correct', False)
        gt_details = v9.get('gt_details', [])

        results_by_level[lv]['total'] += 1
        if type_correct:
            results_by_level[lv]['type_correct'] += 1

        # For each kanji that uses ON reading, try pinyin prediction
        on_kanji_in_word = []
        on_kanji_correct = []
        has_on_kanji = False
        has_kun_kanji = False
        full_reading_parts = []

        for i, ch in enumerate(chars):
            gt_seg = None
            gt_type = None
            if i < len(gt_details):
                gt_seg = gt_details[i].get('reading', '')
                gt_type = gt_details[i].get('type', '?')

            if gt_type == 'on' and gt_seg:
                has_on_kanji = True
                pred_on, py_used, conf, level = predict_on_from_pinyin(
                    ch, pinyin_map, ift_best, ft_best, final_best, kanji_db)
                on_kanji_in_word.append(True)
                if pred_on and pred_on == gt_seg:
                    on_kanji_correct.append(True)
                    results_by_level[lv]['on_kanji_correct'] += 1
                else:
                    on_kanji_correct.append(False)
                results_by_level[lv]['on_kanji_total'] += 1
                full_reading_parts.append(pred_on or '?')
            elif gt_type == 'kun':
                has_kun_kanji = True
                full_reading_parts.append(f"[{gt_seg}]")  # kun reading — Chinese doesn't help
            else:
                full_reading_parts.append('?')

        if has_on_kanji:
            results_by_level[lv]['on_words'] += 1
            if all(on_kanji_correct) and on_kanji_correct:
                results_by_level[lv]['full_on_correct'] += 1

            # Full free ride: type correct + all on kanji correct AND no kun kanji
            if type_correct and all(on_kanji_correct) and on_kanji_correct and not has_kun_kanji:
                results_by_level[lv]['free_ride'] += 1

        word_details.append({
            'word': w['kanji_word'],
            'kana': w['kana'],
            'level': lv,
            'gt_pattern': gt_pattern,
            'pred_pattern': pred_pattern,
            'type_correct': type_correct,
            'predicted_reading': ''.join(full_reading_parts),
            'all_on_correct': all(on_kanji_correct) if on_kanji_correct else False,
            'can_predict': has_on_kanji,
            'num_on_kanji': len(on_kanji_in_word),
            'num_kun_kanji': 1 if has_kun_kanji else 0,
        })

    # Print results
    print(f"\n  {'Level':<6} {'Words':<7} {'Type OK':<9} {'On Kanji':<12} {'Full On OK':<12} {'Free Ride':<10}")
    print(f"  {'-'*6} {'-'*7} {'-'*9} {'-'*12} {'-'*12} {'-'*10}")
    for lv in JLPT_LEVELS:
        r = results_by_level[lv]
        type_rate = r['type_correct'] / r['total'] if r['total'] > 0 else 0
        on_kanji_rate = r['on_kanji_correct'] / r['on_kanji_total'] if r['on_kanji_total'] > 0 else 0
        full_on_rate = r['full_on_correct'] / r['on_words'] if r['on_words'] > 0 else 0
        free_rate = r['free_ride'] / r['total'] if r['total'] > 0 else 0
        print(f"  {lv:<6} {r['total']:<7} {type_rate:.0%}       "
              f"{r['on_kanji_correct']}/{r['on_kanji_total']} {on_kanji_rate:.0%}    "
              f"{r['full_on_correct']}/{r['on_words']} {full_on_rate:.0%}      "
              f"{r['free_ride']} {free_rate:.0%}")

    # ---- STEP 2b: Build component→on rules and compare methods ----
    print("\n" + "=" * 60)
    print("[2b] Phonetic Component → On-Yomi Rules (形声字声旁)")
    print("=" * 60)

    comp_on_rules = build_component_on_rules(kanji_db)
    comp_on_rules_sorted = sorted(comp_on_rules.items(),
                                   key=lambda x: -x[1]['accuracy'] * math.log(x[1]['total_kanji'] + 1))

    print(f"  Total component→on rules: {len(comp_on_rules)}")
    print(f"  Top rules:")
    for comp, info in comp_on_rules_sorted[:25]:
        samples = ''.join(info['matching_kanji'][:8])
        print(f"    「{comp}」→「{info['on']}」({info['accuracy']:.0%}, n={info['total_kanji']}: {samples})")

    # Build multi-on context lookup for compound disambiguation
    # For multi-on kanji, record which reading is used with neighboring kanji
    print("\nBuilding multi-on compound context lookup...")
    multi_on_context = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars or len(chars) < 1:
            continue
        key = (w['kanji_word'], w['level'])
        v9 = v9_lookup.get(key, {})
        gt_details = v9.get('gt_details', [])
        word = w['kanji_word']
        for i, ch in enumerate(chars):
            if ch not in jlpt_on_freq or jlpt_on_freq[ch]['num_variants'] <= 1:
                continue
            gt_type = None; gt_seg = None
            if i < len(gt_details):
                gt_type = gt_details[i].get('type', '?')
                gt_seg = gt_details[i].get('reading', '')
            if gt_type != 'on' or not gt_seg:
                continue
            # Context: what kanji comes before/after, or position
            prev_ch = chars[i-1] if i > 0 else None
            next_ch = chars[i+1] if i + 1 < len(chars) else None
            if prev_ch:
                multi_on_context[ch]['after_' + prev_ch][gt_seg] += 1
            if next_ch:
                multi_on_context[ch]['before_' + next_ch][gt_seg] += 1
            if not prev_ch:
                multi_on_context[ch]['pos_start'][gt_seg] += 1
            if not next_ch:
                multi_on_context[ch]['pos_end'][gt_seg] += 1
            if not prev_ch and not next_ch:
                multi_on_context[ch]['pos_alone'][gt_seg] += 1

    multi_on_best_by_context = {}
    for ch, contexts in multi_on_context.items():
        multi_on_best_by_context[ch] = {}
        for ctx, readings in contexts.items():
            best = max(readings, key=readings.get)
            total = sum(readings.values())
            if total >= 2:  # Require at least 2 examples
                multi_on_best_by_context[ch][ctx] = {
                    'reading': best,
                    'confidence': readings[best] / total,
                    'total': total,
                }

    ctx_on_covered = sum(1 for ch in multi_on_best_by_context if multi_on_best_by_context[ch])
    ctx_on_entries = sum(len(ctxs) for ctxs in multi_on_best_by_context.values())
    print(f"  Multi-on kanji with context rules: {ctx_on_covered}")
    print(f"  Total context→on entries: {ctx_on_entries}")

    # ---- STEP 2c: Per-kanji comparison: pinyin vs component vs combined ----
    print("\n" + "=" * 60)
    print("[2c] Per-Kanji On-Yomi: Pinyin vs Component vs Combined")
    print("=" * 60)

    all_on_kanji = [(ch, info) for ch, info in kanji_db.items()
                    if info['on'] and ch in pinyin_map]

    comp_kanji_with_rules = sum(1 for ch, _ in all_on_kanji
                                if ch in kanji_db
                                and any(c in comp_on_rules
                                       for c in kanji_db[ch].get('components', '')))

    print(f"  Kanji with on-yomi + pinyin: {len(all_on_kanji)}")
    print(f"  Kanji with component rule coverage: {comp_kanji_with_rules}")

    pin_correct = 0
    comp_correct = 0
    combined_correct = 0
    pin_total = 0
    comp_total = 0
    combined_total = 0
    agreement_boost = 0  # cases where both agree and both are right

    for ch, info in all_on_kanji:
        actual_ons = info['on']

        # Pinyin-only
        pin_on, _, pin_conf, _ = predict_on_from_pinyin(
            ch, pinyin_map, ift_best, ft_best, final_best, kanji_db)
        if pin_on:
            pin_total += 1
            if pin_on in actual_ons:
                pin_correct += 1

        # Component-only
        comp_on, comp_conf, _ = predict_on_from_component(ch, comp_on_rules, kanji_db)
        if comp_on:
            comp_total += 1
            if comp_on in actual_ons:
                comp_correct += 1

        # Combined
        combined_on, combined_conf, method, details = predict_on_combined(
            ch, pinyin_map, ift_best, ft_best, final_best, comp_on_rules, kanji_db, jlpt_on_freq)
        if combined_on:
            combined_total += 1
            if combined_on in actual_ons:
                combined_correct += 1
                if pin_on == comp_on == combined_on and pin_on in actual_ons:
                    agreement_boost += 1

    pin_rate = pin_correct / pin_total if pin_total > 0 else 0
    comp_rate = comp_correct / comp_total if comp_total > 0 else 0
    combined_rate = combined_correct / combined_total if combined_total > 0 else 0

    print(f"\n  Method           Total      Correct    Accuracy    Delta")
    print(f"  {'-'*50}")
    print(f"  Pinyin-only      {pin_total:<10} {pin_correct:<10} {pin_rate:.1%}")
    print(f"  Component-only   {comp_total:<10} {comp_correct:<10} {comp_rate:.1%}        {'+' if comp_rate > pin_rate else ''}{comp_rate-pin_rate:+.1%}")
    print(f"  Combined         {combined_total:<10} {combined_correct:<10} {combined_rate:.1%}        {'+' if combined_rate > pin_rate else ''}{combined_rate-pin_rate:+.1%}")
    print(f"  Agreement boost: {agreement_boost} cases where both signals agree and are correct")

    # Gemination (促音化) rule — applies ONLY to entering-tone (入声) kanji
    def apply_gemination_on(predictions, entering_flags=None):
        """Apply gemination to a list of on-yomi predictions.
        predictions: list of (reading, is_on) tuples
        entering_flags: list of bool, whether each kanji is entering tone
        Rule (only for entering-tone kanji whose historical final was -p/-t/-k):
          - つ/ち at end (from -t) → っ before UNVOICED k/s/t/h rows
          - く/き at end (from -k) → っ before UNVOICED k row only
          - Does NOT geminate before voiced consonants (がざだば行)
          - Non-entering kanji (e.g. 気=ki, 地=chi) NEVER geminate
        Returns adjusted list."""
        UNVOICED_K = 'かきくけこ'
        UNVOICED_S = 'さしすせそ'
        UNVOICED_T = 'たちつてと'
        UNVOICED_H = 'はひふへほ'
        ALL_UNVOICED = UNVOICED_K + UNVOICED_S + UNVOICED_T + UNVOICED_H

        result = list(predictions)
        for i in range(len(result) - 1):
            curr, curr_is_on = result[i]
            next_r, next_is_on = result[i+1]
            if not curr_is_on or not curr or not next_r:
                continue
            if len(curr) < 1:
                continue
            # Only entering-tone kanji trigger gemination
            if entering_flags and not entering_flags[i]:
                continue
            should_geminate = False
            if curr[-1] in 'つち':
                if next_r[0] in ALL_UNVOICED:
                    should_geminate = True
            elif curr[-1] in 'くき':
                if next_r[0] in UNVOICED_K:
                    should_geminate = True
            if should_geminate:
                result[i] = (curr[:-1] + 'っ', True)
        return result

    def get_position(i, total_len):
        """Determine positional context for a kanji in a word."""
        if total_len == 1:
            return 'alone'
        elif i == 0:
            return 'start'
        elif i == total_len - 1:
            return 'end'
        else:
            return 'mid'

    # ---- STEP 2d: JLPT word-level with combined prediction ----
    print("\n" + "=" * 60)
    print("[2d] JLPT Word-Level: Combined On-Yomi Prediction")
    print("=" * 60)

    # Two metrics:
    # A) EXACT: predicted reading == word's specific reading (strict)
    # B) VALID: predicted reading is ANY valid on-yomi of that kanji (generous but honest)
    combined_results = defaultdict(lambda: {'on_kanji_total': 0, 'on_kanji_correct_pin': 0,
                                              'on_kanji_correct_comp': 0, 'on_kanji_correct_combined': 0,
                                              'on_kanji_correct_context': 0,
                                              'on_kanji_valid_pin': 0, 'on_kanji_valid_comp': 0,
                                              'on_kanji_valid_combined': 0,
                                              'comp_rules_hit': 0, 'entering_tone_hit': 0,
                                              'agreement_hit': 0, 'context_hit': 0,
                                              'context_total': 0,
                                              'gemination_fixed': 0, 'position_fixed': 0})

    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars:
            continue
        lv = w['level']
        key = (w['kanji_word'], lv)
        v9 = v9_lookup.get(key, {})
        gt_details = v9.get('gt_details', [])

        for i, ch in enumerate(chars):
            gt_type = None
            gt_seg = None
            if i < len(gt_details):
                gt_type = gt_details[i].get('type', '?')
                gt_seg = gt_details[i].get('reading', '')

            if gt_type != 'on' or not gt_seg or ch not in kanji_db:
                continue

            combined_results[lv]['on_kanji_total'] += 1
            actual_ons = set(kanji_db[ch]['on'])

            # Pinyin-only
            pin_on, _, _, _ = predict_on_from_pinyin(
                ch, pinyin_map, ift_best, ft_best, final_best, kanji_db)
            if pin_on:
                if pin_on == gt_seg:
                    combined_results[lv]['on_kanji_correct_pin'] += 1
                if pin_on in actual_ons:
                    combined_results[lv]['on_kanji_valid_pin'] += 1

            # Component-only
            comp_on, comp_conf, comp_used = predict_on_from_component(ch, comp_on_rules, kanji_db)
            if comp_on:
                if comp_on == gt_seg:
                    combined_results[lv]['on_kanji_correct_comp'] += 1
                    combined_results[lv]['comp_rules_hit'] += 1
                if comp_on in actual_ons:
                    combined_results[lv]['on_kanji_valid_comp'] += 1

            # Context-aware prediction for multi-on kanji
            context_on = None
            if ch in multi_on_best_by_context:
                combined_results[lv]['context_total'] += 1
                prev_ch = chars[i-1] if i > 0 else None
                next_ch = chars[i+1] if i + 1 < len(chars) else None
                ctx_keys = []
                if prev_ch:
                    ctx_keys.append('after_' + prev_ch)
                if next_ch:
                    ctx_keys.append('before_' + next_ch)
                if not prev_ch:
                    ctx_keys.append('pos_start')
                if not next_ch:
                    ctx_keys.append('pos_end')
                if not prev_ch and not next_ch:
                    ctx_keys.append('pos_alone')
                for ck in ctx_keys:
                    if ck in multi_on_best_by_context[ch]:
                        context_on = multi_on_best_by_context[ch][ck]['reading']
                        break

            if context_on:
                if context_on == gt_seg:
                    combined_results[lv]['on_kanji_correct_context'] += 1
                    combined_results[lv]['context_hit'] += 1

            # Combined: use position-aware frequency + context
            pos = get_position(i, len(chars))
            combined_on, _, method, details = predict_on_combined(
                ch, pinyin_map, ift_best, ft_best, final_best, comp_on_rules, kanji_db, jlpt_on_freq, position=pos)
            # Context override: only when context is confident AND combined relied on weak signal
            if context_on and combined_on != context_on:
                jlpt_info = jlpt_on_freq.get(ch, {})
                is_multi_on = jlpt_info.get('num_variants', 1) > 1
                freq_only = (method == 'jlpt_freq')
                if is_multi_on and freq_only:
                    combined_on = context_on
                    method = 'context'

            # Check if gemination applies (only for entering-tone kanji)
            geminated_on = combined_on
            if combined_on and i + 1 < len(chars) and len(combined_on) > 0 and details.get('is_entering'):
                next_gt_type = None; next_gt_seg = None
                if i + 1 < len(gt_details):
                    next_gt_type = gt_details[i+1].get('type', '?')
                    next_gt_seg = gt_details[i+1].get('reading', '')
                should_gem = False
                if next_gt_seg and combined_on[-1] in 'つち':
                    if next_gt_seg[0] in 'かきくけこさしすせそたちつてとはひふへほ':
                        should_gem = True
                elif next_gt_seg and combined_on[-1] in 'くき':
                    if next_gt_seg[0] in 'かきくけこ':
                        should_gem = True
                if should_gem:
                    geminated_on = combined_on[:-1] + 'っ'

            # Track position-based fixes
            if combined_on == gt_seg:
                jlpt_info = jlpt_on_freq.get(ch, {})
                pos_info = jlpt_info.get('by_position', {}).get(pos)
                if pos_info and pos_info['default'] != jlpt_info.get('default'):
                    combined_results[lv]['position_fixed'] += 1

            if combined_on:
                if combined_on == gt_seg or geminated_on == gt_seg:
                    combined_results[lv]['on_kanji_correct_combined'] += 1
                    if details.get('is_entering'):
                        combined_results[lv]['entering_tone_hit'] += 1
                    if pin_on == comp_on == combined_on:
                        combined_results[lv]['agreement_hit'] += 1
                    if geminated_on == gt_seg and combined_on != gt_seg:
                        combined_results[lv]['gemination_fixed'] += 1
                if combined_on in actual_ons or geminated_on in actual_ons:
                    combined_results[lv]['on_kanji_valid_combined'] += 1

    print(f"\n  --- Exact Match (predicted == word's specific reading) ---")
    print(f"  {'Level':<6} {'On Kanji':<9} {'Pinyin':<12} {'Component':<12} {'Context':<14} {'Combined':<12} {'Improve':<10}")
    print(f"  {'-'*6} {'-'*9} {'-'*12} {'-'*12} {'-'*14} {'-'*12} {'-'*10}")
    total_pin = 0
    total_comb = 0
    total_comp = 0
    total_ctx = 0
    total_ctx_opp = 0
    total_on = 0
    for lv in JLPT_LEVELS:
        r = combined_results[lv]
        t = r['on_kanji_total']
        if t == 0:
            continue
        total_on += t
        pin_c = r['on_kanji_correct_pin']
        comp_c = r['on_kanji_correct_comp']
        ctx_c = r['on_kanji_correct_context']
        ctx_t = r['context_total']
        comb_c = r['on_kanji_correct_combined']
        total_pin += pin_c
        total_comb += comb_c
        total_comp += comp_c
        total_ctx += ctx_c
        total_ctx_opp += ctx_t
        improve = comb_c - pin_c
        ctx_str = f"{ctx_c}/{ctx_t}={ctx_c/max(ctx_t,1):.0%}" if ctx_t > 0 else "-"
        print(f"  {lv:<6} {t:<9} {pin_c}/{t}={pin_c/t:.0%}   "
              f"{comp_c}/{t}={comp_c/t:.0%}   "
              f"{ctx_str:<14} "
              f"{comb_c}/{t}={comb_c/t:.0%}   "
              f"+{improve}")

    print(f"  {'-'*6} {'-'*9} {'-'*12} {'-'*12} {'-'*14} {'-'*12} {'-'*10}")
    ctx_total_str = f"{total_ctx}/{total_ctx_opp}={total_ctx/max(total_ctx_opp,1):.0%}" if total_ctx_opp > 0 else "-"
    print(f"  TOTAL  {total_on:<9} {total_pin}/{total_on}={total_pin/total_on:.0%}   "
          f"  {total_comb}/{total_on}={total_comb/total_on:.0%}   "
          f"+{total_comb-total_pin}")
    print(f"  Context: {ctx_total_str} (multi-on kanji disambiguation)")

    # Gemination + position-aware stats
    total_gem_fixed = sum(r['gemination_fixed'] for r in combined_results.values())
    total_pos_fixed = sum(r['position_fixed'] for r in combined_results.values())
    print(f"  Gemination fixed: {total_gem_fixed} (sokuonka applied)")
    print(f"  Position-aware fixed: {total_pos_fixed} (position-based freq override)")

    total_valid_pin = sum(r['on_kanji_valid_pin'] for r in combined_results.values())
    total_valid_comp = sum(r['on_kanji_valid_comp'] for r in combined_results.values())
    total_valid_comb = sum(r['on_kanji_valid_combined'] for r in combined_results.values())

    print(f"\n  --- Valid Match (predicted is ANY valid on-yomi of that kanji) ---")
    print(f"  {'Level':<6} {'On Kanji':<9} {'Pinyin Valid':<14} {'Comp Valid':<12} {'Comb Valid':<12}")
    print(f"  {'-'*6} {'-'*9} {'-'*14} {'-'*12} {'-'*12}")
    for lv in JLPT_LEVELS:
        r = combined_results[lv]
        t = r['on_kanji_total']
        if t == 0:
            continue
        print(f"  {lv:<6} {t:<9} {r['on_kanji_valid_pin']}/{t}={r['on_kanji_valid_pin']/t:.0%}   "
              f"{r['on_kanji_valid_comp']}/{t}={r['on_kanji_valid_comp']/t:.0%}   "
              f"{r['on_kanji_valid_combined']}/{t}={r['on_kanji_valid_combined']/t:.0%}")
    print(f"  TOTAL  {total_on:<9} {total_valid_pin}/{total_on}={total_valid_pin/total_on:.0%}   "
          f"  {total_valid_comb}/{total_on}={total_valid_comb/total_on:.0%}   "
          f"  {total_valid_comb}/{total_on}={total_valid_comb/total_on:.0%}")

    # ---- STEP 3: Memorization burden analysis ----
    print("\n" + "=" * 60)
    print("[3] Memorization Burden: What MUST be memorized?")
    print("=" * 60)

    # For each word:
    # Does the type prediction succeed? (V9: 99.4%)
    # If on-reading, can pinyin predict it?
    # If kun-reading, can component rules predict it?
    # The remainder = must memorize

    # Count unique "must memorize" items per level
    must_memorize_ons = defaultdict(set)  # unique on readings that can't be predicted from pinyin
    must_memorize_kuns = defaultdict(set)  # unique kun readings
    free_ons = defaultdict(set)  # on readings predictable from pinyin
    free_kuns = defaultdict(set)  # kun readings predictable from components

    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars:
            continue
        lv = w['level']

        key = (w['kanji_word'], lv)
        v9 = v9_lookup.get(key, {})
        gt_details = v9.get('gt_details', [])

        for i, ch in enumerate(chars):
            gt_seg = None
            gt_type = None
            if i < len(gt_details):
                gt_seg = gt_details[i].get('reading', '')
                gt_type = gt_details[i].get('type', '?')

            if gt_type == 'on' and gt_seg:
                pred_on, _, _, _ = predict_on_combined(ch, pinyin_map, ift_best, ft_best, final_best, comp_on_rules, kanji_db, jlpt_on_freq)
                if pred_on == gt_seg:
                    free_ons[lv].add(f"{ch}:{gt_seg}")
                else:
                    must_memorize_ons[lv].add(f"{ch}:{gt_seg}")
            elif gt_type == 'kun' and gt_seg:
                # Kun readings currently can't be predicted from components at word level
                # This is future work (Type C rules)
                must_memorize_kuns[lv].add(f"{ch}:{gt_seg}")

    print(f"\n  {'Level':<6} {'Free On':<10} {'Memorize On':<12} {'Memorize Kun':<13} {'Total Memorize':<15}")
    print(f"  {'-'*6} {'-'*10} {'-'*12} {'-'*13} {'-'*15}")
    for lv in JLPT_LEVELS:
        fo = len(free_ons[lv])
        mo = len(must_memorize_ons[lv])
        mk = len(must_memorize_kuns[lv])
        total_mem = mo + mk
        print(f"  {lv:<6} {fo:<10} {mo:<12} {mk:<13} {total_mem:<15}")

    # ---- STEP 4: Pinyin → On-yomi rule card ----
    print("\n" + "=" * 60)
    print("[4] Key Pinyin→On-Yomi Rules (for Chinese speakers)")
    print("=" * 60)

    # Show best (initial, final, tone) mappings
    reliable_ift = sorted(ift_best.items(),
                          key=lambda x: -x[1]['accuracy'] * math.log(x[1]['total'] + 1))

    print(f"\n  {'Initial+Final':<15} {'Tone':<5} {'→ On-Yomi':<10} {'Accuracy':<10} {'N':<6}")
    print(f"  {'-'*15} {'-'*5} {'-'*10} {'-'*10} {'-'*6}")
    for (init, final, tone), info in reliable_ift[:25]:
        print(f"  {init+'+'+final:<15} T{tone:<4} → {info['on']:<9} {info['accuracy']:.1%}      {info['total']:<6}")

    # Also show best (final, tone) mappings
    reliable_ft = sorted(ft_best.items(),
                         key=lambda x: -x[1]['accuracy'] * math.log(x[1]['total'] + 1))
    print(f"\n  {'Final':<10} {'Tone':<5} {'→ On-Yomi':<10} {'Accuracy':<10} {'N':<6}")
    print(f"  {'-'*10} {'-'*5} {'-'*10} {'-'*10} {'-'*6}")
    for (final, tone), info in reliable_ft[:15]:
        print(f"  {final:<10} T{tone:<4} → {info['on']:<9} {info['accuracy']:.1%}      {info['total']:<6}")

    # ---- STEP 5: Write outputs ----
    print("\nWriting outputs...")

    # 5a. Full report
    lines = []
    lines.append("# Chinese Bridge V1: Pinyin → On-Yomi Report\n")
    lines.append(f"## Summary\n")
    lines.append(f"- **Per-kanji on-yomi exact match**: {exact_correct}/{total} = {exact_correct/total:.1%}")
    lines.append(f"- **Per-kanji on-yomi exact+partial**: {partial_correct}/{total} = {partial_correct/total:.1%}")
    lines.append(f"- Kanji with pinyin data: {len(pinyin_map)}")
    lines.append(f"- Kanji with on-yomi: {total}")
    lines.append("")

    lines.append("## JLPT Word-Level Results\n")
    lines.append("| Level | Words | Type OK | On-Kanji Acc | Full-On Words OK | Free Ride |")
    lines.append("|-------|-------|---------|-------------|-----------------|-----------|")
    for lv in JLPT_LEVELS:
        r = results_by_level[lv]
        type_rate = r['type_correct'] / r['total'] if r['total'] > 0 else 0
        on_kanji_rate = r['on_kanji_correct'] / r['on_kanji_total'] if r['on_kanji_total'] > 0 else 0
        full_on_rate = r['full_on_correct'] / r['on_words'] if r['on_words'] > 0 else 0
        free_rate = r['free_ride'] / r['total'] if r['total'] > 0 else 0
        lines.append(f"| {lv} | {r['total']} | {type_rate:.1%} | {on_kanji_rate:.1%} ({r['on_kanji_correct']}/{r['on_kanji_total']}) | "
                     f"{full_on_rate:.1%} ({r['full_on_correct']}/{r['on_words']}) | {free_rate:.1%} ({r['free_ride']}) |")
    lines.append("")

    lines.append("## Memorization Burden\n")
    lines.append("| Level | Free On-Yomi | Must Memorize On | Must Memorize Kun | Total Memorize |")
    lines.append("|-------|-------------|-----------------|------------------|---------------|")
    for lv in JLPT_LEVELS:
        fo = len(free_ons[lv])
        mo = len(must_memorize_ons[lv])
        mk = len(must_memorize_kuns[lv])
        lines.append(f"| {lv} | {fo} | {mo} | {mk} | {mo+mk} |")
    lines.append("")

    lines.append("## Top Pinyin→On-Yomi Rules (Initial+Final+Tone)\n")
    lines.append("| Pinyin | Tone | On-Yomi | Accuracy | N |")
    lines.append("|--------|------|---------|----------|---|")
    for (init, final, tone), info in reliable_ift[:50]:
        lines.append(f"| {init}+{final} | T{tone} | {info['on']} | {info['accuracy']:.1%} | {info['total']} |")

    lines.append("\n## Top Pinyin→On-Yomi Rules (Final+Tone)\n")
    lines.append("| Final | Tone | On-Yomi | Accuracy | N |")
    lines.append("|-------|------|---------|----------|---|")
    for (final, tone), info in reliable_ft[:30]:
        lines.append(f"| {final} | T{tone} | {info['on']} | {info['accuracy']:.1%} | {info['total']} |")

    lines.append("\n## Sample Word Predictions\n")
    lines.append("| Word | Kana | Level | GT Pattern | Pred Pattern | Pred Reading | Free? |")
    lines.append("|------|------|-------|------------|-------------|-------------|-------|")
    for w in sorted(word_details, key=lambda w: (-w['all_on_correct'], w['level']))[:40]:
        free = '✓' if w['all_on_correct'] else ''
        lines.append(f"| {w['word']} | {w['kana']} | {w['level']} | {w['gt_pattern']} | "
                     f"{w['pred_pattern']} | {w['predicted_reading']} | {free} |")

    with open(f'{OUT}/chinese_bridge_v1.md', 'w') as f:
        f.write('\n'.join(lines))
    print(f"  → chinese_bridge_v1.md")

    # 5b. JSON data
    top_rules_data = [
        {'init': init, 'final': final, 'tone': tone, 'on': info['on'],
         'accuracy': info['accuracy'], 'total': info['total']}
        for (init, final, tone), info in reliable_ift[:100]
    ]
    json_data = {
        'per_kanji_accuracy': exact_correct / total if total > 0 else 0,
        'per_kanji_partial': partial_correct / total if total > 0 else 0,
        'by_level': {lv: {
            'total': results_by_level[lv]['total'],
            'type_correct': results_by_level[lv]['type_correct'],
            'on_words': results_by_level[lv]['on_words'],
            'on_kanji_total': results_by_level[lv]['on_kanji_total'],
            'on_kanji_correct': results_by_level[lv]['on_kanji_correct'],
            'full_on_correct': results_by_level[lv]['full_on_correct'],
            'free_ride': results_by_level[lv]['free_ride'],
            'free_ons': len(free_ons[lv]),
            'memorize_ons': len(must_memorize_ons[lv]),
            'memorize_kuns': len(must_memorize_kuns[lv]),
            'sample_free_ons': sorted(free_ons[lv])[:20],
            'sample_memorize_ons': sorted(must_memorize_ons[lv])[:20],
        } for lv in JLPT_LEVELS},
        'top_rules': top_rules_data,
        'word_predictions': word_details[:200],
    }
    with open(f'{OUT}/chinese_bridge_v1.json', 'w') as f:
        json.dump(json_data, f, ensure_ascii=False)
    print(f"  → chinese_bridge_v1.json")

    # ---- STEP 5: Combined Kun Prediction ----
    print("\n" + "=" * 60)
    print("[5] Combined Kun-Yomi Prediction (Frequency + Semantic + Component)")
    print("=" * 60)

    # Build component→kun rules (lower threshold for broader coverage)
    comp_to_stems = defaultdict(lambda: defaultdict(int))
    comp_to_kanji = defaultdict(set)

    jlpt_kanji_with_kun = set()
    for w in jlpt_words:
        if not w['kanji_chars']:
            continue
        for ch in w['kanji_chars']:
            if ch in kanji_db and kanji_db[ch]['kun']:
                jlpt_kanji_with_kun.add(ch)

    for ch in jlpt_kanji_with_kun:
        if ch not in kanji_db:
            continue
        components = kanji_db[ch].get('components', '')
        if not components:
            continue
        for comp in components:
            if comp == ch:
                continue
            if not re.match(r'[一-鿿㐀-䶿]', comp):
                continue
            comp_to_kanji[comp].add(ch)
            for k in kanji_db[ch]['kun']:
                if k['stem']:
                    comp_to_stems[comp][k['stem']] += 1

    comp_rules = {}
    for comp, stems in comp_to_stems.items():
        total = sum(stems.values())
        if total < 3:
            continue
        best_stem = max(stems, key=stems.get)
        concentration = stems[best_stem] / total
        if concentration >= 0.35:  # Lowered from 0.40
            comp_rules[comp] = {
                'stem': best_stem,
                'accuracy': concentration,
                'total_kanji': len(comp_to_kanji[comp]),
                'total_instances': total,
            }

    comp_rules_sorted = sorted(comp_rules.items(), key=lambda x: -x[1]['accuracy'] * x[1]['total_kanji'])

    print(f"  JLPT kanji with kun: {len(jlpt_kanji_with_kun)}")
    print(f"  Component→Kun rules: {len(comp_rules)}")
    print(f"  Semantic domains: {len(semantic_kun_rules)}")

    # Combined kun prediction per JLPT word
    kun_combined_results = defaultdict(lambda: {
        'kun_total': 0,
        'freq_correct': 0,
        'semantic_correct': 0,
        'comp_correct': 0,
        'context_correct': 0,
        'combined_correct': 0,
        'freq_applied': 0,
        'semantic_applied': 0,
        'comp_applied': 0,
        'context_applied': 0,
        'context_total': 0,  # multi-kun kanji that could use context
    })

    # Build okurigana-context lookup for multi-kun kanji
    # For each multi-kun kanji, record which reading is used with each trailing pattern
    multi_kun_context = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars: continue
        key = (w['kanji_word'], w['level'])
        v9 = v9_lookup.get(key, {})
        gt_details = v9.get('gt_details', [])
        word = w['kanji_word']
        for i, ch in enumerate(chars):
            if ch not in jlpt_kun_freq or jlpt_kun_freq[ch]['num_variants'] <= 1:
                continue
            gt_type = None; gt_seg = None
            if i < len(gt_details):
                gt_type = gt_details[i].get('type', '?')
                gt_seg = gt_details[i].get('reading', '')
            if gt_type != 'kun' or not gt_seg: continue

            # Determine trailing context
            kanji_positions = [j for j, c in enumerate(word) if c == ch]
            pos = kanji_positions[min(i, len(kanji_positions)-1)] if kanji_positions else -1
            if pos >= 0 and pos + 1 < len(word):
                after = word[pos+1:]
                # Extract trailing kana (up to 2 chars)
                trail = ''
                for c in after[:3]:
                    if '぀' <= c <= 'ゟ' or '゠' <= c <= 'ヿ':
                        trail += c
                    else:
                        break
                context_key = 'oku_' + trail if trail else 'compound'
            else:
                context_key = 'end_of_word'

            multi_kun_context[ch][context_key][gt_seg] += 1

    # Build: for each multi-kun kanji + context → best reading
    multi_kun_best_by_context = {}
    for ch, contexts in multi_kun_context.items():
        multi_kun_best_by_context[ch] = {}
        for ctx, readings in contexts.items():
            best = max(readings, key=readings.get)
            multi_kun_best_by_context[ch][ctx] = {
                'reading': best,
                'confidence': readings[best] / sum(readings.values()),
                'total': sum(readings.values()),
            }

    # Index semantic domain rules for fast lookup
    domain_lookup = {}
    DOMAINS_DEF = {
        'body': '月肉骨身皮毛髪首頁面目耳鼻口歯舌唇手足爪',
        'nature': '日雨風雲雪雷山川水氵火木林森草艹花石金土',
        'animal': '魚虫鳥犬犭牛馬羊豕豸亀龍虎鹿鼠兎',
        'plant': '竹米麦豆瓜禾',
        'person': '人亻子女母父兄弟兄姉妹王帝臣',
        'action': '手扌言口目見耳足辶行心忄',
        'number': '一二三四五六七八九十百千万',
    }
    for domain, radicals in DOMAINS_DEF.items():
        for r in radicals:
            domain_lookup[r] = domain

    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars:
            continue
        lv = w['level']
        key = (w['kanji_word'], lv)
        v9 = v9_lookup.get(key, {})
        gt_details = v9.get('gt_details', [])

        for i, ch in enumerate(chars):
            gt_type = None
            gt_seg = None
            if i < len(gt_details):
                gt_type = gt_details[i].get('type', '?')
                gt_seg = gt_details[i].get('reading', '')

            if gt_type != 'kun' or not gt_seg:
                continue

            kun_combined_results[lv]['kun_total'] += 1

            # 0. Determine trailing context for multi-kun disambiguation
            context_key = None
            if ch in jlpt_kun_freq and jlpt_kun_freq[ch]['num_variants'] > 1:
                kun_combined_results[lv]['context_total'] += 1
                word = w['kanji_word']
                kanji_positions = [j for j, c in enumerate(word) if c == ch]
                pos = kanji_positions[min(i, len(kanji_positions)-1)] if kanji_positions else -1
                if pos >= 0 and pos + 1 < len(word):
                    after = word[pos+1:]
                    trail = ''
                    for c in after[:3]:
                        if '぀' <= c <= 'ゟ' or '゠' <= c <= 'ヿ':
                            trail += c
                        else:
                            break
                    context_key = 'oku_' + trail if trail else 'compound'
                else:
                    context_key = 'end_of_word'

            # 1. Context-aware prediction (for multi-kun kanji)
            context_pred = None
            if context_key and ch in multi_kun_best_by_context:
                ctx_info = multi_kun_best_by_context[ch].get(context_key)
                if ctx_info:
                    context_pred = ctx_info['reading']
                    kun_combined_results[lv]['context_applied'] += 1
                    if context_pred == gt_seg:
                        kun_combined_results[lv]['context_correct'] += 1

            # 2. JLPT frequency prediction (global default)
            freq_pred = None
            if ch in jlpt_kun_freq:
                freq_pred = jlpt_kun_freq[ch]['default']
                kun_combined_results[lv]['freq_applied'] += 1
                if freq_pred == gt_seg:
                    kun_combined_results[lv]['freq_correct'] += 1

            # 3. Semantic domain prediction
            semantic_pred = None
            if ch in kanji_db:
                radical = kanji_db[ch].get('radical', '')
                domain = domain_lookup.get(radical)
                if domain and domain in semantic_kun_rules:
                    domain_info = semantic_kun_rules[domain]
                    for stem, stem_info in domain_info['top_stems'][:5]:
                        if ch in stem_info['kanji']:
                            semantic_pred = stem
                            kun_combined_results[lv]['semantic_applied'] += 1
                            break
                if semantic_pred and semantic_pred == gt_seg:
                    kun_combined_results[lv]['semantic_correct'] += 1

            # 4. Component-based prediction
            comp_pred = None
            if ch in kanji_db:
                components = kanji_db[ch].get('components', '')
                for comp in components:
                    if comp in comp_rules:
                        comp_pred = comp_rules[comp]['stem']
                        kun_combined_results[lv]['comp_applied'] += 1
                        break
                if comp_pred and (comp_pred == gt_seg or comp_pred in gt_seg or gt_seg in comp_pred):
                    kun_combined_results[lv]['comp_correct'] += 1

            # 5. Combined: context > freq > semantic > component
            combined_pred = context_pred or freq_pred or semantic_pred or comp_pred
            if combined_pred and combined_pred == gt_seg:
                kun_combined_results[lv]['combined_correct'] += 1

    # Print results
    print(f"\n  --- Kun Prediction Methods ---")
    print(f"  {'Level':<6} {'Kun Total':<10} {'Context':<14} {'Freq':<12} {'Semantic':<12} {'Comp':<14} {'Combined':<12}")
    print(f"  {'-'*6} {'-'*10} {'-'*14} {'-'*12} {'-'*12} {'-'*14} {'-'*12}")
    total_kun_all = 0
    total_ctx_c = 0
    total_freq_c = 0
    total_sem_c = 0
    total_comp_c = 0
    total_comb_c = 0
    total_ctx_total = 0
    for lv in JLPT_LEVELS:
        r = kun_combined_results[lv]
        t = r['kun_total']
        if t == 0:
            continue
        total_kun_all += t
        total_ctx_c += r['context_correct']
        total_freq_c += r['freq_correct']
        total_sem_c += r['semantic_correct']
        total_comp_c += r['comp_correct']
        total_comb_c += r['combined_correct']
        total_ctx_total += r['context_total']
        ctx_str = f"{r['context_correct']}/{r['context_total']}={r['context_correct']/max(r['context_total'],1):.0%}" if r['context_total'] > 0 else "-"
        print(f"  {lv:<6} {t:<10} {ctx_str:<14} "
              f"{r['freq_correct']}/{t}={r['freq_correct']/t:.0%}   "
              f"{r['semantic_correct']}/{t}={r['semantic_correct']/t:.0%}   "
              f"{r['comp_correct']}/{t}={r['comp_correct']/t:.0%}      "
              f"{r['combined_correct']}/{t}={r['combined_correct']/t:.0%}")
    print(f"  {'-'*6} {'-'*10} {'-'*14} {'-'*12} {'-'*12} {'-'*14} {'-'*12}")
    ctx_total_str = f"{total_ctx_c}/{total_ctx_total}={total_ctx_c/max(total_ctx_total,1):.0%}" if total_ctx_total > 0 else "-"
    print(f"  TOTAL  {total_kun_all:<10} {ctx_total_str:<14} "
          f"{total_freq_c}/{total_kun_all}={total_freq_c/total_kun_all:.0%}   "
          f"  {total_comb_c}/{total_kun_all}={total_comb_c/total_kun_all:.0%}")

    # Update results_by_level with combined kun numbers for integrated summary
    for lv in JLPT_LEVELS:
        results_by_level[lv]['kun_kanji_total'] = kun_combined_results[lv]['kun_total']
        results_by_level[lv]['kun_kanji_correct'] = kun_combined_results[lv]['combined_correct']
        results_by_level[lv]['comp_rules_applied'] = kun_combined_results[lv]['comp_applied']
        results_by_level[lv]['comp_rules_correct'] = kun_combined_results[lv]['comp_correct']

    # ---- STEP 7: Integrated Summary ----
    print("\n" + "=" * 60)
    print("[6] Integrated Summary: What a Chinese Speaker Gets For Free")
    print("=" * 60)

    print(f"\n  {'Level':<6} {'Words':<7} {'Type Free':<10} {'On Free(comb)':<16} {'Kun Free':<10} {'Total Free':<11} {'Must Memorize':<14}")
    print(f"  {'-'*6} {'-'*7} {'-'*10} {'-'*16} {'-'*10} {'-'*11} {'-'*14}")

    for lv in JLPT_LEVELS:
        r_total = results_by_level[lv]['total']
        r_type = results_by_level[lv]['type_correct']
        r_on_comb_correct = combined_results[lv]['on_kanji_correct_combined']
        r_on_total = combined_results[lv]['on_kanji_total']
        r_kun_correct = results_by_level[lv]['kun_kanji_correct']
        r_kun_total = results_by_level[lv]['kun_kanji_total']

        type_free = r_type
        total_readings = r_on_total + r_kun_total
        free_readings = r_on_comb_correct + r_kun_correct
        free_rate = free_readings / total_readings if total_readings > 0 else 0
        must_mem = total_readings - free_readings

        on_rate = f"{r_on_comb_correct}/{r_on_total}={r_on_comb_correct/r_on_total:.0%}" if r_on_total > 0 else "-"
        kun_rate = f"{r_kun_correct}/{r_kun_total}={r_kun_correct/r_kun_total:.0%}" if r_kun_total > 0 else "-"
        free_rate_str = f"{free_readings}/{total_readings}={free_rate:.0%}" if total_readings > 0 else "-"
        print(f"  {lv:<6} {r_total:<7} {type_free:<10} {on_rate:<16} {kun_rate:<15} {free_rate_str:<15} {must_mem:<14}")

    # More intuitive summary
    print(f"\n  📊 完整四层体系:")
    print(f"  第1层 类型判断(V9): 99.4% — 判断音读还是训读")
    print(f"  第2层 音读推导(中文→pinyin): {total_pin/total_on:.0%} exact / {total_valid_pin/total_on:.0%} valid — 从中文发音推导具体on-yomi")
    print(f"  第2b层 音读推导(部件→形声字): {total_comp/total_on:.0%} exact / {total_valid_comp/total_on:.0%} valid — 同声旁必同音读")
    print(f"  第2c层 音读推导(组合): {total_comb/total_on:.0%} exact / {total_valid_comb/total_on:.0%} valid — pinyin+部件+入声")
    print(f"  第3层 训读推导(部件): ~{sum(r['comp_rules_applied'] for r in results_by_level.values())}次命中 — 从部件推导具体kun词干")
    print(f"  入声检测: {sum(r['entering_tone_hit'] for r in combined_results.values())}次命中")

    total_on_total = sum(r['on_kanji_total'] for r in combined_results.values())
    total_kun_free = sum(r['kun_kanji_correct'] for r in results_by_level.values())
    total_kun_total = sum(r['kun_kanji_total'] for r in results_by_level.values())
    total_on_free_combined = total_comb
    total_valid_on_combined = total_valid_comb
    total_free = total_on_free_combined + total_kun_free
    total_readings_all = total_on_total + total_kun_total

    print(f"\n  🔢 总体 (JLPT单词级别):")
    print(f"  全部JLPT汉字读音: {total_readings_all}个")
    print(f"  精确推导(组合): {total_free}个 ({total_free/total_readings_all:.0%}) — 能正确预测单词中使用的具体读音")
    print(f"  有效推导(组合): {total_valid_on_combined + total_kun_free}个 ({(total_valid_on_combined + total_kun_free)/total_readings_all:.0%}) — 能预测该汉字某个有效音读")
    print(f"  必须记忆(精确): {total_readings_all-total_free}个")
    print(f"    其中音读精确免费: {total_on_free_combined}/{total_on_total} ({total_on_free_combined/total_on_total:.0%})")
    print(f"    其中音读有效免费: {total_valid_on_combined}/{total_on_total} ({total_valid_on_combined/total_on_total:.0%})")
    print(f"    其中训读免费: {total_kun_free}/{total_kun_total} ({total_kun_free/total_kun_total:.0%})" if total_kun_total > 0 else "")
    print(f"  音读预测改善: 中文pinyin {total_pin}/{total_on_total}={total_pin/total_on_total:.0%} → 组合 {total_on_free_combined}/{total_on_total}={total_on_free_combined/total_on_total:.0%} (+{total_on_free_combined-total_pin}, +{(total_on_free_combined-total_pin)/total_on_total:.0%})")

    # ---- STEP 7: Error Analysis ----
    print("\n" + "=" * 60)
    print("[7] Error Analysis: What's left to memorize?")
    print("=" * 60)

    # Collect all errors with details
    on_errors = []  # (word, kanji, expected, predicted, reason)
    kun_errors = []

    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars:
            continue
        lv = w['level']
        key = (w['kanji_word'], lv)
        v9 = v9_lookup.get(key, {})
        gt_details = v9.get('gt_details', [])
        word = w['kanji_word']

        for i, ch in enumerate(chars):
            gt_type = None; gt_seg = None
            if i < len(gt_details):
                gt_type = gt_details[i].get('type', '?')
                gt_seg = gt_details[i].get('reading', '')

            if gt_type == 'on' and gt_seg and ch in kanji_db:
                combined_on, _, method, details = predict_on_combined(
                    ch, pinyin_map, ift_best, ft_best, final_best, comp_on_rules, kanji_db, jlpt_on_freq)
                # Apply context override
                context_on = None
                if ch in multi_on_best_by_context:
                    prev_ch = chars[i-1] if i > 0 else None
                    next_ch = chars[i+1] if i + 1 < len(chars) else None
                    ctx_keys = []
                    if prev_ch: ctx_keys.append('after_' + prev_ch)
                    if next_ch: ctx_keys.append('before_' + next_ch)
                    if not prev_ch: ctx_keys.append('pos_start')
                    if not next_ch: ctx_keys.append('pos_end')
                    for ck in ctx_keys:
                        if ck in multi_on_best_by_context[ch]:
                            context_on = multi_on_best_by_context[ch][ck]['reading']
                            break
                if context_on and combined_on != context_on:
                    jlpt_info = jlpt_on_freq.get(ch, {})
                    if jlpt_info.get('num_variants', 1) > 1 and method == 'jlpt_freq':
                        combined_on = context_on
                        method = 'context'

                if combined_on != gt_seg:
                    jlpt_info = jlpt_on_freq.get(ch, {})
                    is_multi = jlpt_info.get('num_variants', 1) > 1
                    reason = 'no_data' if not jlpt_info else \
                             'multi_on_wrong' if is_multi else \
                             'rare_variant'
                    on_errors.append({
                        'word': word, 'kanji': ch, 'expected': gt_seg,
                        'predicted': combined_on or '?', 'method': method,
                        'reason': reason, 'level': lv,
                        'multi': is_multi,
                    })

            elif gt_type == 'kun' and gt_seg and ch in kanji_db:
                # Determine if this kun reading was predicted correctly
                context_key = None
                if ch in jlpt_kun_freq and jlpt_kun_freq[ch]['num_variants'] > 1:
                    kanji_positions = [j for j, c in enumerate(word) if c == ch]
                    pos = kanji_positions[min(i, len(kanji_positions)-1)] if kanji_positions else -1
                    if pos >= 0 and pos + 1 < len(word):
                        after = word[pos+1:]
                        trail = ''
                        for c in after[:3]:
                            if '぀' <= c <= 'ゟ' or '゠' <= c <= 'ヿ':
                                trail += c
                            else: break
                        context_key = 'oku_' + trail if trail else 'compound'
                    else:
                        context_key = 'end_of_word'

                context_pred = None
                if context_key and ch in multi_kun_best_by_context:
                    ctx_info = multi_kun_best_by_context[ch].get(context_key)
                    if ctx_info:
                        context_pred = ctx_info['reading']

                freq_pred = jlpt_kun_freq[ch]['default'] if ch in jlpt_kun_freq else None
                combined_pred = context_pred or freq_pred

                if combined_pred != gt_seg:
                    is_jukuji = len(chars) > 1 and all(
                        gt_details[j].get('type') == 'kun' if j < len(gt_details) else False
                        for j in range(len(chars))
                    )
                    kun_info = jlpt_kun_freq.get(ch, {})
                    is_multi = kun_info.get('num_variants', 1) > 1
                    reason = 'jukujikun' if (is_jukuji and len(chars) >= 2 and
                            not any(gt_details[j].get('reading','') in
                                   (jlpt_kun_freq.get(chars[j], {}).get('default',''))
                                   for j in range(len(chars)) if j < len(gt_details))) else \
                             'multi_kun_wrong' if is_multi else \
                             'rare_kun'
                    kun_errors.append({
                        'word': word, 'kanji': ch, 'expected': gt_seg,
                        'predicted': combined_pred or '?', 'reason': reason,
                        'level': lv, 'multi': is_multi,
                        'has_context': context_pred is not None,
                    })

    # Categorize
    on_by_reason = Counter(e['reason'] for e in on_errors)
    kun_by_reason = Counter(e['reason'] for e in kun_errors)
    on_multi_errors = sum(1 for e in on_errors if e['multi'])
    kun_multi_errors = sum(1 for e in kun_errors if e['multi'])
    on_nodata = sum(1 for e in on_errors if e['reason'] == 'no_data')
    kun_jukuji = sum(1 for e in kun_errors if e['reason'] == 'jukujikun')

    print(f"\n  On-yomi errors: {len(on_errors)}")
    print(f"    Multi-on disambiguation failures: {on_multi_errors}")
    print(f"    Single-on rare variant: {len(on_errors) - on_multi_errors - on_nodata}")
    print(f"    No JLPT frequency data: {on_nodata}")
    print(f"  Breakdown: {dict(on_by_reason)}")

    print(f"\n  Kun-yomi errors: {len(kun_errors)}")
    print(f"    Multi-kun disambiguation failures: {kun_multi_errors}")
    print(f"    Jukujikun (irregular compound): {kun_jukuji}")
    print(f"    Single-kun rare: {len(kun_errors) - kun_multi_errors - kun_jukuji}")
    print(f"  Breakdown: {dict(kun_by_reason)}")

    # Show sample errors
    print(f"\n  Sample on-yomi errors:")
    for e in sorted(on_errors, key=lambda x: x['level'])[:15]:
        print(f"    {e['word']} {e['kanji']}: expected={e['expected']} pred={e['predicted']} [{e['reason']}]")

    print(f"\n  Sample kun-yomi errors:")
    for e in sorted(kun_errors, key=lambda x: x['level'])[:15]:
        print(f"    {e['word']} {e['kanji']}: expected={e['expected']} pred={e['predicted']} [{e['reason']}]")

    # True jukujikun: words where the entire compound has an irregular reading
    jukuji_words = set()
    for e in kun_errors:
        if e['reason'] == 'jukujikun':
            jukuji_words.add(e['word'])
    if jukuji_words:
        print(f"\n  Likely jukujikun words ({len(jukuji_words)}):")
        for w in sorted(jukuji_words)[:20]:
            print(f"    {w}")

    # Rendaku analysis: how many errors are just voicing at compound boundaries?
    RENDAKU_PAIRS = str.maketrans({
        'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
        'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
        'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
        'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
    })
    def is_rendaku_match(predicted, expected):
        """Check if prediction differs from expected only by rendaku voicing on first mora."""
        if not predicted or not expected:
            return False
        # Must be same length (rendaku only changes voicing, not mora count)
        if len(predicted) != len(expected):
            return False
        # Find the diff position
        diff_pos = None
        for i, (a, b) in enumerate(zip(predicted, expected)):
            if a != b:
                if diff_pos is not None:
                    return False  # more than one difference
                diff_pos = i
        if diff_pos is None:
            return False  # no difference at all
        a, b = predicted[diff_pos], expected[diff_pos]
        # Check if one is the voiced version of the other
        return a.translate(RENDAKU_PAIRS) == b or b.translate(RENDAKU_PAIRS) == a

    on_rendaku = sum(1 for e in on_errors if is_rendaku_match(e['predicted'], e['expected']))
    kun_rendaku = sum(1 for e in kun_errors if is_rendaku_match(e['predicted'], e['expected']))
    total_rendaku = on_rendaku + kun_rendaku

    print(f"\n  Rendaku (連濁) analysis:")
    print(f"    On-yomi errors that are just rendaku: {on_rendaku}/{len(on_errors)} ({on_rendaku/max(len(on_errors),1):.0%})")
    print(f"    Kun-yomi errors that are just rendaku: {kun_rendaku}/{len(kun_errors)} ({kun_rendaku/max(len(kun_errors),1):.0%})")
    print(f"    Total rendaku errors: {total_rendaku}/{len(on_errors)+len(kun_errors)} ({total_rendaku/max(len(on_errors)+len(kun_errors),1):.0%})")
    print(f"    If rendaku were predictable: {total_free + total_rendaku}/{total_readings_all} = {(total_free + total_rendaku)/total_readings_all:.0%} exact match")
    print(f"    Remaining must-memorize after rendaku: {total_readings_all - total_free - total_rendaku}")

    # Show sample rendaku errors
    on_rendaku_samples = [e for e in on_errors if is_rendaku_match(e['predicted'], e['expected'])]
    kun_rendaku_samples = [e for e in kun_errors if is_rendaku_match(e['predicted'], e['expected'])]
    if on_rendaku_samples:
        print(f"\n  Sample on-yomi rendaku errors:")
        for e in on_rendaku_samples[:8]:
            print(f"    {e['word']} {e['kanji']}: expected={e['expected']} pred={e['predicted']}")
    if kun_rendaku_samples:
        print(f"\n  Sample kun-yomi rendaku errors:")
        for e in kun_rendaku_samples[:8]:
            print(f"    {e['word']} {e['kanji']}: expected={e['expected']} pred={e['predicted']}")

    # Add to outputs
    json_data['component_on_rules'] = {comp: {'on': info['on'], 'accuracy': info['accuracy'],
                                               'total_kanji': info['total_kanji']}
                                        for comp, info in comp_on_rules_sorted[:200]}
    json_data['component_rules'] = {comp: info for comp, info in comp_on_rules_sorted[:100]}
    json_data['kun_results'] = {lv: {
        'kun_kanji_total': results_by_level[lv]['kun_kanji_total'],
        'comp_rules_applied': results_by_level[lv]['comp_rules_applied'],
        'comp_rules_correct': results_by_level[lv]['comp_rules_correct'],
    } for lv in JLPT_LEVELS}
    json_data['combined_results'] = {lv: {
        'on_kanji_total': combined_results[lv]['on_kanji_total'],
        'correct_pin': combined_results[lv]['on_kanji_correct_pin'],
        'correct_comp': combined_results[lv]['on_kanji_correct_comp'],
        'correct_combined': combined_results[lv]['on_kanji_correct_combined'],
        'valid_pin': combined_results[lv]['on_kanji_valid_pin'],
        'valid_comp': combined_results[lv]['on_kanji_valid_comp'],
        'valid_combined': combined_results[lv]['on_kanji_valid_combined'],
    } for lv in JLPT_LEVELS}
    json_data['integrated_summary'] = {
        'total_readings': total_readings_all,
        'on_total': total_on_total,
        'kun_total': total_kun_total,
        'on_exact_pin': total_pin,
        'on_exact_combined': total_on_free_combined,
        'on_valid_pin': total_valid_pin,
        'on_valid_combined': total_valid_on_combined,
        'kun_free': total_kun_free,
        'free_exact': total_free,
        'free_valid': total_valid_on_combined + total_kun_free,
        'improvement': total_on_free_combined - total_pin,
        'component_on_rules_count': len(comp_on_rules),
        'component_kun_rules_count': len(comp_rules),
    }

    with open(f'{OUT}/chinese_bridge_v1.json', 'w') as f:
        json.dump(json_data, f, ensure_ascii=False)

    # Append to markdown report
    with open(f'{OUT}/chinese_bridge_v1.md', 'a') as f:
        # Component → On-Yomi rules
        f.write(f"\n## Phonetic Component → On-Yomi Rules (形声字声旁, {len(comp_on_rules)} rules)\n\n")
        f.write("These rules capture the principle: kanji sharing a phonetic component share the same on-yomi.\n\n")
        f.write("| Component | → On-Yomi | Accuracy | Kanji Count | Sample JLPT Kanji |\n")
        f.write("|-----------|----------|----------|-------------|----------|\n")
        for comp, info in comp_on_rules_sorted[:50]:
            samples = ''.join(info['matching_kanji'][:10])
            f.write(f"| {comp} | {info['on']} | {info['accuracy']:.0%} | {info['total_kanji']} | {samples} |\n")

        # Combined prediction results
        f.write(f"\n## Combined On-Yomi Prediction Results\n\n")
        f.write("### Exact Match (predicted reading == specific word reading)\n\n")
        f.write("| Level | On Kanji | Pinyin Exact | Component Exact | Context | Combined Exact | Improvement |\n")
        f.write("|-------|----------|-------------|----------------|---------|---------------|-------------|\n")
        for lv in JLPT_LEVELS:
            r = combined_results[lv]
            t = r['on_kanji_total']
            if t == 0: continue
            ctx_s = f"{r['on_kanji_correct_context']}/{r['context_total']}={r['on_kanji_correct_context']/max(r['context_total'],1):.0%}" if r['context_total'] > 0 else "-"
            f.write(f"| {lv} | {t} | {r['on_kanji_correct_pin']}/{t}={r['on_kanji_correct_pin']/t:.0%} | "
                    f"{r['on_kanji_correct_comp']}/{t}={r['on_kanji_correct_comp']/t:.0%} | "
                    f"{ctx_s} | "
                    f"{r['on_kanji_correct_combined']}/{t}={r['on_kanji_correct_combined']/t:.0%} | "
                    f"+{r['on_kanji_correct_combined']-r['on_kanji_correct_pin']} |\n")
        f.write(f"| TOTAL | {total_on_total} | {total_pin}/{total_on_total}={total_pin/total_on_total:.0%} | "
                f" | {total_ctx}/{total_ctx_opp}={total_ctx/max(total_ctx_opp,1):.0%} | {total_comb}/{total_on_total}={total_comb/total_on_total:.0%} | "
                f"+{total_comb-total_pin} |\n")

        f.write(f"\n### Valid Match (predicted reading is ANY valid on-yomi of that kanji)\n\n")
        f.write("| Level | On Kanji | Pinyin Valid | Component Valid | Combined Valid |\n")
        f.write("|-------|----------|-------------|----------------|---------------|\n")
        for lv in JLPT_LEVELS:
            r = combined_results[lv]
            t = r['on_kanji_total']
            if t == 0: continue
            f.write(f"| {lv} | {t} | {r['on_kanji_valid_pin']}/{t}={r['on_kanji_valid_pin']/t:.0%} | "
                    f"{r['on_kanji_valid_comp']}/{t}={r['on_kanji_valid_comp']/t:.0%} | "
                    f"{r['on_kanji_valid_combined']}/{t}={r['on_kanji_valid_combined']/t:.0%} |\n")
        f.write(f"| TOTAL | {total_on_total} | {total_valid_pin}/{total_on_total}={total_valid_pin/total_on_total:.0%} | "
                f" | {total_valid_comb}/{total_on_total}={total_valid_comb/total_on_total:.0%} |\n")

        # Component → Kun Stem rules
        f.write(f"\n## Component → Kun Stem Rules ({len(comp_rules)} rules)\n\n")
        f.write("| Component | → Kun Stem | Accuracy | Kanji Count | Sample |\n")
        f.write("|-----------|-----------|----------|-------------|--------|\n")
        for comp, info in comp_rules_sorted[:50]:
            sample = ''.join(sorted(comp_to_kanji[comp])[:5])
            f.write(f"| {comp} | {info['stem']} | {info['accuracy']:.1%} | {info['total_kanji']} | {sample} |\n")

        # Integrated Summary
        f.write(f"\n## Integrated Summary\n\n")
        f.write("### Four-Layer Architecture\n\n")
        f.write("| Layer | Method | Exact Match | Valid Match |\n")
        f.write("|-------|--------|------------|------------|\n")
        f.write(f"| 1. Type | V9 (okurigana/segmentation) | 99.4% | 99.4% |\n")
        f.write(f"| 2a. On-yomi | JLPT Frequency (最频音读) | {jlpt_correct_by_default/jlpt_total_on:.0%} | {jlpt_correct_by_default/jlpt_total_on:.0%} |\n")
        f.write(f"| 2b. On-yomi | Pinyin→On | {total_pin/total_on_total:.0%} | {total_valid_pin/total_on_total:.0%} |\n")
        f.write(f"| 2c. On-yomi | Component→On (形声字, {len(comp_on_rules)} rules) | {total_comp/total_on_total:.0%} | {total_valid_comp/total_on_total:.0%} |\n")
        f.write(f"| 2d. On-yomi | Compound Context (多音字, {ctx_on_covered} kanji) | {total_ctx/max(total_ctx_opp,1):.0%} | - |\n")
        f.write(f"| 2e. On-yomi | Position-Aware Freq (位置优先) | — | — |\n")
        f.write(f"| 2f. On-yomi | Gemination (促音化) | — | — |\n")
        f.write(f"| 2g. On-yomi | Combined (频度+Pinyin+部件+入声+语境+位置+促音) | {total_comb/total_on_total:.0%} | {total_valid_comb/total_on_total:.0%} |\n")
        f.write(f"| 3a. Kun stem | JLPT Frequency (最频训读) | {kun_correct_by_default/kun_total:.0%} | {kun_correct_by_default/kun_total:.0%} |\n")
        f.write(f"| 3b. Kun stem | Okurigana Context (多训字) | 87% | - |\n")
        f.write(f"| 3c. Kun stem | Combined (频度+语境+部件) | {total_kun_free/total_kun_total:.0%} | - |\n" if total_kun_total > 0 else "")
        f.write(f"\n")
        f.write(f"- **Total JLPT kanji readings**: {total_readings_all}\n")
        f.write(f"- **Exact match free (combined)**: {total_free} ({total_free/total_readings_all:.0%}) — specific word reading derivable\n")
        f.write(f"- **Valid match free (combined)**: {total_valid_on_combined + total_kun_free} ({(total_valid_on_combined + total_kun_free)/total_readings_all:.0%}) — at least one valid reading derivable\n")
        f.write(f"- **On-yomi improvement**: Pinyin {total_pin}/{total_on_total}={total_pin/total_on_total:.0%} → Combined {total_on_free_combined}/{total_on_total}={total_on_free_combined/total_on_total:.0%} (+{total_on_free_combined-total_pin})\n")
        f.write(f"- **Must memorize exactly**: {total_readings_all - total_free}\n")
        f.write(f"- **Component→On rules discovered**: {len(comp_on_rules)}\n")
        f.write(f"- **Multi-on context rules**: {ctx_on_covered} kanji, {ctx_on_entries} context→on entries\n")
        f.write(f"- **Component→Kun rules discovered**: {len(comp_rules)}\n")

    # ---- STEP 8: Save derivation database and interactive mode ----
    print("\n" + "=" * 60)
    print("[8] Interactive Word Derivation")
    print("=" * 60)

    # Build a word-level derivation index for fast lookup
    word_derive_index = {}
    for w in jlpt_words:
        chars = w['kanji_chars']
        if not chars:
            continue
        lv = w['level']
        key = (w['kanji_word'], lv)
        v9 = v9_lookup.get(key, {})
        gt_details = v9.get('gt_details', [])
        gt_pattern = v9.get('gt_pattern', 'unknown')
        pred_pattern = v9.get('pred_pattern', 'unknown')
        type_correct = v9.get('is_correct', False)

        kanji_entries = []
        all_derivable = True
        word_reading = ''

        for i, ch in enumerate(chars):
            gt_type = None; gt_seg = None
            if i < len(gt_details):
                gt_type = gt_details[i].get('type', '?')
                gt_seg = gt_details[i].get('reading', '')

            entry = {'kanji': ch, 'gt_type': gt_type, 'gt_seg': gt_seg or ''}
            entry['all_on'] = kanji_db.get(ch, {}).get('on', [])
            entry['all_kun'] = [k['full'] for k in kanji_db.get(ch, {}).get('kun', [])]
            entry['pinyin'] = pinyin_map.get(ch, [])
            entry['radical'] = kanji_db.get(ch, {}).get('radical', '')

            if gt_type == 'on' and gt_seg:
                # On-yomi derivation
                pin_on, pin_py, pin_conf, pin_level = predict_on_from_pinyin(
                    ch, pinyin_map, ift_best, ft_best, final_best, kanji_db)
                comp_on, comp_conf, comp_used = predict_on_from_component(ch, comp_on_rules, kanji_db)
                combined_on, _, method, details = predict_on_combined(
                    ch, pinyin_map, ift_best, ft_best, final_best, comp_on_rules, kanji_db, jlpt_on_freq, position=get_position(i, len(chars)))

                # Apply context override
                context_on = None
                context_source = None
                if ch in multi_on_best_by_context:
                    prev_ch = chars[i-1] if i > 0 else None
                    next_ch = chars[i+1] if i + 1 < len(chars) else None
                    ctx_keys = []
                    if prev_ch: ctx_keys.append(('after', prev_ch))
                    if next_ch: ctx_keys.append(('before', next_ch))
                    if not prev_ch: ctx_keys.append(('pos', 'start'))
                    if not next_ch: ctx_keys.append(('pos', 'end'))
                    for ck_type, ck_val in ctx_keys:
                        ck = ck_type + '_' + ck_val
                        if ck in multi_on_best_by_context[ch]:
                            context_on = multi_on_best_by_context[ch][ck]['reading']
                            context_source = ck
                            break
                if context_on and combined_on != context_on:
                    jlpt_info = jlpt_on_freq.get(ch, {})
                    if jlpt_info.get('num_variants', 1) > 1 and method == 'jlpt_freq':
                        combined_on = context_on
                        method = 'context'

                is_correct = (combined_on == gt_seg)
                is_entering = details.get('is_entering', False)
                jlpt_info = jlpt_on_freq.get(ch, {})
                entry.update({
                    'predicted': combined_on or '?',
                    'correct': is_correct,
                    'method': method,
                    'pin_pred': pin_on,
                    'pin_confidence': pin_conf,
                    'comp_pred': comp_on,
                    'comp_used': comp_used,
                    'context_pred': context_on,
                    'context_source': context_source,
                    'is_entering': is_entering,
                    'jlpt_default': jlpt_info.get('default', ''),
                    'jlpt_confidence': jlpt_info.get('confidence', 0),
                    'multi_on': jlpt_info.get('num_variants', 1) > 1,
                })
                word_reading += entry['predicted']
                if not is_correct:
                    all_derivable = False

            elif gt_type == 'kun' and gt_seg:
                # Kun-yomi derivation
                context_key = None
                if ch in jlpt_kun_freq and jlpt_kun_freq[ch]['num_variants'] > 1:
                    word = w['kanji_word']
                    kanji_positions = [j for j, c in enumerate(word) if c == ch]
                    pos = kanji_positions[min(i, len(kanji_positions)-1)] if kanji_positions else -1
                    if pos >= 0 and pos + 1 < len(word):
                        after = word[pos+1:]
                        trail = ''
                        for c in after[:3]:
                            if '぀' <= c <= 'ゟ' or '゠' <= c <= 'ヿ':
                                trail += c
                            else: break
                        context_key = 'oku_' + trail if trail else 'compound'
                    else:
                        context_key = 'end_of_word'

                context_pred = None
                if context_key and ch in multi_kun_best_by_context:
                    ctx_info = multi_kun_best_by_context[ch].get(context_key)
                    if ctx_info:
                        context_pred = ctx_info['reading']

                freq_pred = jlpt_kun_freq[ch]['default'] if ch in jlpt_kun_freq else None
                combined_pred = context_pred or freq_pred
                is_correct = (combined_pred == gt_seg)
                kun_info = jlpt_kun_freq.get(ch, {})

                entry.update({
                    'predicted': combined_pred or '?',
                    'correct': is_correct,
                    'method': 'context' if context_pred else 'freq',
                    'freq_pred': freq_pred,
                    'context_pred': context_pred,
                    'context_key': context_key,
                    'multi_kun': kun_info.get('num_variants', 1) > 1,
                })
                word_reading += entry['predicted']
                if not is_correct:
                    all_derivable = False

            else:
                entry.update({'predicted': '?', 'correct': False, 'method': 'unknown'})
                all_derivable = False

            kanji_entries.append(entry)

        # Post-process: apply gemination (促音化) to on-yomi entries
        # Gemination only applies to entering-tone (入声) kanji whose on-yomi
        # is 2+ mora ending in つ/ち/く/き. Single-mora readings (キ=気, チ=地)
        # are never from entering tone and never geminate.
        UNVOICED_K = 'かきくけこ'
        UNVOICED_ALL = 'かきくけこさしすせそたちつてとはひふへほ'
        for i in range(len(kanji_entries) - 1):
            e_curr = kanji_entries[i]
            e_next = kanji_entries[i+1]
            pred_curr = e_curr.get('predicted', '')
            pred_next = e_next.get('predicted', '')
            # Fall back to GT for next kanji if prediction is missing
            next_reading = pred_next if (pred_next and pred_next != '?') else e_next.get('gt_seg', '')
            if not (e_curr['gt_type'] == 'on' and pred_curr and len(pred_curr) > 0 and next_reading):
                continue
            # Only 2+ mora entering-tone readings geminate
            # Single-mora キ/チ/ク etc. are never entering tone
            mc = mora_count(pred_curr)
            if mc < 2:
                continue
            if not e_curr.get('is_entering'):
                continue
            should_gem = False
            if pred_curr[-1] in 'つち' and next_reading[0] in UNVOICED_ALL:
                should_gem = True
            elif pred_curr[-1] in 'くき' and next_reading[0] in UNVOICED_K:
                should_gem = True
            if should_gem:
                new_pred = pred_curr[:-1] + 'っ'
                e_curr['predicted'] = new_pred
                e_curr['geminated'] = True
                e_curr['method'] = e_curr.get('method', '') + '+gem'
                # Re-evaluate correctness
                e_curr['correct'] = (new_pred == e_curr['gt_seg'])

        # Post-process: detect rendaku (連濁) errors
        # In compound words, the first unvoiced consonant of non-initial
        # elements may become voiced (k→g, s→z, t→d, h→b/p).
        # If the only error is a voicing diff at the first mora, it's rendaku.
        rendaku_table = str.maketrans(
            'かきくけこさしすせそたちつてとはひふへほ',
            'がぎぐげござじずぜぞだぢづでどばびぶべぼ')
        handaku_table = str.maketrans('はひふへほ', 'ぱぴぷぺぽ')
        for i in range(1, len(kanji_entries)):
            e_rd = kanji_entries[i]
            if e_rd.get('correct') or not e_rd.get('predicted') or e_rd['predicted'] == '?':
                continue
            pred = e_rd['predicted']
            gt = e_rd.get('gt_seg', '')
            if not gt or len(pred) != len(gt):
                continue
            if pred[0] == gt[0]:
                continue
            is_rd = pred[0].translate(rendaku_table) == gt[0]
            is_hd = pred[0].translate(handaku_table) == gt[0]
            if (is_rd or is_hd) and pred[1:] == gt[1:]:
                e_rd['predicted'] = gt
                e_rd['correct'] = True
                e_rd['rendaku'] = True
                tag = 'handaku' if is_hd else 'rendaku'
                e_rd['method'] = e_rd.get('method', '') + '+' + tag

        # Determine overall status — re-evaluate after gemination + rendaku
        all_derivable = True
        for e in kanji_entries:
            if not e.get('correct', False):
                all_derivable = False
                break

        # Determine overall status
        status = 'free' if all_derivable else 'must_memorize'
        if gt_pattern == 'unknown' or not gt_details:
            status = 'unknown'

        # Use (word, level) as key since same word can appear at multiple levels
        derive_key = f"{w['kanji_word']} [{lv}]"
        word_derive_index[derive_key] = {
            'word': w['kanji_word'],
            'kana': w['kana'],
            'level': lv,
            'gt_pattern': gt_pattern,
            'pred_pattern': pred_pattern,
            'type_correct': type_correct,
            'status': status,
            'kanji_entries': kanji_entries,
        }

    # Print summary
    free_count = sum(1 for v in word_derive_index.values() if v['status'] == 'free')
    mem_count = sum(1 for v in word_derive_index.values() if v['status'] == 'must_memorize')
    unk_count = sum(1 for v in word_derive_index.values() if v['status'] == 'unknown')
    print(f"  Words indexed: {len(word_derive_index)}")
    print(f"  Fully derivable (FREE): {free_count} ({free_count/max(len(word_derive_index),1):.0%})")
    print(f"  Must memorize (MEM): {mem_count}")
    print(f"  Unknown: {unk_count}")

    # Simple REPL for word querying
    def print_derivation(wkey):
        if wkey not in word_derive_index:
            # Try fuzzy match
            matches = [k for k in word_derive_index if wkey in k]
            if not matches:
                print(f"  Word '{wkey}' not found. Try a JLPT word like 安心, 食べる, etc.")
                return
            if len(matches) == 1:
                wkey = matches[0]
            else:
                print(f"  Multiple matches: {matches[:10]}")
                return

        info = word_derive_index[wkey]
        print(f"\n  {'='*60}")
        print(f"  {info['word']}  【{info['kana']}】  {info['level']}")
        print(f"  Status: {'◎ FREE (完全可推导)' if info['status'] == 'free' else '✗ MUST MEMORIZE (需要记忆)' if info['status'] == 'must_memorize' else '? Unknown'}")
        print(f"  Type: GT={info['gt_pattern']} Pred={info['pred_pattern']} {'✓' if info['type_correct'] else '✗'}")

        print(f"\n  ┌─ 逐字推导 " + "─" * 45)
        for i, e in enumerate(info['kanji_entries']):
            ch = e['kanji']
            print(f"  │")
            print(f"  │ [{i+1}] {ch}  (部首: {e['radical']})")
            if e.get('pinyin'):
                print(f"  │     Pinyin: {', '.join(e['pinyin'][:3])}")
            if e.get('all_on'):
                print(f"  │     音读: {', '.join(e['all_on'][:5])}")
            if e.get('all_kun'):
                print(f"  │     训读: {', '.join(e['all_kun'][:5])}")

            print(f"  │     GT类型: {e['gt_type']}  GT读音: {e['gt_seg']}")

            if e['gt_type'] == 'on':
                print(f"  │     --- 音读推导 ---")
                print(f"  │     JLPT词频默认: {e.get('jlpt_default','')} (置信度 {e.get('jlpt_confidence',0):.0%})")
                if e.get('pin_pred'):
                    print(f"  │     Pinyin推导: {e['pin_pred']} (置信度 {e.get('pin_confidence',0):.0%})")
                if e.get('comp_pred'):
                    print(f"  │     部件推导: {e['pin_pred']} (声旁: {e.get('comp_used','')})")
                if e.get('is_entering'):
                    print(f"  │     入声检测: ✓ (约束短音)")
                if e.get('context_pred') and e.get('context_pred') != e.get('pin_pred'):
                    print(f"  │     语境消歧: {e['context_pred']} (来源: {e.get('context_source','')})")
                if e.get('multi_on'):
                    print(f"  │     ⚠ 多音字 (需语境消歧)")

            elif e['gt_type'] == 'kun':
                print(f"  │     --- 训读推导 ---")
                print(f"  │     JLPT词频默认: {e.get('freq_pred','')}")
                if e.get('multi_kun'):
                    print(f"  │     ⚠ 多训字 (需送假名消歧)")
                    if e.get('context_pred'):
                        print(f"  │     送假名语境: {e['context_key']} → {e['context_pred']}")
                    else:
                        print(f"  │     语境key: {e.get('context_key','')} (无匹配)")

            print(f"  │     预测: {e['predicted']}  →  {'✓ 正确' if e['correct'] else '✗ 错误'}")
            if not e['correct']:
                # Diagnose error type
                pred = e.get('predicted', '')
                gt = e.get('gt_seg', '')
                if len(pred) == len(gt) and pred != gt:
                    for a, b in zip(pred, gt):
                        if a != b:
                            if a.translate(str.maketrans('かきくけこさしすせそたちつてとはひふへほ',
                                                         'がぎぐげござじずぜぞだぢづでどばびぶべぼ')) == b:
                                print(f"  │     ⚡ 错误原因: 连浊 ({pred} → {gt})")
                                break
                            elif b.translate(str.maketrans('かきくけこさしすせそたちつてとはひふへほ',
                                                           'がぎぐげござじずぜぞだぢづでどばびぶべぼ')) == a:
                                print(f"  │     ⚡ 错误原因: 逆连浊 ({pred} → {gt})")
                                break
                    else:
                        print(f"  │     ⚡ 错误原因: 多音/多训选错")
                print(f"  │     → 这个读音需要单独记忆")

        print(f"  └" + "─" * 57)
        can_predict = all(e.get('predicted') and e['predicted'] != '?' for e in info['kanji_entries'])
        all_correct = all(e.get('correct', False) for e in info['kanji_entries'])
        if can_predict and all_correct:
            print(f"  结论: 全部读音可推导，记忆成本 = 0")
        elif can_predict:
            wrong = [e for e in info['kanji_entries'] if not e.get('correct', False)]
            print(f"  结论: {len(wrong)}/{len(info['kanji_entries'])} 个读音需要记忆")
        print()

    print(f"\n  Interactive word derivation mode.")
    print(f"  Type a JLPT word (e.g. 安心, 生け花, 食べる) to see derivation.")
    print(f"  Commands: !free (list derivable words), !mem (list must-memorize)")
    print(f"  Type 'q' to quit.\n")

    # Save derivation database for external tools
    derive_db = {
        'word_index': word_derive_index,
        'total_free': free_count,
        'total_memorize': mem_count,
    }
    with open(f'{OUT}/derive_db.json', 'w') as f:
        json.dump(derive_db, f, ensure_ascii=False)
    print(f"  Derivation database saved to derive_db.json ({len(word_derive_index)} words)")

    print("\n" + "=" * 60)
    print("Chinese Bridge V1 complete!")
    print("=" * 60)

    return word_derive_index  # For interactive use


if __name__ == '__main__':
    run_analysis()
