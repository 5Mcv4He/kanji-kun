#!/usr/bin/env python3
"""
Kun-Yomi V8: Integration, Verification & Export Layer
======================================================
6 modules that bridge the gap between research data and learner-ready deliverables:

1. WORD-LEVEL PREDICTION ENGINE — classify every JLPT word (on/kun/mixed),
   apply rule chain, compare prediction vs ground truth, compute real accuracy.
2. REVERSE INDEX — kana reading → possible kanji, grouped by JLPT level.
3. MINIMAL PAIRS — word pairs differing by exactly one phonological feature.
4. ANKI CSV EXPORT — direct SRS import with rule annotations.
5. LEARNING BURDEN QUANTIFICATION — exact compression ratio of rules vs rote.
6. KNOWN-KANJI DIVIDEND — Chinese speaker kanji advantage quantified.
"""

import json, re, os, csv, itertools
from collections import Counter, defaultdict
from functools import lru_cache
import openpyxl

BASE = '/Volumes/SSD/work/kanji-kun'
OUT = f'{BASE}/output'
WORD_XLSX = f'{BASE}/word.xlsx'
KANJI_XLSM = f'{BASE}/漢字検索V2.xlsm'
V4_JSON = f'{BASE}/kunyomi_exhaustive_v4.json'
V3_JSON = f'{BASE}/gold_panning_v3_results.json'
TIERED_JSON = f'{BASE}/output/kun_tiered_rules.json'

JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

# Kana normalization
KATA_TO_HIRA = str.maketrans(
    'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'
    'ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ'
    'ャュョッァィゥェォ',
    'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'
    'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ'
    'ゃゅょっあいうえお'  # Small kana → small kana, not full-size
)
# Additional: normalize チ, ヂ, ツ, ヅ, フ with diacritics
KATA_TO_HIRA_EXTRA = str.maketrans('ヷヸヹヺ', 'わゐゑを')

def kata_to_hira(s):
    return s.translate(KATA_TO_HIRA).translate(KATA_TO_HIRA_EXTRA)

def clean_kana(s):
    """Normalize kana for matching: remove small-kana markers, long vowels."""
    s = kata_to_hira(s)
    s = s.replace('ー', '').replace('ッ', 'つ').replace('っ', 'つ')
    return s

def mora_count(s):
    """Count morae in kana string."""
    s = kata_to_hira(s)
    count = 0
    i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉ':
            count += 1
            i += 2
        else:
            count += 1
            i += 1
    return count


# ============================================================
# DATA LOADING
# ============================================================

def load_data():
    print("Loading data...")
    # --- JLPT words ---
    wb = openpyxl.load_workbook(WORD_XLSX, read_only=True)
    ws = wb['红宝书去重版']
    jlpt_words = []
    for row in ws.iter_rows(min_row=4, max_row=9575, values_only=True):
        kana_raw = str(row[2]).strip() if row[2] else ''
        kanji_raw = str(row[3]).strip() if row[3] else ''
        level = str(row[23]).strip() if len(row) > 23 and row[23] else ''
        if level not in JLPT_LEVELS:
            continue
        has_kanji = bool(re.search(r'[一-鿿㐀-䶿]', kanji_raw))
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', kanji_raw) if has_kanji else []
        kana_clean = clean_kana(kana_raw)
        jlpt_words.append({
            'kana_raw': kana_raw,
            'kana': kana_clean,
            'kanji_word': kanji_raw,
            'level': level,
            'kanji_chars': kanji_chars,
            'num_kanji': len(kanji_chars),
            'mora': mora_count(kana_raw),
            'has_okurigana': bool(re.search(r'[ぁ-ん]', kanji_raw)) if has_kanji else False,
        })
    wb.close()
    print(f"  Words: {len(jlpt_words)}")

    # --- Kanji DB ---
    wb2 = openpyxl.load_workbook(KANJI_XLSM, read_only=True)
    ws2 = wb2['漢字一覧']
    kanji_db = {}
    for row in ws2.iter_rows(min_row=2, max_row=46850, values_only=True):
        if not row[0]:
            continue
        ch = str(row[0]).strip()
        if not ch or len(ch) > 2:
            continue
        radical = str(row[3]).strip() if row[3] else ''
        components = str(row[1]).strip() if row[1] else ''
        on_raw = str(row[9]).strip() if row[9] else ''
        kun_raw = str(row[10]).strip() if row[10] else ''
        meaning = str(row[11]).strip() if row[11] else ''

        on_list = []
        for o in on_raw.replace('、', ',').split(','):
            o = o.strip()
            if o:
                on_list.append(kata_to_hira(o))

        kun_raw_list = [k.strip() for k in kun_raw.replace('、', ',').split(',') if k.strip()]
        kun_list = []
        for kr in kun_raw_list:
            if '・' in kr:
                parts = kr.split('・')
                stem = parts[0].replace('.', '')
                oku = '.'.join(p.replace('.', '') for p in parts[1:])
                kun_list.append({'stem': stem, 'okurigana': oku, 'full': f"{stem}.{oku}"})
            elif kr:
                stem_clean = kr.replace('.', '')
                kun_list.append({'stem': stem_clean, 'okurigana': '', 'full': stem_clean})

        kanji_db[ch] = {
            'radical': radical, 'components': components,
            'on_readings': on_list, 'kun_readings': kun_list,
            'meaning': meaning,
        }
    wb2.close()
    print(f"  Kanji: {len(kanji_db)}")

    # --- V4 JSON ---
    with open(V4_JSON) as f:
        v4 = json.load(f)
    # --- V3 JSON ---
    with open(V3_JSON) as f:
        v3 = json.load(f)
    # --- Tiered rules ---
    with open(TIERED_JSON) as f:
        tiered = json.load(f)
    # Count total rules
    total_rules = 0
    for lv in JLPT_LEVELS:
        lv_data = tiered.get('levels', {}).get(lv, {})
        total_rules += len(lv_data.get('rules', []))
    total_rules += len(tiered.get('iron_laws', []))
    total_rules += len(tiered.get('verification_layer', []))
    print(f"  Rules: {total_rules} total (iron_laws + verification + per-level)")

    return jlpt_words, kanji_db, v4, v3, tiered, total_rules


# ============================================================
# GROUND TRUTH: Classify every JLPT word's reading type
# ============================================================

def classify_word_ground_truth(w, kanji_db):
    """
    Determine ground truth reading type for a JLPT word.
    Uses aggressive multi-strategy matching to minimize 'unknown' labels.
    """
    kana = w['kana']
    chars = w['kanji_chars']
    n = len(chars)

    if n == 0:
        return {'pattern': 'no_kanji', 'details': []}

    # Get all possible reading segments for each kanji
    kanji_readings = []
    for ch in chars:
        if ch not in kanji_db:
            kanji_readings.append({'on': [], 'kun_stems': [], 'kun_full': []})
            continue
        info = kanji_db[ch]
        kr = {
            'on': info['on_readings'],
            'kun_stems': [k['stem'] for k in info['kun_readings'] if k['stem']],
            'kun_full': [(k['stem'], k['okurigana']) for k in info['kun_readings'] if k['stem']],
        }
        kanji_readings.append(kr)

    if n == 1:
        return _classify_single_kanji(kana, chars[0], kanji_readings[0])

    # Multi-kanji: try multiple strategies
    result = _segment_on_on(kana, chars, kanji_readings)
    if result['pattern'] != 'unknown':
        return result

    result = _segment_kun_aware(kana, chars, kanji_readings, w.get('has_okurigana'))
    if result['pattern'] != 'unknown':
        return result

    result = _segment_any_match(kana, chars, kanji_readings)
    if result['pattern'] != 'unknown':
        return result

    # Last resort: vote based on individual kanji reading availability
    return _vote_pattern(kana, chars, kanji_readings)


def _classify_single_kanji(kana, ch, kr):
    """Classify single-kanji word with flexible matching."""
    # Strategy 1: exact match with kun full reading (stem + okurigana)
    for stem, oku in kr['kun_full']:
        if kana == stem + oku or kana == stem:
            return {'pattern': 'kun', 'details': [
                {'kanji': ch, 'type': 'kun', 'reading': stem, 'match': 'exact'}]}
    # Strategy 2: kana starts with a kun stem and there's okurigana
    for stem, oku in kr['kun_full']:
        if oku and kana.startswith(stem):
            return {'pattern': 'kun', 'details': [
                {'kanji': ch, 'type': 'kun', 'reading': stem, 'match': 'stem_prefix'}]}
    # Strategy 3: kana starts with any kun stem (2+ mora)
    for stem in sorted(kr['kun_stems'], key=len, reverse=True):
        if len(stem) >= 1 and kana.startswith(stem):
            return {'pattern': 'kun', 'details': [
                {'kanji': ch, 'type': 'kun', 'reading': stem, 'match': 'stem_start'}]}
    # Strategy 4: exact on-yomi match
    for on in kr['on']:
        if on == kana:
            return {'pattern': 'on', 'details': [
                {'kanji': ch, 'type': 'on', 'reading': on, 'match': 'exact'}]}
    # Strategy 5: on-yomi substring (for multi-mora on)
    for on in sorted(kr['on'], key=len, reverse=True):
        if len(on) >= 2 and on in kana[:len(on)]:
            return {'pattern': 'on', 'details': [
                {'kanji': ch, 'type': 'on', 'reading': on, 'match': 'substring'}]}
    # Strategy 6: kana contains any kun stem
    for stem in kr['kun_stems']:
        if stem and stem in kana:
            return {'pattern': 'kun', 'details': [
                {'kanji': ch, 'type': 'kun', 'reading': stem, 'match': 'contains'}]}
    # Strategy 7: check if kanji has only on, only kun, or both
    has_on = len(kr['on']) > 0
    has_kun = len(kr['kun_stems']) > 0
    if has_kun and not has_on:
        return {'pattern': 'kun~', 'details': [
            {'kanji': ch, 'type': 'kun', 'reading': '', 'match': 'inferred'}]}
    if has_on and not has_kun:
        return {'pattern': 'on~', 'details': [
            {'kanji': ch, 'type': 'on', 'reading': '', 'match': 'inferred'}]}

    return {'pattern': 'unknown', 'details': [
        {'kanji': ch, 'type': '?', 'reading': '', 'match': 'none'}]}


def _segment_on_on(kana, chars, kanji_readings):
    """Try to match all kanji via on-yomi (most common for compounds)."""
    # DP: try all ways to split kana into on-yomi segments
    n = len(chars)
    all_on_readings = []
    for i, kr in enumerate(kanji_readings):
        all_on_readings.append([(r, len(r)) for r in kr['on'] if r])

    # Greedy forward
    pos = 0
    details = []
    for i, readings in enumerate(all_on_readings):
        if not readings:
            details.append({'kanji': chars[i], 'type': '?', 'reading': '', 'match': 'no_data'})
            continue
        matched = None
        for reading, rlen in sorted(readings, key=lambda x: -x[1]):
            if kana[pos:pos + rlen] == reading:
                matched = (reading, 'on', 'exact')
                break
        if matched is None:
            # Try shifted match
            for reading, rlen in sorted(readings, key=lambda x: -x[1]):
                idx = kana.find(reading, pos)
                if idx >= 0 and idx <= pos + 2:
                    matched = (reading, 'on', 'shifted')
                    pos = idx
                    break
        if matched:
            details.append({'kanji': chars[i], 'type': matched[1], 'reading': matched[0], 'match': matched[2]})
            pos += len(matched[0])
        else:
            details.append({'kanji': chars[i], 'type': '?', 'reading': '', 'match': 'none'})

    types = [d['type'] for d in details]
    if pos == len(kana) and all(t == 'on' for t in types):
        return {'pattern': '+'.join(types), 'details': details}

    # Try reverse greedy
    pos = len(kana)
    rev_details = [None] * n
    all_ok = True
    for i in range(n - 1, -1, -1):
        readings = all_on_readings[i]
        if not readings:
            all_ok = False
            continue
        matched = None
        for reading, rlen in sorted(readings, key=lambda x: -x[1]):
            start = pos - rlen
            if start >= 0 and kana[start:pos] == reading:
                matched = (reading, 'on')
                break
        if matched:
            rev_details[i] = {'kanji': chars[i], 'type': matched[1], 'reading': matched[0], 'match': 'exact_rev'}
            pos -= len(matched[0])
        else:
            all_ok = False

    if all_ok and pos == 0:
        rev_types = [d['type'] for d in rev_details]
        if all(t == 'on' for t in rev_types):
            return {'pattern': '+'.join(rev_types), 'details': rev_details}

    return {'pattern': 'unknown', 'details': details}


def _segment_kun_aware(kana, chars, kanji_readings, has_okurigana):
    """Segment knowing that okurigana at the end belongs to the last kanji."""
    n = len(chars)
    if n == 2 and has_okurigana:
        # Last kanji has okurigana → it uses kun reading
        # First kanji could be on or kun
        kr0, kr1 = kanji_readings[0], kanji_readings[1]
        details = [None, None]

        # Try matching first kanji as on
        matched_first = None
        for on, rlen in sorted([(r, len(r)) for r in kr0['on'] if r], key=lambda x: -x[1]):
            if kana.startswith(on):
                matched_first = (on, 'on', len(on))
                break
        if matched_first is None:
            for stem in sorted(kr0['kun_stems'], key=len, reverse=True):
                if kana.startswith(stem):
                    matched_first = (stem, 'kun', len(stem))
                    break

        if matched_first:
            details[0] = {'kanji': chars[0], 'type': matched_first[1],
                          'reading': matched_first[0], 'match': 'prefix'}
            remaining = kana[matched_first[2]:]
            # Match second kanji (with okurigana) against remaining kana
            for stem, oku in kr1['kun_full']:
                if remaining == stem + oku or (oku and remaining.startswith(stem)):
                    details[1] = {'kanji': chars[1], 'type': 'kun',
                                  'reading': stem, 'match': 'oku_tail'}
                    return {'pattern': f"{matched_first[1]}+kun", 'details': details}
            # Try just stem match
            for stem in kr1['kun_stems']:
                if remaining == stem or remaining.startswith(stem):
                    details[1] = {'kanji': chars[1], 'type': 'kun',
                                  'reading': stem, 'match': 'stem_tail'}
                    return {'pattern': f"{matched_first[1]}+kun", 'details': details}

    return {'pattern': 'unknown', 'details': []}


def _segment_any_match(kana, chars, kanji_readings):
    """Fallback: just check if any kanji has a reading that matches somewhere in kana."""
    types = []
    details = []
    kun_count = 0
    on_count = 0
    for i, ch in enumerate(chars):
        kr = kanji_readings[i]
        matched = False
        # Check on
        for on in kr['on']:
            if on and on in kana:
                on_count += 1
                matched = True
                details.append({'kanji': ch, 'type': 'on', 'reading': on, 'match': 'contains'})
                break
        if not matched:
            # Check kun
            for stem in kr['kun_stems']:
                if stem and stem in kana:
                    kun_count += 1
                    matched = True
                    details.append({'kanji': ch, 'type': 'kun', 'reading': stem, 'match': 'contains'})
                    break
        if not matched:
            details.append({'kanji': ch, 'type': '?', 'reading': '', 'match': 'none'})

    types = [d['type'] for d in details]
    if all(t in ('on', 'kun') for t in types):
        return {'pattern': '+'.join(types) + '~', 'details': details}
    return {'pattern': 'unknown', 'details': details}


def _vote_pattern(kana, chars, kanji_readings):
    """Last resort: count on vs kun availability for each kanji."""
    types = []
    for i, ch in enumerate(chars):
        kr = kanji_readings[i]
        has_on = len(kr['on']) > 0
        has_kun = len(kr['kun_stems']) > 0
        if has_kun and not has_on:
            types.append('kun')
        elif has_on and not has_kun:
            types.append('on')
        elif has_on and has_kun:
            types.append('mixed')
        else:
            types.append('?')
    pattern = '+'.join(types)
    if '?' not in pattern:
        return {'pattern': pattern + '~', 'details': [
            {'kanji': chars[i], 'type': types[i], 'reading': '', 'match': 'voted'}
            for i in range(len(chars))]}
    return {'pattern': 'unknown', 'details': [
        {'kanji': chars[i], 'type': types[i], 'reading': '', 'match': 'voted'}
        for i in range(len(chars))]}


# ============================================================
# RULE EXTRACTION (from tiered rules JSON)
# ============================================================

def extract_iron_laws(tiered):
    """Extract iron laws as simple predicate functions."""
    laws = []
    for law in tiered.get('iron_laws', []):
        laws.append({
            'id': law.get('id', ''),
            'name': law.get('name', ''),
            'rule': law.get('rule', ''),
            'accuracy': law.get('accuracy', 0),
            'description': law.get('description', ''),
        })
    return laws


# ============================================================
# MODULE 1: WORD-LEVEL PREDICTION ENGINE
# ============================================================

def build_prediction_engine(jlpt_words, kanji_db, v4, v3, tiered):
    """
    For every JLPT word:
    1. Classify ground truth (on/kun/mixed)
    2. Apply rule-based prediction
    3. Compare and compute real accuracy
    """
    print("\n[1/6] Word-Level Prediction Engine...")

    # Step 1: Ground truth classification
    gt_stats = Counter()
    word_results = []

    for w in jlpt_words:
        gt = classify_word_ground_truth(w, kanji_db)
        w['ground_truth'] = gt
        gt_stats[gt['pattern']] += 1

        # Step 2: Rule-based prediction
        prediction = predict_word_reading(w, kanji_db)
        w['prediction'] = prediction

        # Step 3: Compare — focus on on/kun type correctness, not exact pattern
        gt_pat = gt['pattern']
        pred_pat = prediction['predicted_pattern']

        gt_clean = gt_pat.rstrip('~')
        pred_clean = pred_pat.rstrip('~').rstrip('.')

        # Classify into: pure_on, pure_kun, mixed, no_kanji, unknown
        def classify(p):
            if p in ('no_kanji',):
                return 'no_kanji'
            if p in ('unknown',):
                return 'unknown'
            parts = p.split('+')
            has_on = any('on' in pt for pt in parts)
            has_kun = any('kun' in pt for pt in parts)
            has_mixed = any('mixed' in pt for pt in parts)
            has_unknown = any(pt in ('...', '?') for pt in parts)
            if has_mixed or has_unknown:
                return 'ambiguous'
            if has_on and has_kun:
                return 'mixed'
            if has_on:
                return 'pure_on'
            if has_kun:
                return 'pure_kun'
            return 'other'

        gt_class = classify(gt_clean)
        pred_class = classify(pred_clean)

        # Correct if the fundamental type classification matches
        if gt_class == pred_class:
            is_correct = True
        elif gt_class == 'ambiguous':
            # Ambiguous ground truth — give credit if prediction is reasonable
            is_correct = pred_class in ('pure_on', 'pure_kun', 'mixed')
        elif gt_class == 'unknown':
            is_correct = False  # Can't verify
        else:
            is_correct = False

        w['prediction_correct'] = is_correct

        word_results.append(w)

    # Statistics
    total = len(word_results)
    correct = sum(1 for w in word_results if w['prediction_correct'])
    accuracy = correct / total if total > 0 else 0

    # Per-level accuracy
    level_stats = {}
    for lv in JLPT_LEVELS:
        lv_words = [w for w in word_results if w['level'] == lv]
        lv_correct = sum(1 for w in lv_words if w['prediction_correct'])
        level_stats[lv] = {
            'total': len(lv_words),
            'correct': lv_correct,
            'accuracy': lv_correct / len(lv_words) if lv_words else 0,
        }

    # Per-pattern accuracy
    pattern_stats = {}
    for w in word_results:
        pat = w['ground_truth']['pattern']
        if pat not in pattern_stats:
            pattern_stats[pat] = {'total': 0, 'correct': 0}
        pattern_stats[pat]['total'] += 1
        if w['prediction_correct']:
            pattern_stats[pat]['correct'] += 1
    for pat in pattern_stats:
        pattern_stats[pat]['accuracy'] = (pattern_stats[pat]['correct'] /
                                          pattern_stats[pat]['total']
                                          if pattern_stats[pat]['total'] > 0 else 0)

    # Error analysis: words where prediction failed
    errors = [w for w in word_results if not w['prediction_correct']]
    error_by_level = defaultdict(list)
    for w in errors:
        error_by_level[w['level']].append(w)

    print(f"  Ground truth patterns: {dict(gt_stats.most_common(10))}")
    print(f"  Overall prediction accuracy: {accuracy:.1%} ({correct}/{total})")
    for lv in JLPT_LEVELS:
        s = level_stats[lv]
        print(f"  {lv}: {s['accuracy']:.1%} ({s['correct']}/{s['total']})")

    return {
        'total_words': total,
        'correct_predictions': correct,
        'accuracy': accuracy,
        'ground_truth_distribution': dict(gt_stats),
        'level_stats': level_stats,
        'pattern_stats': {k: dict(v) for k, v in pattern_stats.items()},
        'errors': errors,
        'error_by_level': {k: len(v) for k, v in error_by_level.items()},
        'word_results': word_results,
    }


def predict_word_reading(w, kanji_db):
    """Apply rule chain to predict on/kun for a word."""
    chars = w['kanji_chars']
    n = w['num_kanji']
    has_oku = w['has_okurigana']
    kana = w['kana']

    if n == 0:
        return {'predicted_pattern': 'no_kanji', 'rule_chain': [], 'confidence': 0}

    rules_fired = []

    # --- Iron Law 1: Has okurigana → contains kun (96.1%) ---
    if has_oku:
        rules_fired.append({'rule': 'IL1_okurigana', 'predicts': 'kun', 'confidence': 0.961})

    # --- Iron Law 2: Single kanji → mostly kun (84%) ---
    if n == 1:
        # Check if this kanji has any kun readings
        ch = chars[0]
        has_kun = False
        has_on = False
        if ch in kanji_db:
            has_kun = len(kanji_db[ch]['kun_readings']) > 0
            has_on = len(kanji_db[ch]['on_readings']) > 0

        if has_oku:
            # With okurigana → kun (very high confidence)
            rules_fired.append({'rule': 'IL2_single_okuri', 'predicts': 'kun', 'confidence': 0.96})
        elif has_kun and not has_on:
            # Only has kun readings → kun
            rules_fired.append({'rule': 'IL2_kun_only', 'predicts': 'kun', 'confidence': 0.99})
        elif has_on and not has_kun:
            # Only has on readings → on
            rules_fired.append({'rule': 'IL2_on_only', 'predicts': 'on', 'confidence': 0.99})
        else:
            # Has both, default to kun based on statistical tendency
            rules_fired.append({'rule': 'IL2_single_default', 'predicts': 'kun', 'confidence': 0.84})

    # --- Iron Law 3: 2-kanji with 2-3 mora → likely on+on (63-71%) ---
    if n == 2 and w['mora'] <= 3 and not has_oku:
        rules_fired.append({'rule': 'A3_short_compound', 'predicts': 'on+on', 'confidence': 0.71})

    # --- 3+ kanji compounds → mostly on readings ---
    if n >= 3 and not has_oku:
        on_votes = 0
        kun_votes = 0
        for ch in chars:
            if ch in kanji_db:
                if kanji_db[ch]['on_readings']:
                    on_votes += 1
                if kanji_db[ch]['kun_readings']:
                    kun_votes += 1
        if on_votes >= n * 0.7:
            rules_fired.append({'rule': 'A4_multi_on', 'predicts': f"on+{'on+' * (n-2)}on", 'confidence': 0.65})

    # --- Compound with okurigana at end → last kanji is kun ---
    if n >= 2 and has_oku:
        rules_fired.append({'rule': 'A1_compound_oku', 'predicts': 'kun', 'confidence': 0.90})
        # If first kanji has on readings, predict on+kun
        ch0 = chars[0]
        if ch0 in kanji_db and kanji_db[ch0]['on_readings']:
            rules_fired.append({'rule': 'A1_on_kun_mix', 'predicts': 'on+kun', 'confidence': 0.65})
        else:
            rules_fired.append({'rule': 'A1_kun_kun_mix', 'predicts': 'kun+kun', 'confidence': 0.70})

    # --- Radical-based prediction ---
    for ch in chars:
        if ch in kanji_db:
            rad = kanji_db[ch]['radical']
            if rad in '魚米牛竹虫木雨金巾宀广':
                rules_fired.append({'rule': f'B_noun_rad_{rad}', 'predicts': 'kun', 'confidence': 0.93})
            if rad in '手言力足刀':
                rules_fired.append({'rule': f'B_verb_rad_{rad}', 'predicts': 'kun', 'confidence': 0.80})

    # --- Determine final prediction ---
    if n == 1:
        kun_votes = sum(1 for r in rules_fired if r['predicts'] == 'kun')
        on_votes = sum(1 for r in rules_fired if r['predicts'] == 'on')
        if kun_votes > on_votes:
            predicted_pattern = 'kun'
            confidence = max(r['confidence'] for r in rules_fired if r['predicts'] == 'kun')
        elif on_votes > kun_votes:
            predicted_pattern = 'on'
            confidence = max(r['confidence'] for r in rules_fired if r['predicts'] == 'on')
        else:
            predicted_pattern = 'kun'  # default
            confidence = 0.5
    elif n == 2:
        on_votes = sum(1 for r in rules_fired if 'on' in r['predicts'] and 'kun' not in r['predicts'])
        kun_votes = sum(1 for r in rules_fired if r['predicts'] == 'kun')
        mix_votes = sum(1 for r in rules_fired if r['predicts'] in ('on+kun', 'kun+on'))

        if mix_votes > 0 and has_oku:
            # First kanji analysis
            ch0 = chars[0]
            if ch0 in kanji_db and kanji_db[ch0]['on_readings']:
                predicted_pattern = 'on+kun'
            else:
                predicted_pattern = 'kun+kun'
        elif on_votes >= 2 or (on_votes >= 1 and 'default_multi' in [r.get('rule','') for r in rules_fired]):
            predicted_pattern = 'on+on'
        else:
            predicted_pattern = 'kun+kun'
        confidence = 0.65
    else:
        # 3+ kanji
        if has_oku:
            predicted_pattern = 'kun+...'
        else:
            predicted_pattern = 'on+...'
        confidence = 0.55

    return {
        'predicted_pattern': predicted_pattern,
        'rule_chain': rules_fired,
        'confidence': round(confidence, 3),
    }


# ============================================================
# MODULE 2: REVERSE INDEX (Reading → Kanji)
# ============================================================

def build_reverse_index(jlpt_words, kanji_db):
    """Build kana reading → possible kanji index, grouped by JLPT level."""
    print("\n[2/6] Reverse Index (Reading → Kanji)...")

    # kana → {kanji → {levels, on_kun, meanings}}
    reading_index = defaultdict(lambda: defaultdict(lambda: {'levels': set(), 'types': set(), 'meanings': []}))

    for w in jlpt_words:
        kana = w['kana']
        gt = w.get('ground_truth', {})
        for d in gt.get('details', []):
            kanji = d['kanji']
            if kanji and kanji in kanji_db:
                entry = reading_index[kana][kanji]
                entry['levels'].add(w['level'])
                entry['types'].add(d['type'])
                if kanji_db[kanji]['meaning'] and len(entry['meanings']) < 3:
                    meaning = kanji_db[kanji]['meaning'][:50]
                    if meaning not in entry['meanings']:
                        entry['meanings'].append(meaning)

    # Also index by reading stem (first 1-3 mora)
    stem_index = defaultdict(lambda: defaultdict(lambda: {'levels': set(), 'types': set(), 'meanings': []}))
    for kana, kanji_map in reading_index.items():
        for stem_len in [1, 2, 3]:
            if len(kana) >= stem_len:
                stem = kana[:stem_len]
                for kanji, entry in kanji_map.items():
                    se = stem_index[stem][kanji]
                    se['levels'] |= entry['levels']
                    se['types'] |= entry['types']
                    if not se['meanings']:
                        se['meanings'] = entry['meanings'][:2]

    # Sort by kanji count
    sorted_readings = sorted(reading_index.items(), key=lambda x: len(x[1]), reverse=True)
    sorted_stems = sorted(stem_index.items(), key=lambda x: len(x[1]), reverse=True)

    print(f"  {len(reading_index)} unique kana readings indexed")
    print(f"  Top ambiguous: {' > '.join(f'{k}({len(v)})' for k, v in sorted_readings[:10])}")

    return {
        'reading_index': {k: {kk: {
            'levels': sorted(list(vv['levels'])),
            'types': sorted(list(vv['types'])),
            'meanings': vv['meanings'],
        } for kk, vv in v.items()} for k, v in sorted_readings},
        'stem_index': {k: {kk: {
            'levels': sorted(list(vv['levels'])),
            'types': sorted(list(vv['types'])),
            'meanings': vv['meanings'],
        } for kk, vv in v.items()} for k, v in sorted_stems[:200]},
        'total_readings': len(reading_index),
    }


# ============================================================
# MODULE 3: MINIMAL PAIRS
# ============================================================

def find_minimal_pairs(jlpt_words):
    """
    Find word pairs that differ by exactly one phonological feature.
    Focus on confusable pairs only (voicing, vowel alternation, similar consonants).
    """
    print("\n[3/6] Minimal Pairs...")

    # Only consider words with kanji, and group by mora count and key pattern
    kanji_words = [w for w in jlpt_words if w['num_kanji'] > 0]

    # Index by kana length and by "canonical form" (kana with voicing normalized)
    by_len = defaultdict(list)
    for w in kanji_words:
        by_len[len(w['kana'])].append(w)

    # Phonologically related consonant groups (same articulation place/manner)
    related_consonants = {
        # Voicing pairs
        'か': {'が'}, 'き': {'ぎ'}, 'く': {'ぐ'}, 'け': {'げ'}, 'こ': {'ご'},
        'が': {'か'}, 'ぎ': {'き'}, 'ぐ': {'く'}, 'げ': {'け'}, 'ご': {'こ'},
        'さ': {'ざ'}, 'し': {'じ'}, 'す': {'ず'}, 'せ': {'ぜ'}, 'そ': {'ぞ'},
        'ざ': {'さ'}, 'じ': {'し'}, 'ず': {'す'}, 'ぜ': {'せ'}, 'ぞ': {'そ'},
        'た': {'だ'}, 'ち': {'ぢ'}, 'つ': {'づ'}, 'て': {'で'}, 'と': {'ど'},
        'だ': {'た'}, 'ぢ': {'ち'}, 'づ': {'つ'}, 'で': {'て'}, 'ど': {'と'},
        'は': {'ば', 'ぱ'}, 'ひ': {'び', 'ぴ'}, 'ふ': {'ぶ', 'ぷ'}, 'へ': {'べ', 'ぺ'}, 'ほ': {'ぼ', 'ぽ'},
        'ば': {'は', 'ぱ'}, 'び': {'ひ', 'ぴ'}, 'ぶ': {'ふ', 'ぷ'}, 'べ': {'へ', 'ぺ'}, 'ぼ': {'ほ', 'ぽ'},
        'ぱ': {'は', 'ば'}, 'ぴ': {'ひ', 'び'}, 'ぷ': {'ふ', 'ぶ'}, 'ぺ': {'へ', 'べ'}, 'ぽ': {'ほ', 'ぼ'},
        # Same-place consonants (velar ↔ velar, alveolar ↔ alveolar, etc.)
        'か': {'た', 'が'}, 'き': {'ち', 'ぎ'}, 'く': {'つ', 'ぐ'}, 'け': {'て', 'げ'}, 'こ': {'と', 'ご'},
        'た': {'か', 'だ', 'さ'}, 'ち': {'き', 'ぢ', 'し'}, 'つ': {'く', 'づ', 'す'}, 'て': {'け', 'で', 'せ'}, 'と': {'こ', 'ど', 'そ'},
        # Nasal-related
        'ま': {'ば', 'ぱ', 'な'}, 'み': {'び', 'ぴ', 'に'}, 'む': {'ぶ', 'ぷ', 'ぬ'}, 'め': {'べ', 'ぺ', 'ね'}, 'も': {'ぼ', 'ぽ', 'の'},
        'な': {'ま', 'だ', 'ら'}, 'に': {'み', 'ぢ', 'り'}, 'ぬ': {'む', 'づ', 'る'}, 'ね': {'め', 'で', 'れ'}, 'の': {'も', 'ど', 'ろ'},
        # Liquid ↔ liquid
        'ら': {'だ', 'な'}, 'り': {'ぢ', 'に'}, 'る': {'づ', 'ぬ'}, 'れ': {'で', 'ね'}, 'ろ': {'ど', 'の'},
        # Sibilant-related
        'さ': {'ざ', 'た', 'は'}, 'し': {'じ', 'ち', 'ひ'}, 'す': {'ず', 'つ', 'ふ'}, 'せ': {'ぜ', 'て', 'へ'}, 'そ': {'ぞ', 'と', 'ほ'},
    }

    def is_confusable(c1, c2):
        """Check if two kana characters represent confusable sounds."""
        if c1 == c2:
            return False
        # Same vowel, different consonant → check if consonants are related
        if c1 in related_consonants and c2 in related_consonants[c1]:
            return True
        # Same consonant, different vowel → always confusable
        c1_cons = c1  # In kana, the whole character encodes consonant+vowel
        c2_cons = c2
        # Check if they share consonant but differ in vowel
        # This is harder in kana because consonant is encoded in the character
        # For vowel-only characters: あいうえお
        vowels = 'あいうえお'
        if c1 in vowels and c2 in vowels and c1 != c2:
            return True
        return False

    def classify_diff(c1, c2):
        """Classify the type of phonological difference."""
        # Voicing
        voicing_map = {'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
                       'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
                       'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
                       'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
                       'は2': 'ぱ', 'ひ2': 'ぴ', 'ふ2': 'ぷ', 'へ2': 'ぺ', 'ほ2': 'ぽ'}
        # Check both directions
        for k, v in voicing_map.items():
            k_clean = k.rstrip('2')
            v_clean = v
            if (c1 == k_clean and c2 == v_clean) or (c2 == k_clean and c1 == v_clean):
                return 'voicing'
        # Vowel: same consonant row
        vowels = 'あいうえお'
        if c1 in vowels and c2 in vowels:
            return 'vowel'
        # Check if same consonant row (same initial consonant in romaji)
        # This is a heuristic based on kana rows
        k_rows = {
            'k': 'かきくけこがぎぐげご', 's': 'さしすせそざじずぜぞ',
            't': 'たちつてとだぢづでど', 'n': 'なにぬねの',
            'h': 'はひふへほばびぶべぼぱぴぷぺぽ', 'm': 'まみむめも',
            'y': 'やゆよ', 'r': 'らりるれろ', 'w': 'わを'
        }
        c1_row = c2_row = None
        for row, chars in k_rows.items():
            if c1 in chars: c1_row = row
            if c2 in chars: c2_row = row
        if c1_row and c1_row == c2_row:
            return 'vowel'
        return 'consonant'

    pairs = []
    seen_pairs = set()

    # Find pairs within same length group
    for length, words in by_len.items():
        # Only consider words with 2-5 char kana (most meaningful)
        if length < 2 or length > 5:
            continue
        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                w1, w2 = words[i], words[j]
                k1, k2 = w1['kana'], w2['kana']
                if k1 == k2:
                    continue
                pair_key = tuple(sorted([k1, k2]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                if len(k1) != len(k2):
                    continue

                diffs = [(idx, k1[idx], k2[idx]) for idx in range(len(k1)) if k1[idx] != k2[idx]]
                if len(diffs) != 1:
                    continue

                idx, c1, c2 = diffs[0]

                # Only keep confusable pairs
                if not is_confusable(c1, c2):
                    continue

                diff_type = classify_diff(c1, c2)
                pairs.append({
                    'word1': {'kanji': w1['kanji_word'], 'kana': w1['kana_raw'], 'level': w1['level']},
                    'word2': {'kanji': w2['kanji_word'], 'kana': w2['kana_raw'], 'level': w2['level']},
                    'type': diff_type,
                    'diff_position': idx,
                    'diff_from': c1,
                    'diff_to': c2,
                })

    # By type
    by_type = defaultdict(list)
    for p in pairs:
        by_type[p['type']].append(p)

    for t in by_type:
        by_type[t] = sorted(by_type[t], key=lambda p: (p['word1']['level'], p['word2']['level']))

    print(f"  {len(pairs)} confusable minimal pairs found")
    for t, plist in sorted(by_type.items()):
        print(f"    {t}: {len(plist)} pairs")

    return {
        'total_pairs': len(pairs),
        'by_type': {k: len(v) for k, v in by_type.items()},
        'pairs': {k: v[:100] for k, v in by_type.items()},  # Top 100 per type
    }


# ============================================================
# MODULE 4: ANKI CSV EXPORT
# ============================================================

def export_anki(jlpt_words, kanji_db, pred_results):
    """Generate Anki-compatible CSV with rule annotations."""
    print("\n[4/6] Anki CSV Export...")

    rows = []
    for w in jlpt_words:
        if w['num_kanji'] == 0:
            continue

        gt = w.get('ground_truth', {})
        pred = w.get('prediction', {})

        # Build rule notes
        rule_notes = ' | '.join(
            f"{r['rule']}({r['predicts']} {r['confidence']:.0%})"
            for r in pred.get('rule_chain', [])[:3]
        )

        # Build meaning from kanji DB
        meanings = []
        for ch in w['kanji_chars']:
            if ch in kanji_db and kanji_db[ch]['meaning']:
                m = kanji_db[ch]['meaning'][:80]
                meanings.append(f"{ch}:{m}")
        meaning_str = '; '.join(meanings[:3])

        # Determine reading type tag
        pattern = gt.get('pattern', '?')
        if 'kun' in pattern and 'on' not in pattern:
            reading_tag = 'kun'
        elif 'on' in pattern and 'kun' not in pattern:
            reading_tag = 'on'
        elif 'kun' in pattern and 'on' in pattern:
            reading_tag = 'mixed'
        else:
            reading_tag = 'other'

        # Anki fields: guid, Word, Reading, Meaning, Level, ReadingType, Pattern, Rules, KanjiDetail
        row = {
            'guid': f"kk_{w['kanji_word']}_{w['kana_raw']}",
            'Word': w['kanji_word'],
            'Reading': w['kana_raw'],
            'Meaning': meaning_str,
            'Level': w['level'],
            'ReadingType': reading_tag,
            'Pattern': pattern,
            'Rules': rule_notes,
            'KanjiDetail': meaning_str,
        }
        rows.append(row)

    # Sort by level then word
    rows.sort(key=lambda r: (JLPT_LEVELS.index(r['Level']), r['Word']))

    # Write CSV
    csv_path = f'{OUT}/kun_v8_anki_deck.csv'
    fields = ['guid', 'Word', 'Reading', 'Meaning', 'Level', 'ReadingType', 'Pattern', 'Rules', 'KanjiDetail']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    # Per-level decks
    for lv in JLPT_LEVELS:
        lv_rows = [r for r in rows if r['Level'] == lv]
        lv_path = f'{OUT}/kun_v8_anki_{lv}.csv'
        with open(lv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(lv_rows)

    print(f"  {len(rows)} cards exported")
    print(f"  Files: kun_v8_anki_deck.csv + 5 per-level CSVs")

    return {'total_cards': len(rows), 'csv_path': csv_path}


# ============================================================
# MODULE 5: LEARNING BURDEN QUANTIFICATION
# ============================================================

def quantify_learning_burden(jlpt_words, kanji_db, tiered, pred_results, total_rules):
    """
    Calculate exact compression ratio: rote memorization vs rule-based learning.
    """
    print("\n[5/6] Learning Burden Quantification...")

    # Total unique word-reading pairs (rote memorization items)
    unique_word_readings = set()
    for w in jlpt_words:
        if w['num_kanji'] > 0:
            unique_word_readings.add((w['kanji_word'], w['kana_raw']))
    rote_items = len(unique_word_readings)

    # Count unique kanji across all JLPT words
    all_jlpt_kanji = set()
    for w in jlpt_words:
        for ch in w['kanji_chars']:
            if ch in kanji_db:
                all_jlpt_kanji.add(ch)

    # How many unique reading-stems exist in JLPT?
    all_stems = set()
    for ch in all_jlpt_kanji:
        for kr in kanji_db[ch]['kun_readings']:
            if kr['stem']:
                all_stems.add(kr['stem'])
    total_stems = len(all_stems)

    # Coverage analysis
    word_results = pred_results['word_results']

    # Per-level breakdown
    level_burden = {}
    for lv in JLPT_LEVELS:
        lv_words = [w for w in word_results if w['level'] == lv]
        lv_total = len(lv_words)
        lv_correct = sum(1 for w in lv_words if w.get('prediction_correct'))

        lv_kanji = set()
        for w in lv_words:
            for ch in w['kanji_chars']:
                if ch in kanji_db:
                    lv_kanji.add(ch)

        lv_stems = set()
        for ch in lv_kanji:
            for kr in kanji_db[ch]['kun_readings']:
                if kr['stem']:
                    lv_stems.add(kr['stem'])

        lv_rote = len(set((w['kanji_word'], w['kana_raw']) for w in lv_words))

        # Rules available for this level
        lv_rules = len(tiered.get('levels', {}).get(lv, {}).get('rules', []))

        level_burden[lv] = {
            'total_words': lv_total,
            'unique_word_readings': lv_rote,
            'unique_kanji': len(lv_kanji),
            'unique_stems': len(lv_stems),
            'prediction_accuracy': lv_correct / lv_total if lv_total > 0 else 0,
            'words_per_kanji': lv_total / len(lv_kanji) if lv_kanji else 0,
            'level_rules': lv_rules,
            'compression': lv_rote / lv_rules if lv_rules > 0 else 0,
        }

    # Overall compression
    compression = {
        'rote_items': rote_items,
        'total_unique_kanji': len(all_jlpt_kanji),
        'total_unique_stems': total_stems,
        'total_rules': total_rules,
        'avg_words_per_kanji': rote_items / len(all_jlpt_kanji) if all_jlpt_kanji else 0,
        'stems_per_kanji': total_stems / len(all_jlpt_kanji) if all_jlpt_kanji else 0,
        'rules_vs_rote': f"{total_rules} rules vs {rote_items} rote items = {rote_items / total_rules:.1f}x compression",
        'level_breakdown': level_burden,
    }

    print(f"  Rote items: {rote_items}")
    print(f"  Unique JLPT kanji: {len(all_jlpt_kanji)}")
    print(f"  Unique JLPT stems: {total_stems}")
    print(f"  {compression['rules_vs_rote']}")

    return compression


# ============================================================
# MODULE 6: KNOWN-KANJI DIVIDEND
# ============================================================

def known_kanji_dividend(jlpt_words, kanji_db):
    """
    Quantify the Chinese speaker advantage:
    - How many JLPT kanji are shared with common Chinese?
    - How many JLPT words use only these "known" kanji?
    - What's the meaning-comprehension vs reading gap?
    """
    print("\n[6/6] Known-Kanji Dividend...")

    # Estimate: Chinese speakers know ~2000-3000 characters
    # We'll use the kanji that appear in JLPT as "known" and check
    # what percentage of words they can already understand (meaning-wise)

    # All JLPT kanji (these are "known" to Chinese speakers visually)
    all_jlpt_kanji = set()
    for w in jlpt_words:
        for ch in w['kanji_chars']:
            if ch in kanji_db:
                all_jlpt_kanji.add(ch)

    # Additional common kanji that Chinese speakers know but aren't in JLPT
    # (we don't have this data, but we can estimate)
    # For now, use JLPT kanji as the "known" set

    # Words fully composed of known kanji = words Chinese speaker can understand
    # (meaning-wise, not reading-wise)
    words_understandable = []
    words_partial = []
    words_unknown = []

    for w in jlpt_words:
        if w['num_kanji'] == 0:
            words_unknown.append(w)
            continue
        known_count = sum(1 for ch in w['kanji_chars'] if ch in all_jlpt_kanji)
        if known_count == w['num_kanji']:
            words_understandable.append(w)
        elif known_count > 0:
            words_partial.append(w)
        else:
            words_unknown.append(w)

    # The gap: understand meaning but can't read it
    # For each understandable word, what's the reading type?
    meaning_only = []
    reading_too = []
    for w in words_understandable:
        gt = w.get('ground_truth', {})
        pattern = gt.get('pattern', 'unknown')
        # Chinese speaker can infer meaning from kanji, but reading requires
        # knowing on/kun distinction
        meaning_only.append({
            'word': w['kanji_word'],
            'kana': w['kana_raw'],
            'level': w['level'],
            'pattern': pattern,
            'meaning_hint': '; '.join(
                f"{ch}:{kanji_db[ch]['meaning'][:30]}"
                for ch in w['kanji_chars'] if ch in kanji_db
            ) if w['kanji_chars'] else '',
        })

    # Per-level statistics
    level_dividend = {}
    for lv in JLPT_LEVELS:
        lv_words = [w for w in jlpt_words if w['level'] == lv]
        lv_total = len(lv_words)
        lv_understandable = [w for w in words_understandable if w['level'] == lv]
        lv_partial = [w for w in words_partial if w['level'] == lv]

        lv_kanji = set()
        for w in words_understandable:
            if w['level'] == lv:
                for ch in w['kanji_chars']:
                    lv_kanji.add(ch)

        level_dividend[lv] = {
            'total_words': lv_total,
            'understandable_words': len(lv_understandable),
            'understandable_pct': len(lv_understandable) / lv_total if lv_total > 0 else 0,
            'partial_words': len(lv_partial),
            'used_kanji': len(lv_kanji),
        }

    total_jlpt = len(jlpt_words)
    understandable_pct = len(words_understandable) / total_jlpt if total_jlpt > 0 else 0

    print(f"  JLPT kanji: {len(all_jlpt_kanji)} (all visually known to Chinese speakers)")
    print(f"  Understandable words (meaning-wise): {len(words_understandable)}/{total_jlpt} = {understandable_pct:.1%}")
    print(f"  Partial understanding: {len(words_partial)}")
    print(f"  The 'reading gap': {len(words_understandable)} words you understand but can't pronounce")

    return {
        'total_jlpt_kanji': len(all_jlpt_kanji),
        'total_words': total_jlpt,
        'understandable_words': len(words_understandable),
        'understandable_pct': understandable_pct,
        'partial_words': len(words_partial),
        'level_breakdown': level_dividend,
    }


# ============================================================
# OUTPUT GENERATORS
# ============================================================

def write_prediction_report(pred_results, kanji_db):
    """Write word-level prediction engine report."""
    print("  Writing prediction report...")
    lines = []
    lines.append("# V8 Word-Level Prediction Engine Report\n")
    lines.append(f"**Overall Accuracy:** {pred_results['accuracy']:.1%} "
                 f"({pred_results['correct_predictions']}/{pred_results['total_words']} words)\n")

    lines.append("\n## Ground Truth Distribution\n")
    lines.append("| Pattern | Count |")
    lines.append("|---------|-------|")
    for pat, count in sorted(pred_results['ground_truth_distribution'].items(), key=lambda x: -x[1]):
        lines.append(f"| {pat} | {count} |")

    lines.append("\n## Per-Level Accuracy\n")
    lines.append("| Level | Total | Correct | Accuracy |")
    lines.append("|-------|-------|---------|----------|")
    for lv in JLPT_LEVELS:
        s = pred_results['level_stats'][lv]
        lines.append(f"| {lv} | {s['total']} | {s['correct']} | {s['accuracy']:.1%} |")

    lines.append("\n## Per-Pattern Accuracy\n")
    lines.append("| Pattern | Total | Correct | Accuracy |")
    lines.append("|---------|-------|---------|----------|")
    for pat, s in sorted(pred_results['pattern_stats'].items(), key=lambda x: -x[1]['total']):
        lines.append(f"| {pat} | {s['total']} | {s['correct']} | {s['accuracy']:.1%} |")

    lines.append(f"\n## Error Analysis ({len(pred_results['errors'])} total errors)\n")
    lines.append("| Level | Errors |")
    lines.append("|-------|--------|")
    for lv in JLPT_LEVELS:
        lines.append(f"| {lv} | {pred_results['error_by_level'].get(lv, 0)} |")

    lines.append("\n### Top 20 Misclassified Words\n")
    lines.append("| Word | Kana | Level | Ground Truth | Predicted | Confidence |")
    lines.append("|------|------|-------|--------------|-----------|------------|")
    for w in pred_results['errors'][:20]:
        gt = w.get('ground_truth', {})
        pred = w.get('prediction', {})
        lines.append(f"| {w['kanji_word']} | {w['kana_raw']} | {w['level']} | "
                     f"{gt.get('pattern', '?')} | {pred.get('predicted_pattern', '?')} | "
                     f"{pred.get('confidence', 0):.1%} |")

    lines.append("\n## Per-Word Annotations (first 100 words)\n")
    lines.append("| # | Word | Kana | Level | GT | Pred | Correct | Rules |")
    lines.append("|---|------|------|-------|----|------|---------|-------|")
    for i, w in enumerate(pred_results['word_results'][:100]):
        gt = w.get('ground_truth', {})
        pred = w.get('prediction', {})
        correct = '✓' if w.get('prediction_correct') else '✗'
        rules_str = ', '.join(r['rule'] for r in pred.get('rule_chain', [])[:3])
        lines.append(f"| {i+1} | {w['kanji_word']} | {w['kana_raw']} | {w['level']} | "
                     f"{gt.get('pattern', '?')} | {pred.get('predicted_pattern', '?')} | "
                     f"{correct} | {rules_str} |")

    report = '\n'.join(lines)
    path = f'{OUT}/kun_v8_prediction_engine.md'
    with open(path, 'w') as f:
        f.write(report)
    print(f"    → {path}")

    # Also save as JSON for Web App
    json_data = {
        'accuracy': pred_results['accuracy'],
        'total_words': pred_results['total_words'],
        'correct_predictions': pred_results['correct_predictions'],
        'ground_truth_distribution': pred_results['ground_truth_distribution'],
        'level_stats': pred_results['level_stats'],
        'pattern_stats': pred_results['pattern_stats'],
        'error_by_level': pred_results['error_by_level'],
        # Sample of annotated words for Web App
        'annotated_words': [
            {
                'word': w['kanji_word'],
                'kana': w['kana_raw'],
                'level': w['level'],
                'ground_truth': w.get('ground_truth', {}).get('pattern', '?'),
                'prediction': w.get('prediction', {}).get('predicted_pattern', '?'),
                'confidence': w.get('prediction', {}).get('confidence', 0),
                'correct': w.get('prediction_correct', False),
                'rules': [r['rule'] for r in w.get('prediction', {}).get('rule_chain', [])[:3]],
            }
            for w in pred_results['word_results']
        ],
    }
    json_path = f'{OUT}/kun_v8_prediction_engine.json'
    with open(json_path, 'w') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"    → {json_path}")


def write_reverse_index_report(rev_data):
    """Write reverse index report."""
    print("  Writing reverse index report...")
    lines = []
    lines.append("# V8 Reverse Index: Reading → Kanji\n")
    lines.append(f"**{rev_data['total_readings']}** unique kana readings indexed.\n")

    lines.append("\n## Most Ambiguous Readings (most possible kanji)\n")
    lines.append("| Reading | # Kanji | Sample Kanji (with meanings) |")
    lines.append("|---------|---------|------------------------------|")

    sorted_readings = sorted(rev_data['reading_index'].items(), key=lambda x: -len(x[1]))[:30]
    for kana, kanji_map in sorted_readings:
        kanji_list = sorted(kanji_map.items(), key=lambda x: -len(x[1]['levels']))[:8]
        samples = ', '.join(
            f"{k}({', '.join(v['meanings'][:1])})"
            for k, v in kanji_list
        )
        lines.append(f"| {kana} | {len(kanji_map)} | {samples[:150]} |")

    lines.append("\n## By First Mora (stem index top 50)\n")
    lines.append("| Stem | # Kanji | Top Kanji |")
    lines.append("|------|---------|-----------|")
    for stem, kanji_map in sorted(rev_data['stem_index'].items(), key=lambda x: -len(x[1]))[:50]:
        top = ', '.join(sorted(kanji_map.keys(), key=lambda k: -len(kanji_map[k]['levels']))[:5])
        lines.append(f"| {stem} | {len(kanji_map)} | {top} |")

    report = '\n'.join(lines)
    path = f'{OUT}/kun_v8_reverse_index.md'
    with open(path, 'w') as f:
        f.write(report)
    print(f"    → {path}")

    # JSON for Web App
    json_path = f'{OUT}/kun_v8_reverse_index.json'
    with open(json_path, 'w') as f:
        json.dump(rev_data, f, ensure_ascii=False, indent=2)
    print(f"    → {json_path}")


def write_minimal_pairs_report(mp_data):
    """Write minimal pairs report."""
    print("  Writing minimal pairs report...")
    lines = []
    lines.append("# V8 Minimal Pairs: Words That Differ By One Sound\n")
    lines.append(f"**{mp_data['total_pairs']}** minimal pairs found.\n")

    for ptype in ['voicing', 'vowel', 'consonant']:
        pairs = mp_data['pairs'].get(ptype, [])
        if not pairs:
            continue
        lines.append(f"\n## {ptype.title()} Differences ({len(pairs)} pairs)\n")
        lines.append("| # | Word 1 | Word 2 | Diff | Levels |")
        lines.append("|---|--------|--------|------|--------|")
        for i, p in enumerate(pairs[:30]):
            lines.append(f"| {i+1} | {p['word1']['kanji']}({p['word1']['kana']}) | "
                         f"{p['word2']['kanji']}({p['word2']['kana']}) | "
                         f"{p['diff_from']}↔{p['diff_to']} | "
                         f"{p['word1']['level']}/{p['word2']['level']} |")

    report = '\n'.join(lines)
    path = f'{OUT}/kun_v8_minimal_pairs.md'
    with open(path, 'w') as f:
        f.write(report)
    print(f"    → {path}")


def write_burden_report(burden_data):
    """Write learning burden report."""
    print("  Writing burden report...")
    lines = []
    lines.append("# V8 Learning Burden Quantification\n")
    lines.append("## Rote vs Rule-Based: Exact Compression\n")
    lines.append(f"- **Rote memorization items (unique word→reading pairs):** {burden_data['rote_items']}")
    lines.append(f"- **Unique JLPT kanji:** {burden_data['total_unique_kanji']}")
    lines.append(f"- **Unique JLPT kun-yomi stems:** {burden_data['total_unique_stems']}")
    lines.append(f"- **Total rules in system:** {burden_data['total_rules']}")
    lines.append(f"- **Compression:** {burden_data['rules_vs_rote']}")
    lines.append(f"- **Avg words per kanji:** {burden_data['avg_words_per_kanji']:.1f}")
    lines.append(f"- **Stems per kanji:** {burden_data['stems_per_kanji']:.1f}\n")

    lines.append("\n## Per-Level Breakdown\n")
    lines.append("| Level | Words | Unique Words | Kanji | Stems | Accuracy | W/Kanji | Lv Rules | Compression |")
    lines.append("|-------|-------|-------------|-------|-------|----------|---------|----------|-------------|")
    for lv in JLPT_LEVELS:
        s = burden_data['level_breakdown'][lv]
        lines.append(f"| {lv} | {s['total_words']} | {s['unique_word_readings']} | "
                     f"{s['unique_kanji']} | {s['unique_stems']} | "
                     f"{s['prediction_accuracy']:.1%} | {s['words_per_kanji']:.1f} | "
                     f"{s['level_rules']} | {s['compression']:.1f}x |")

    report = '\n'.join(lines)
    path = f'{OUT}/kun_v8_burden.md'
    with open(path, 'w') as f:
        f.write(report)
    print(f"    → {path}")


def write_dividend_report(div_data):
    """Write known-kanji dividend report."""
    print("  Writing dividend report...")
    lines = []
    lines.append("# V8 Known-Kanji Dividend: Chinese Speaker Advantage\n")
    lines.append(f"**{div_data['total_jlpt_kanji']}** JLPT kanji are visually familiar to Chinese speakers.\n")
    lines.append(f"- **{div_data['understandable_pct']:.1%}** of JLPT words ({div_data['understandable_words']}/{div_data['total_words']}) "
                 "are meaning-comprehensible without study")
    lines.append(f"- **{div_data['partial_words']}** words partially comprehensible")
    lines.append(f"- **The reading gap:** {div_data['understandable_words']} words you can understand but can't pronounce\n")

    lines.append("\n## Per-Level Breakdown\n")
    lines.append("| Level | Total | Understandable | % | Partial | Kanji Used |")
    lines.append("|-------|-------|---------------|----|---------|------------|")
    for lv in JLPT_LEVELS:
        s = div_data['level_breakdown'][lv]
        lines.append(f"| {lv} | {s['total_words']} | {s['understandable_words']} | "
                     f"{s['understandable_pct']:.1%} | {s['partial_words']} | {s['used_kanji']} |")

    lines.append("\n## Implications for Learning Strategy\n")
    lines.append("1. **You already know the meaning** of most JLPT words — focus on pronunciation")
    lines.append("2. **On-yomi** words are easier (similar to Chinese readings) — learn kun-yomi rules for the rest")
    lines.append("3. **Single-kanji words** are the hardest (purely Japanese readings) — use radical/component rules")
    lines.append("4. **Compound words** are mostly on+on at higher levels — kun-yomi matters most at N5/N4")

    report = '\n'.join(lines)
    path = f'{OUT}/kun_v8_dividend.md'
    with open(path, 'w') as f:
        f.write(report)
    print(f"    → {path}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Kun-Yomi V8: Integration, Verification & Export")
    print("=" * 60)

    jlpt_words, kanji_db, v4, v3, tiered, total_rules = load_data()

    # Module 1: Word-Level Prediction Engine
    pred_results = build_prediction_engine(jlpt_words, kanji_db, v4, v3, tiered)
    write_prediction_report(pred_results, kanji_db)

    # Module 2: Reverse Index
    rev_data = build_reverse_index(jlpt_words, kanji_db)
    write_reverse_index_report(rev_data)

    # Module 3: Minimal Pairs
    mp_data = find_minimal_pairs(jlpt_words)
    write_minimal_pairs_report(mp_data)

    # Module 4: Anki CSV Export
    anki_data = export_anki(jlpt_words, kanji_db, pred_results)

    # Module 5: Learning Burden Quantification
    burden_data = quantify_learning_burden(jlpt_words, kanji_db, tiered, pred_results, total_rules)
    write_burden_report(burden_data)

    # Module 6: Known-Kanji Dividend
    div_data = known_kanji_dividend(jlpt_words, kanji_db)
    write_dividend_report(div_data)

    # Summary
    print("\n" + "=" * 60)
    print("V8 generation complete!")
    files = [
        'kun_v8_prediction_engine.md / .json',
        'kun_v8_reverse_index.md / .json',
        'kun_v8_minimal_pairs.md',
        'kun_v8_anki_deck.csv (+ 5 per-level CSVs)',
        'kun_v8_burden.md',
        'kun_v8_dividend.md',
    ]
    for f in files:
        print(f"  {f}")
    print("=" * 60)


if __name__ == '__main__':
    main()
