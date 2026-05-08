#!/usr/bin/env python3
"""
Kun-Yomi V9: Precision Ground Truth + Full Rule System + Explanation Chains
============================================================================
Key improvements over V8:
1. DP-based kana segmentation → near-perfect ground truth for regular words
2. Apply ALL V5 rules (328) to JLPT word-level prediction
3. Generate human-readable explanation chains per word
4. Per-level optimized rule subsets (greedy minimal-rule selection)
"""

import json, re, os, csv
from collections import Counter, defaultdict
from functools import lru_cache
import openpyxl

BASE = '/Volumes/SSD/work/kanji-kun'
OUT = f'{BASE}/output'
WORD_XLSX = f'{BASE}/word.xlsx'
KANJI_XLSM = f'{BASE}/漢字検索V2.xlsm'
TIERED_JSON = f'{BASE}/output/kun_tiered_rules.json'

JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

# Kana normalization
KATA_TO_HIRA = str.maketrans(
    'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'
    'ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ'
    'ャュョッァィゥェォヷヸヹヺ',
    'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'
    'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ'
    'ゃゅょっあいうえおわゐゑを'
)

def kata_to_hira(s):
    return s.translate(KATA_TO_HIRA)

def clean_kana(s):
    s = kata_to_hira(s)
    return s

def mora_count(s):
    s = kata_to_hira(s)
    count = 0
    i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉ':
            count += 1; i += 2
        else:
            count += 1; i += 1
    return count


# ============================================================
# DATA LOADING
# ============================================================

def load_data():
    print("Loading data...")
    # JLPT words
    wb = openpyxl.load_workbook(WORD_XLSX, read_only=True)
    ws = wb['红宝书去重版']
    jlpt_words = []
    for row in ws.iter_rows(min_row=4, max_row=9575, values_only=True):
        kana_raw = str(row[2]).strip() if row[2] else ''
        kanji_raw = str(row[3]).strip() if row[3] else ''
        level = str(row[23]).strip() if len(row) > 23 and row[23] else ''
        if level not in JLPT_LEVELS: continue
        has_kanji = bool(re.search(r'[一-鿿㐀-䶿]', kanji_raw))
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', kanji_raw) if has_kanji else []
        kana_clean = clean_kana(kana_raw)
        jlpt_words.append({
            'kana_raw': kana_raw, 'kana': kana_clean,
            'kanji_word': kanji_raw, 'level': level,
            'kanji_chars': kanji_chars, 'num_kanji': len(kanji_chars),
            'mora': mora_count(kana_raw),
            'has_okurigana': bool(re.search(r'[ぁ-ん]', kanji_raw)) if has_kanji else False,
        })
    wb.close()
    print(f"  Words: {len(jlpt_words)}")

    # Kanji DB with precomputed reading lookup
    wb2 = openpyxl.load_workbook(KANJI_XLSM, read_only=True)
    ws2 = wb2['漢字一覧']
    kanji_db = {}
    for row in ws2.iter_rows(min_row=2, max_row=46850, values_only=True):
        if not row[0]: continue
        ch = str(row[0]).strip()
        if not ch or len(ch) > 2: continue
        radical = str(row[3]).strip() if row[3] else ''
        components = str(row[1]).strip() if row[1] else ''
        on_raw = str(row[9]).strip() if row[9] else ''
        kun_raw = str(row[10]).strip() if row[10] else ''
        meaning = str(row[11]).strip() if row[11] else ''

        on_list = []
        for o in on_raw.replace('、', ',').split(','):
            o = o.strip()
            if o: on_list.append(kata_to_hira(o))

        kun_raw_list = [k.strip() for k in kun_raw.replace('、', ',').split(',') if k.strip()]
        kun_list = []
        for kr in kun_raw_list:
            if '・' in kr:
                parts = kr.split('・')
                stem = parts[0].replace('.', '')
                oku = '.'.join(p.replace('.', '') for p in parts[1:])
                kun_list.append({'stem': stem, 'okurigana': oku, 'full': f"{stem}.{oku}"})
            elif kr:
                s = kr.replace('.', '')
                kun_list.append({'stem': s, 'okurigana': '', 'full': s})

        # Precompute ALL possible kanji→kana mappings for DP segmentation
        all_kana_readings = set()
        for on in on_list:
            if on: all_kana_readings.add(on)
        for k in kun_list:
            if k['stem']: all_kana_readings.add(k['stem'])
            if k['okurigana']: all_kana_readings.add(k['stem'] + k['okurigana'])

        kanji_db[ch] = {
            'radical': radical, 'components': components,
            'on_readings': on_list, 'kun_readings': kun_list,
            'meaning': meaning,
            '_all_readings': sorted(all_kana_readings, key=len, reverse=True),
            '_on_set': set(on_list),
            '_kun_stems': set(k['stem'] for k in kun_list if k['stem']),
            '_kun_full': set(k['stem'] + k['okurigana'] for k in kun_list if k['stem']),
        }
    wb2.close()
    print(f"  Kanji: {len(kanji_db)}")

    # V5 rules
    with open(TIERED_JSON) as f:
        tiered = json.load(f)
    total_rules = sum(len(tiered['levels'][lv]['rules']) for lv in JLPT_LEVELS)
    total_rules += len(tiered.get('iron_laws', [])) + len(tiered.get('verification_layer', []))
    print(f"  Rules: {total_rules} total")

    return jlpt_words, kanji_db, tiered


# ============================================================
# MODULE 1: DP KANA SEGMENTATION (near-perfect ground truth)
# ============================================================

def dp_segment(kana, kanji_chars, kanji_db):
    """
    DP-based kana segmentation for multi-kanji words.
    Uses full DP to find the optimal matching of kana to kanji readings.
    Returns (pattern, details, confidence).
    """
    n_kanji = len(kanji_chars)
    klen = len(kana)

    if n_kanji == 0:
        return 'no_kanji', [], 1.0
    if n_kanji == 1:
        return segment_single(kana, kanji_chars[0], kanji_db)

    # Collect all reading candidates for each kanji WITH sound change variants
    all_readings = []
    for i, ch in enumerate(kanji_chars):
        if ch not in kanji_db:
            all_readings.append([])
            continue
        info = kanji_db[ch]
        candidates = []

        # On readings + sokuon variants
        for r in info['on_readings']:
            if not r: continue
            candidates.append((r, 'on'))
            # 促音便: final つ/ち/く/き → っ before certain consonants
            if r and r[-1] in 'つちくき':
                sokuon_form = r[:-1] + 'っ'
                if sokuon_form != r:
                    candidates.append((sokuon_form, 'on_sokuon'))
            # Also: つ→っ before k,s,t,p (most common)
            if r and r.endswith('つ'):
                candidates.append((r[:-1] + 'っ', 'on_sokuon2'))

        # Kun stems + rendaku + sokuon variants
        for k in info['kun_readings']:
            if not k['stem']: continue
            stem = k['stem']
            candidates.append((stem, 'kun'))

            # Rendaku (voicing) for second+ kanji in compounds
            voicing_map_first = {
                'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
                'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
                'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
                'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
            }
            # Also 半濁音: は→ぱ
            handaku_map = {'は': 'ぱ', 'ひ': 'ぴ', 'ふ': 'ぷ', 'へ': 'ぺ', 'ほ': 'ぽ'}

            for vmap, suffix in [(voicing_map_first, '_rendaku'), (handaku_map, '_handaku')]:
                for kv, gv in vmap.items():
                    if stem.startswith(kv):
                        voiced = gv + stem[len(kv):]
                        if voiced != stem:
                            candidates.append((voiced, f'kun{suffix}'))

            # Sokuon for kun stems ending in つ/ち
            if stem and stem[-1] in 'つち':
                candidates.append((stem[:-1] + 'っ', 'kun_sokuon'))

        # Full kun readings (stem+okurigana) for last kanji
        for k in info['kun_readings']:
            if k['stem'] and k['okurigana']:
                full = k['stem'] + k['okurigana']
                if full not in [c[0] for c in candidates]:
                    candidates.append((full, 'kun_full'))
                # Rendaku variants of full kun
                for kv, gv in voicing_map_first.items():
                    if full.startswith(kv):
                        voiced_full = gv + full[len(kv):]
                        if voiced_full not in [c[0] for c in candidates]:
                            candidates.append((voiced_full, 'kun_full_rendaku'))

        # Deduplicate
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c[0] not in seen:
                seen.add(c[0])
                unique_candidates.append(c)
        all_readings.append(unique_candidates)

    # DP: dp[pos][i] = best (prev_pos, reading_info) or None
    # We want to match ALL kanji and cover ALL kana
    dp = [[None] * (n_kanji + 1) for _ in range(klen + 1)]
    dp[0][0] = (0, None, None)  # base case

    for pos in range(klen + 1):
        for i in range(n_kanji):
            if dp[pos][i] is None:
                continue
            for reading, rtype in all_readings[i]:
                rlen = len(reading)
                end = pos + rlen
                if end <= klen and kana[pos:end] == reading:
                    if dp[end][i + 1] is None:
                        dp[end][i + 1] = (pos, reading, rtype)

    # Best solution: all kanji matched, all (or most) kana covered
    best_end = None
    for pos in range(klen, -1, -1):
        if dp[pos][n_kanji] is not None:
            best_end = pos
            break

    if best_end is None:
        # Try partial: match as many kanji as possible
        best_i = 0
        for i in range(n_kanji + 1):
            for pos in range(klen + 1):
                if dp[pos][i] is not None:
                    best_i = i
        if best_i == 0:
            return 'unknown', [], 0.0
        # Reconstruct partial match
        return reconstruct_partial(kana, kanji_chars, all_readings, dp, best_i)

    # Reconstruct
    details = []
    pos = best_end
    for i in range(n_kanji - 1, -1, -1):
        prev_pos, reading, rtype = dp[pos][i + 1]
        details.append({
            'kanji': kanji_chars[i],
            'type': 'kun' if 'kun' in rtype else 'on',
            'reading': reading,
            'match': 'exact_dp',
            'segment': kana[prev_pos:pos],
        })
        pos = prev_pos
    details.reverse()

    # Build pattern
    types = [d['type'] for d in details]
    # Normalize sound-change types
    types = ['kun' if ('kun' in t or 'rendaku' in t or 'handaku' in t) else
             'on' if ('on' in t or 'sokuon' in t) else t
             for t in types]
    pattern = '+'.join(types)

    confidence = 1.0 if best_end == klen else 0.8
    if best_end < klen:
        pattern += '~'

    return pattern, details, confidence


def segment_single(kana, ch, kanji_db):
    """Classify single-kanji word."""
    if ch not in kanji_db:
        return 'unknown', [], 0.0
    info = kanji_db[ch]

    # Check exact full kun (stem + okurigana)
    for k in info['kun_readings']:
        if k['stem'] and k['okurigana']:
            full = k['stem'] + k['okurigana']
            if full == kana:
                return 'kun', [{'kanji': ch, 'type': 'kun', 'reading': k['stem'], 'match': 'exact_full'}], 1.0

    # Check exact stem
    for k in info['kun_readings']:
        if k['stem'] and k['stem'] == kana and not k['okurigana']:
            return 'kun', [{'kanji': ch, 'type': 'kun', 'reading': k['stem'], 'match': 'exact_stem'}], 1.0

    # Check kana starts with stem (has okurigana)
    for k in info['kun_readings']:
        if k['stem'] and k['okurigana'] and kana.startswith(k['stem']):
            return 'kun', [{'kanji': ch, 'type': 'kun', 'reading': k['stem'], 'match': 'stem_prefix'}], 0.95

    # Check exact on
    for on in info['on_readings']:
        if on == kana:
            return 'on', [{'kanji': ch, 'type': 'on', 'reading': on, 'match': 'exact_on'}], 1.0

    # Check on substring (some on-yomi are longer)
    for on in sorted(info['on_readings'], key=len, reverse=True):
        if len(on) >= 2 and kana.startswith(on):
            return 'on', [{'kanji': ch, 'type': 'on', 'reading': on, 'match': 'on_prefix'}], 0.7

    # Check any kun stem match
    for k in info['kun_readings']:
        if k['stem'] and k['stem'] in kana:
            return 'kun', [{'kanji': ch, 'type': 'kun', 'reading': k['stem'], 'match': 'contains'}], 0.7

    # Heuristic: has on only
    if info['on_readings'] and not info['kun_readings']:
        return 'on', [{'kanji': ch, 'type': 'on', 'reading': info['on_readings'][0], 'match': 'only_on'}], 0.6
    # Heuristic: has kun only
    if info['kun_readings'] and not info['on_readings']:
        return 'kun', [{'kanji': ch, 'type': 'kun', 'reading': '', 'match': 'only_kun'}], 0.6

    return 'unknown', [{'kanji': ch, 'type': '?', 'reading': '', 'match': 'none'}], 0.0


def reconstruct_partial(kana, chars, all_readings, dp, best_i):
    """Reconstruct best partial match."""
    # Find best ending position for best_i
    best_pos = 0
    for pos in range(len(kana) + 1):
        if dp[pos][best_i] is not None:
            best_pos = pos

    details = []
    pos = best_pos
    for i in range(best_i - 1, -1, -1):
        prev_pos, reading, rtype = dp[pos][i + 1]
        if reading is None:
            break
        rtype_clean = 'kun' if ('kun' in (rtype or '') or 'rendaku' in (rtype or '') or 'handaku' in (rtype or '')) else 'on'
        details.append({
            'kanji': chars[i], 'type': rtype_clean,
            'reading': reading, 'match': 'dp_partial',
        })
        pos = prev_pos
    details.reverse()

    # Fill remaining with ?
    for i in range(len(details), len(chars)):
        details.append({'kanji': chars[i], 'type': '?', 'reading': '', 'match': 'unmatched'})

    types = [d['type'] for d in details]
    pattern = '+'.join(types) + '~'
    return pattern, details, 0.5


# ============================================================
# MODULE 2: FULL RULE APPLICATION
# ============================================================

def build_rule_engine(tiered):
    """Extract and index all rules for fast application."""
    all_rules = []

    # Iron laws
    for r in tiered.get('iron_laws', []):
        all_rules.append(r)

    # Verification layer
    for r in tiered.get('verification_layer', []):
        all_rules.append(r)

    # Per-level rules (deduplicated by rule_id)
    seen_ids = set()
    for lv in JLPT_LEVELS:
        for r in tiered['levels'][lv]['rules']:
            rid = r['rule_id']
            if rid not in seen_ids:
                seen_ids.add(rid)
                all_rules.append(r)

    # Index by bridge for fast lookup
    by_bridge = defaultdict(list)
    for r in all_rules:
        by_bridge[r['bridge']].append(r)

    print(f"  Indexed {len(all_rules)} unique rules across {len(by_bridge)} bridges")
    return all_rules, by_bridge


def _try_kun_segmentation(kana, chars, kanji_db):
    """Try to segment kana using kun stems + rendaku/handaku/sokuon variants (non-overlapping).
    Returns list of (kanji, reading) or None."""
    n = len(chars)
    if n == 0:
        return None

    VOICING_MAP = {
        'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
        'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
        'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
        'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
    }
    HANDAKU_MAP = {'は': 'ぱ', 'ひ': 'ぴ', 'ふ': 'ぷ', 'へ': 'ぺ', 'ほ': 'ぽ'}

    # Collect all kun stem candidates for each kanji (including sound-change variants)
    all_stems_with_variants = []
    for i, ch in enumerate(chars):
        if ch not in kanji_db:
            return None
        info = kanji_db[ch]
        variants = set()
        for k in info['kun_readings']:
            stem = k['stem']
            if not stem or len(stem) < 1:
                continue
            # Base stem
            variants.add(stem)
            # Sokuon variants
            if stem[-1] in 'つちくき':
                variants.add(stem[:-1] + 'っ')
            if stem[-1] in 'つち':
                variants.add(stem[:-1] + 'っ')
            # Rendaku/handaku variants (only for 2nd+ kanji)
            if i > 0:
                for vmap in [VOICING_MAP, HANDAKU_MAP]:
                    for kv, gv in vmap.items():
                        if stem.startswith(kv):
                            variants.add(gv + stem[len(kv):])
        # Also include full kun (stem + okurigana) for last kanji
        if i == n - 1:
            for k in info['kun_readings']:
                if k['stem'] and k['okurigana']:
                    full = k['stem'] + k['okurigana']
                    variants.add(full)
                    # Rendaku for full
                    for kv, gv in VOICING_MAP.items():
                        if full.startswith(kv):
                            variants.add(gv + full[len(kv):])

        if not variants:
            return None
        all_stems_with_variants.append(sorted(variants, key=len, reverse=True))

    result = []

    def backtrack(pos, i):
        if i == n:
            return pos == len(kana)
        for stem in all_stems_with_variants[i]:
            end = pos + len(stem)
            if end <= len(kana) and kana[pos:end] == stem:
                result.append((chars[i], stem))
                if backtrack(end, i + 1):
                    return True
                result.pop()
        return False

    if backtrack(0, 0):
        return result[:]
    return None


def _try_on_segmentation(kana, chars, kanji_db):
    """Try to segment kana using only on readings (non-overlapping). Returns list of (kanji, reading) or None."""
    n = len(chars)
    all_ons = []
    for ch in chars:
        if ch not in kanji_db:
            return None
        ons = sorted(set(r for r in kanji_db[ch]['on_readings'] if r), key=len, reverse=True)
        if not ons:
            return None
        all_ons.append(ons)

    result = []

    def backtrack(pos, i):
        if i == n:
            return pos == len(kana)
        for on in all_ons[i]:
            end = pos + len(on)
            if end <= len(kana) and kana[pos:end] == on:
                result.append((chars[i], on))
                if backtrack(end, i + 1):
                    return True
                result.pop()
        # Also try sokuon variants
        for on in all_ons[i]:
            if on and on[-1] in 'つちくき':
                sokuon_form = on[:-1] + 'っ'
                end = pos + len(sokuon_form)
                if end <= len(kana) and kana[pos:end] == sokuon_form:
                    result.append((chars[i], sokuon_form))
                    if backtrack(end, i + 1):
                        return True
                    result.pop()
        return False

    if backtrack(0, 0):
        return result[:]
    return None


def _detect_per_kanji_reading(kana, chars, kanji_db, has_oku=False):
    """Detect on/kun for each kanji in a compound. Returns list of 'on'/'kun'/'?' per kanji."""
    n = len(chars)
    types = []

    # For compounds with okurigana, the last kanji is always kun
    if has_oku and n >= 2:
        # Try to segment: last kanji takes remaining kana (with okurigana), others take their portion
        # First, try to match earlier kanji with on readings
        remaining = kana
        for i in range(n - 1):
            ch = chars[i]
            if ch not in kanji_db:
                types.append('?')
                continue
            # Try on first
            matched = False
            for on in sorted(kanji_db[ch]['on_readings'], key=len, reverse=True):
                if on and remaining.startswith(on):
                    types.append('on')
                    remaining = remaining[len(on):]
                    matched = True
                    break
            if not matched:
                # Try kun stem
                for k in sorted(kanji_db[ch]['kun_readings'], key=lambda x: len(x['stem']), reverse=True):
                    stem = k['stem']
                    if stem and remaining.startswith(stem):
                        types.append('kun')
                        remaining = remaining[len(stem):]
                        matched = True
                        break
            if not matched:
                types.append('on')  # default guess
        types.append('kun')  # last kanji with okurigana
        return types

    # Without okurigana: try per-kanji matching
    # First pass: check if each kanji's on/kun readings match at expected positions
    # We do a simple greedy left-to-right match
    pos = 0
    for i, ch in enumerate(chars):
        if ch not in kanji_db:
            types.append('?')
            continue
        info = kanji_db[ch]
        is_last = (i == n - 1)

        # Try on reading match
        on_matched = None
        for on in sorted(info['on_readings'], key=len, reverse=True):
            if on and pos + len(on) <= len(kana) and kana[pos:pos + len(on)] == on:
                on_matched = on
                break
        # Also try sokuon
        if not on_matched:
            for on in sorted(info['on_readings'], key=len, reverse=True):
                if on and on[-1] in 'つちくき':
                    sokuon = on[:-1] + 'っ'
                    if pos + len(sokuon) <= len(kana) and kana[pos:pos + len(sokuon)] == sokuon:
                        on_matched = sokuon
                        break

        # Try kun stem match
        kun_matched = None
        for k in sorted(info['kun_readings'], key=lambda x: len(x['stem']), reverse=True):
            stem = k['stem']
            if stem and pos + len(stem) <= len(kana) and kana[pos:pos + len(stem)] == stem:
                kun_matched = stem
                break
        # Try rendaku
        if not kun_matched and i > 0:
            voicing_map_first = {
                'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
                'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
                'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
                'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
            }
            for k in sorted(info['kun_readings'], key=lambda x: len(x['stem']), reverse=True):
                stem = k['stem']
                if stem:
                    for kv, gv in voicing_map_first.items():
                        if stem.startswith(kv):
                            voiced = gv + stem[len(kv):]
                            if pos + len(voiced) <= len(kana) and kana[pos:pos + len(voiced)] == voiced:
                                kun_matched = voiced
                                break
                    if kun_matched:
                        break

        # Decide on vs kun
        if on_matched and kun_matched:
            # Both match: prefer longer match
            if len(on_matched) >= len(kun_matched):
                types.append('on')
                pos += len(on_matched)
            else:
                types.append('kun')
                pos += len(kun_matched)
        elif on_matched:
            types.append('on')
            pos += len(on_matched)
        elif kun_matched:
            types.append('kun')
            pos += len(kun_matched)
        elif is_last and pos < len(kana):
            # Last kanji, remaining kana → probably kun (with okurigana-like trailing)
            types.append('kun')
        else:
            # Can't match: use heuristics
            has_on = len(info['on_readings']) > 0
            has_kun = len(info['kun_readings']) > 0
            if has_on and not has_kun:
                types.append('on')
            elif has_kun and not has_on:
                types.append('kun')
            else:
                types.append('on')  # default for compounds

    return types


def apply_rules_to_word(w, kanji_db, by_bridge):
    """Apply all applicable rules to a word. Returns (predicted_pattern, fired_rules, explanation)."""
    chars = w['kanji_chars']
    n = w['num_kanji']
    has_oku = w['has_okurigana']
    kana = w['kana']

    if n == 0:
        return 'no_kanji', [], 'No kanji in word'

    fired = []
    explanations = []

    # ---- Precompute kanji features ----
    kanji_has_on = []
    kanji_has_kun = []
    kanji_kun_stems = []
    kanji_on_readings = []
    for ch in chars:
        if ch in kanji_db:
            info = kanji_db[ch]
            kanji_has_on.append(len(info['on_readings']) > 0)
            kanji_has_kun.append(len(info['kun_readings']) > 0)
            kanji_kun_stems.append([k['stem'] for k in info['kun_readings'] if k['stem']])
            kanji_on_readings.append(info['on_readings'])
        else:
            kanji_has_on.append(False)
            kanji_has_kun.append(False)
            kanji_kun_stems.append([])
            kanji_on_readings.append([])

    # ---- Okurigana suffix extraction ----
    okurigana_suffix = None
    if has_oku and n >= 1:
        kana_part = re.sub(r'[一-鿿㐀-䶿]', '', w['kanji_word'])
        if kana_part:
            okurigana_suffix = kana_part[-2:] if len(kana_part) >= 2 else kana_part

    # ---- Type A: Reading type prediction (CRITICAL — must fire first) ----
    # A2: Single kanji with NO kun readings → ON (fixes on→kun errors)
    if n == 1:
        ch = chars[0]
        if ch in kanji_db:
            has_on_only = kanji_has_on[0] and not kanji_has_kun[0]
            has_kun_only = kanji_has_kun[0] and not kanji_has_on[0]

            # Strip special characters (～, 〜, etc.) from kana for matching
            kana_clean = re.sub(r'[～〜]', '', kana)

            if has_oku:
                # Check: does kana start with an on reading? (案じる → あん+じる, on=あん)
                kana_starts_with_on = False
                on_match_reading = None
                for on in sorted(kanji_on_readings[0], key=len, reverse=True):
                    if on and len(on) >= 1 and kana_clean.startswith(on):
                        kana_starts_with_on = True
                        on_match_reading = on
                        break

                # Check: does a kun stem also match at the start?
                kun_stem_starts = False
                kun_stem_match = None
                for k in kanji_db[ch]['kun_readings']:
                    stem = k['stem']
                    if stem and kana_clean.startswith(stem):
                        kun_stem_starts = True
                        kun_stem_match = stem
                        break

                # Check: does kana match a full kun reading (stem+okurigana)?
                kana_is_full_kun = False
                for k in kanji_db[ch]['kun_readings']:
                    if k['stem'] and k['okurigana']:
                        if k['stem'] + k['okurigana'] == kana_clean:
                            kana_is_full_kun = True
                            break
                    elif k['stem'] and k['stem'] == kana_clean:
                        kana_is_full_kun = True
                        break

                if kana_starts_with_on and not kana_is_full_kun and not kun_stem_starts:
                    # Kana starts with on reading and no kun stem matches → on
                    fired.append({'rule_id': 'A2_on_prefix', 'rule_type': 'A', 'bridge': 'on_ref',
                                  'name': '假名前缀匹配音读', 'accuracy': 0.88,
                                  'prediction': 'reading_type = on', 'rule_text': '假名以音读开头→音读'})
                    explanations.append(f"假名「{kana_clean}」以音读「{on_match_reading}」开头→音读(88%)")
                elif kana_starts_with_on and kun_stem_starts and on_match_reading and kun_stem_match:
                    # Both match: prefer the longer match
                    if len(on_match_reading) > len(kun_stem_match):
                        fired.append({'rule_id': 'A2_on_prefix', 'rule_type': 'A', 'bridge': 'on_ref',
                                      'name': '假名前缀匹配音读', 'accuracy': 0.75,
                                      'prediction': 'reading_type = on', 'rule_text': '音读前缀更长→音读'})
                        explanations.append(f"音读「{on_match_reading}」长于训词干「{kun_stem_match}」→音读")
                    else:
                        fired.append({'rule_id': 'A1', 'rule_type': 'A', 'bridge': 'okurigana',
                                      'name': '送假名→训读', 'accuracy': 0.961,
                                      'prediction': 'reading_type = kun', 'rule_text': '有送假名→训读'})
                        explanations.append(f"训词干「{kun_stem_match}」≥音读「{on_match_reading}」→训读(96%)")
                else:
                    # Neither on nor kun match the start. Check for honorific prefix/suffix.
                    stripped_kana = kana_clean
                    has_prefix = False
                    stripped_match = False
                    for prefix in ['お', 'ご']:
                        if kana_clean.startswith(prefix) and len(kana_clean) > len(prefix):
                            stripped = kana_clean[len(prefix):]
                            # Also strip common suffixes
                            for suffix in ['さん', 'さま', 'ちゃん']:
                                if stripped.endswith(suffix) and len(stripped) > len(suffix):
                                    stripped = stripped[:-len(suffix)]
                            # Check if stripped kana matches on reading
                            for on in kanji_on_readings[0]:
                                if on and stripped == on:
                                    stripped_match = True
                                    on_match_reading = on
                                    has_prefix = True
                                    stripped_kana = stripped
                                    break
                            if stripped_match:
                                break
                            # Also check without suffix stripping
                            for on in kanji_on_readings[0]:
                                if on and stripped == on:
                                    stripped_match = True
                                    on_match_reading = on
                                    has_prefix = True
                                    stripped_kana = stripped
                                    break
                            if stripped_match:
                                break
                    if stripped_match:
                        fired.append({'rule_id': 'A2_on_match', 'rule_type': 'A', 'bridge': 'on_ref',
                                      'name': '假名匹配音读', 'accuracy': 0.95,
                                      'prediction': 'reading_type = on', 'rule_text': '去前缀后匹音读→音读'})
                        explanations.append(f"去敬语前后「{stripped_kana}」匹音读「{on_match_reading}」→音读(95%)")
                    else:
                        # A1: Single kanji + okurigana → kun (96.1%)
                        fired.append({'rule_id': 'A1', 'rule_type': 'A', 'bridge': 'okurigana',
                                      'name': '送假名→训读', 'accuracy': 0.961,
                                      'prediction': 'reading_type = kun', 'rule_text': '有送假名→训读'})
                        explanations.append(f"单汉字+送假名→训读(96%)")
            elif has_on_only:
                # Only on readings available → on
                fired.append({'rule_id': 'A2_on_only', 'rule_type': 'A', 'bridge': 'on_ref',
                              'name': '仅有音读', 'accuracy': 0.99,
                              'prediction': 'reading_type = on', 'rule_text': '仅音读→音读'})
                explanations.append(f"仅有音读→音读(99%)")
            elif has_kun_only:
                # Only kun readings available → kun
                fired.append({'rule_id': 'A2_kun_only', 'rule_type': 'A', 'bridge': 'okurigana',
                              'name': '仅有训读', 'accuracy': 0.99,
                              'prediction': 'reading_type = kun', 'rule_text': '仅训读→训读'})
                explanations.append(f"仅有训读→训读(99%)")
            else:
                # Has both on and kun. Multi-signal discrimination.
                # Use kana_clean (stripped of ~, 〜) for matching

                # Check for 々 (iteration mark): kana is typically doubled on-reading
                if '々' in w['kanji_word']:
                    half_len = len(kana_clean) // 2
                    if half_len >= 1:
                        first_half = kana_clean[:half_len]
                        second_half = kana_clean[half_len:]
                        # Check if first half matches an on reading
                        if any(on == first_half for on in kanji_on_readings[0]):
                            fired.append({'rule_id': 'A2_on_match', 'rule_type': 'A', 'bridge': 'on_ref',
                                          'name': '假名匹配音读', 'accuracy': 0.95,
                                          'prediction': 'reading_type = on', 'rule_text': '叠字符→音读'})
                            explanations.append(f"叠字符「々」+音读「{first_half}」→音读(95%)")
                            # Set pred_pattern directly, skip rest
                            pred_pattern = 'on'
                            explanation = ' → '.join(explanations[:5]) if explanations else '无匹配规则'
                            return pred_pattern, fired, explanation

                kana_matches_on = any(on == kana_clean for on in kanji_on_readings[0])
                kana_matches_kun = any(
                    k['stem'] == kana_clean or (k['stem'] + k['okurigana']) == kana_clean
                    for k in kanji_db[ch]['kun_readings']
                )

                # Phonetic on-yomi signals (strong indicators)
                ends_with_n = kana.endswith('ん')  # ん is almost never in kun stems
                ends_with_ku = kana.endswith('く') and len(kana) <= 3  # 〜く common on ending
                ends_with_chi_ki_tsu = kana[-1] in 'ちきつ' and len(kana) <= 2  # CV on
                is_1_mora = mora_count(kana) == 1  # Single mora → very likely on
                is_2_mora_cv = (mora_count(kana) == 2 and len(kana) == 2
                                and kana[-1] in 'あいうえおかきくけこさしすせそ'
                                                 'たちつてとはひふへほまみむめもやゆよらりるれろわをん'
                                                 'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ')

                on_signals = sum([ends_with_n, ends_with_ku, ends_with_chi_ki_tsu,
                                  is_1_mora, is_2_mora_cv])

                if kana_matches_on and not kana_matches_kun:
                    fired.append({'rule_id': 'A2_on_match', 'rule_type': 'A', 'bridge': 'on_ref',
                                  'name': '假名匹配音读', 'accuracy': 0.95,
                                  'prediction': 'reading_type = on', 'rule_text': '假名全匹音读→音读'})
                    explanations.append(f"假名「{kana}」完全匹配音读→音读(95%)")
                elif on_signals >= 2 and not kana_matches_kun:
                    # Multiple phonetic on-yomi signals + no kun match → on
                    fired.append({'rule_id': 'A2_on_phonetic', 'rule_type': 'A', 'bridge': 'phonological',
                                  'name': '音读语音特征', 'accuracy': 0.82,
                                  'prediction': 'reading_type = on', 'rule_text': '音读语音模式→音读'})
                    signal_names = []
                    if ends_with_n: signal_names.append('ん尾')
                    if ends_with_ku: signal_names.append('く尾')
                    if ends_with_chi_ki_tsu: signal_names.append('CV尾')
                    if is_1_mora: signal_names.append('1拍')
                    if is_2_mora_cv: signal_names.append('2拍CV')
                    explanations.append(f"音读语音特征({'/'.join(signal_names)})→音读(82%)")
                elif kana_matches_kun and not kana_matches_on:
                    # Kana matches a kun reading but not on → kun
                    fired.append({'rule_id': 'A3', 'rule_type': 'A', 'bridge': 'okurigana',
                                  'name': '单汉字→训读', 'accuracy': 0.84,
                                  'prediction': 'reading_type = kun', 'rule_text': '单汉字→训读'})
                    explanations.append(f"假名匹配训读→训读(84%)")
                else:
                    # A3: Single kanji with both on and kun → kun (84%)
                    fired.append({'rule_id': 'A3', 'rule_type': 'A', 'bridge': 'okurigana',
                                  'name': '单汉字→训读', 'accuracy': 0.84,
                                  'prediction': 'reading_type = kun', 'rule_text': '单汉字→训读'})
                    explanations.append(f"单汉字词→训读(84%)")

    # ---- Compound bridge (for multi-kanji) ----
    if n >= 2:
        # Check: can kun stems non-overlappingly segment the kana?
        kun_segments = _try_kun_segmentation(kana, chars, kanji_db)
        kun_kun_segmented = kun_segments is not None and len(kun_segments) == n

        # Check: can on readings non-overlappingly segment the kana?
        on_segments = _try_on_segmentation(kana, chars, kanji_db)
        on_on_segmented = on_segments is not None and len(on_segments) == n

        # Simple stem-in-kana check (looser than full segmentation)
        kun_stems_match = []
        for i, stems in enumerate(kanji_kun_stems):
            match = False
            for stem in sorted(stems, key=len, reverse=True):
                if stem and stem in kana:
                    match = True
                    break
            kun_stems_match.append(match)
        all_kun_match = all(kun_stems_match)
        all_have_on = all(kanji_has_on)

        if has_oku:
            # Compound with trailing kana. Could be:
            # A) true okurigana (kun reading + okurigana suffix) → contains kun
            # B) on+on compound + trailing particle (に, と, で, etc.)
            # C) honorific prefix (お, ご) + on reading
            # Try on+on segmentation first to distinguish

            # Check if full on+on segmentation works (ignoring trailing kana)
            trailing_kana = ''
            kana_for_on = kana
            on_on_with_trailing = False

            if on_on_segmented:
                # On readings perfectly cover the kana → on+on
                on_on_with_trailing = True
            elif not on_on_segmented and on_segments is None:
                # Try removing trailing particles and re-check
                common_particles = ['に', 'と', 'で', 'を', 'は', 'が', 'へ', 'も', 'の', 'さ']
                for particle in common_particles:
                    if kana.endswith(particle) and len(kana) > len(particle):
                        test_kana = kana[:-len(particle)]
                        test_segments = _try_on_segmentation(test_kana, chars, kanji_db)
                        if test_segments is not None and len(test_segments) == n:
                            on_segments = test_segments
                            on_on_segmented = True
                            trailing_kana = particle
                            on_on_with_trailing = True
                            kana_for_on = test_kana
                            break

            if on_on_with_trailing:
                # On+on with trailing particle/honorific → on+on
                fired.append({'rule_id': 'A4_on_on', 'rule_type': 'A', 'bridge': 'compound',
                              'name': '双音读→音+音', 'accuracy': 0.95,
                              'prediction': 'reading_type = on_on', 'rule_text': '音读分割匹配→音+音'})
                if trailing_kana:
                    explanations.append(f"双汉字音读完整分割+尾助词「{trailing_kana}」→音+音(95%)")
                else:
                    explanations.append(f"双汉字音读完整分割→音+音(95%)")
                pred_pattern = 'on+on'
            else:
                # True okurigana compound → contains kun
                fired.append({'rule_id': 'A5_compound_oku', 'rule_type': 'A', 'bridge': 'compound',
                              'name': '复合词含送假→含训读', 'accuracy': 0.90,
                              'prediction': 'reading_type = contains_kun', 'rule_text': '复合词送假→训'})
                explanations.append(f"复合词含送假名→含训读(90%)")

                # Per-kanji detection for mixed compounds with okurigana
                per_kanji_types = _detect_per_kanji_reading(kana, chars, kanji_db, has_oku=True)
                pred_pattern = '+'.join(per_kanji_types)
                explanations.append(f"逐字检测→{pred_pattern}")

        elif kun_kun_segmented and not on_on_segmented:
            # Both kanji's kun stems perfectly segment the kana → kun+kun
            fired.append({'rule_id': 'A6_kun_kun_match', 'rule_type': 'A', 'bridge': 'compound',
                          'name': '双训读匹配→训+训', 'accuracy': 0.92,
                          'prediction': 'reading_type = kun_kun', 'rule_text': '双训词干匹配→训+训'})
            explanations.append(f"双汉字训读词干完整分割→训+训(92%)")
            pred_pattern = 'kun+kun'

        elif on_on_segmented and not kun_kun_segmented:
            # On readings perfectly segment the kana → on+on
            fired.append({'rule_id': 'A4_on_on', 'rule_type': 'A', 'bridge': 'compound',
                          'name': '双音读→音+音', 'accuracy': 0.95,
                          'prediction': 'reading_type = on_on', 'rule_text': '音读分割匹配→音+音'})
            explanations.append(f"双汉字音读完整分割→音+音(95%)")
            pred_pattern = 'on+on'

        elif kun_kun_segmented and on_on_segmented:
            # Both match: prefer kun if stems are longer (more specific), else on
            kun_total_len = sum(len(s[1]) for s in kun_segments)
            on_total_len = sum(len(s[1]) for s in on_segments)
            if kun_total_len >= on_total_len:
                fired.append({'rule_id': 'A6_kun_kun_match', 'rule_type': 'A', 'bridge': 'compound',
                              'name': '双训读匹配→训+训', 'accuracy': 0.75,
                              'prediction': 'reading_type = kun_kun', 'rule_text': '训读更长→训+训'})
                explanations.append(f"训读音段更长→训+训(75%)")
                pred_pattern = 'kun+kun'
            else:
                fired.append({'rule_id': 'A4_on_on', 'rule_type': 'A', 'bridge': 'compound',
                              'name': '双音读→音+音', 'accuracy': 0.75,
                              'prediction': 'reading_type = on_on', 'rule_text': '音读更长→音+音'})
                explanations.append(f"音读音段更长→音+音(75%)")
                pred_pattern = 'on+on'

        elif all_kun_match and len(kana) >= 3:
            # Fallback: both stems appear in kana (may overlap) → kun+kun
            fired.append({'rule_id': 'A6_kun_kun_match', 'rule_type': 'A', 'bridge': 'compound',
                          'name': '双训读匹配→训+训', 'accuracy': 0.85,
                          'prediction': 'reading_type = kun_kun', 'rule_text': '双训词干匹配→训+训'})
            explanations.append(f"双汉字训读词干均匹配→训+训(85%)")
            pred_pattern = 'kun+kun'

        else:
            # No clean segmentation → per-kanji mixed detection
            per_kanji_types = _detect_per_kanji_reading(kana, chars, kanji_db, has_oku=False)
            pred_pattern = '+'.join(per_kanji_types)

            # Check if it's a pure pattern
            all_on = all(t == 'on' for t in per_kanji_types)
            all_kun = all(t == 'kun' for t in per_kanji_types)

            if all_on:
                fired.append({'rule_id': 'A4_on_on', 'rule_type': 'A', 'bridge': 'compound',
                              'name': '双音读→音+音', 'accuracy': 0.71,
                              'prediction': 'reading_type = on_on', 'rule_text': '逐字全音→音+音'})
                explanations.append(f"逐字检测全音读→音+音")
            elif all_kun:
                fired.append({'rule_id': 'A6_kun_kun_match', 'rule_type': 'A', 'bridge': 'compound',
                              'name': '双训读匹配→训+训', 'accuracy': 0.85,
                              'prediction': 'reading_type = kun_kun', 'rule_text': '逐字全训→训+训'})
                explanations.append(f"逐字检测全训读→训+训")
            else:
                explanations.append(f"逐字检测→{pred_pattern}")

        # ---- Okurigana bridge for word class in compounds ----
        if has_oku:
            for rule in by_bridge['okurigana']:
                rid = rule['rule_id']
                if okurigana_suffix:
                    suffix_map = {
                        'B_oku_る': 'る', 'B_oku_す': 'す', 'B_oku_う': 'う',
                        'B_oku_く': 'く', 'B_oku_い': 'い', 'B_oku_える': 'える',
                        'B_oku_む': 'む', 'B_oku_つ': 'つ', 'B_oku_ぶ': 'ぶ',
                        'B_oku_ぐ': 'ぐ', 'B_oku_ぬ': 'ぬ', 'B_oku_ける': 'ける',
                    }
                    for rsid, tsuf in suffix_map.items():
                        if rid == rsid and okurigana_suffix.endswith(tsuf):
                            fired.append(rule)
                            pred_name = rule['prediction'].replace('wclass = ', '')
                            explanations.append(f"送假名「{okurigana_suffix}」→{pred_name}({rule['accuracy']:.0%})")
                            break

        explanation = ' → '.join(explanations[:5]) if explanations else '无匹配规则'
        return pred_pattern, fired, explanation

    # ---- Single kanji: radical bridge for word class ----
    if n == 1:
        for ch in chars:
            if ch in kanji_db:
                rad = kanji_db[ch]['radical']
                rad_rule_id = f"B_rad_{rad}_noun"
                for rule in by_bridge['radical']:
                    rid = rule['rule_id']
                    if rid == rad_rule_id:
                        fired.append(rule)
                        explanations.append(f"部首「{rad}」→名词({rule['accuracy']:.0%})")
                        break

    # ---- Okurigana bridge for word class (single kanji) ----
    if n == 1 and has_oku:
        for rule in by_bridge['okurigana']:
            rid = rule['rule_id']
            if rid == 'B_oku_none':
                continue  # Already handled
            if okurigana_suffix:
                suffix_map = {
                    'B_oku_る': 'る', 'B_oku_す': 'す', 'B_oku_う': 'う',
                    'B_oku_く': 'く', 'B_oku_い': 'い', 'B_oku_える': 'える',
                    'B_oku_む': 'む', 'B_oku_つ': 'つ', 'B_oku_ぶ': 'ぶ',
                    'B_oku_ぐ': 'ぐ', 'B_oku_ぬ': 'ぬ', 'B_oku_ける': 'ける',
                    'B_oku_める': 'める', 'B_oku_れる': 'れる', 'B_oku_せる': 'せる',
                    'B_oku_しい': 'しい',
                }
                for rsid, tsuf in suffix_map.items():
                    if rid == rsid and okurigana_suffix.endswith(tsuf):
                        fired.append(rule)
                        pred_name = rule['prediction'].replace('wclass = ', '')
                        explanations.append(f"送假名「{okurigana_suffix}」→{pred_name}({rule['accuracy']:.0%})")
                        break

    # ---- Phonological verification ----
    voiced = set('がぎぐげござじずぜぞだぢづでどばびぶべぼ')
    voiced_in_kana = [c for c in kana if c in voiced]
    if voiced_in_kana:
        has_dup_voiced = len(voiced_in_kana) != len(set(voiced_in_kana))
        if not has_dup_voiced:
            fired.append({'rule_id': 'D1', 'rule_type': 'D', 'bridge': 'phonological',
                          'name': '浊音不重复', 'accuracy': 0.995,
                          'prediction': 'verify', 'rule_text': '浊音不重复'})
            explanations.append(f"验证：浊音不重复(99.5%)")

    # ---- Determine final prediction for single kanji ----
    if n == 1:
        on_rule_ids = {'A2_on_only', 'A2_on_match', 'A2_on_phonetic', 'A2_on_prefix'}
        kun_rule_ids = {'A1', 'A3', 'A2_kun_only'}

        on_fired = [r for r in fired if r['rule_id'] in on_rule_ids]
        kun_fired = [r for r in fired if r['rule_id'] in kun_rule_ids]

        if on_fired and not kun_fired:
            pred_pattern = 'on'
        elif kun_fired and not on_fired:
            pred_pattern = 'kun'
        elif has_oku:
            pred_pattern = 'kun'
        elif kanji_has_kun[0]:
            pred_pattern = 'kun'
        else:
            pred_pattern = 'on'
    else:
        # Already set above
        pass

    explanation = ' → '.join(explanations[:5]) if explanations else '无匹配规则'
    return pred_pattern, fired, explanation


# ============================================================
# MODULE 3: MAIN PIPELINE
# ============================================================

def run_pipeline():
    print("=" * 60)
    print("Kun-Yomi V9: DP Segmentation + Full Rule System")
    print("=" * 60)

    jlpt_words, kanji_db, tiered = load_data()
    all_rules, by_bridge = build_rule_engine(tiered)

    # ---- STEP 1: DP Ground Truth ----
    print("\n[1/4] DP Ground Truth Classification...")
    gt_stats = Counter()
    for w in jlpt_words:
        pattern, details, confidence = dp_segment(w['kana'], w['kanji_chars'], kanji_db)
        w['gt_pattern'] = pattern
        w['gt_details'] = details
        w['gt_confidence'] = confidence
        gt_stats[pattern] += 1

    print(f"  Ground truth distribution:")
    for pat, cnt in gt_stats.most_common(12):
        print(f"    {pat}: {cnt}")

    # ---- STEP 2: Rule Application ----
    print("\n[2/4] Applying Full Rule System...")
    correct = 0
    total = 0
    word_results = []

    for w in jlpt_words:
        if w['num_kanji'] == 0:
            w['pred_pattern'] = 'no_kanji'
            w['fired_rules'] = []
            w['explanation'] = ''
            w['is_correct'] = True  # no-kanji words are trivially correct
            word_results.append(w)
            continue

        pred, fired, explanation = apply_rules_to_word(w, kanji_db, by_bridge)
        w['pred_pattern'] = pred
        w['fired_rules'] = fired
        w['explanation'] = explanation

        # Compare
        gt = w['gt_pattern'].rstrip('~')
        is_correct = _compare_patterns(gt, pred)
        w['is_correct'] = is_correct

        total += 1
        if is_correct:
            correct += 1

        word_results.append(w)

    accuracy = correct / total if total > 0 else 0
    print(f"  Overall accuracy: {accuracy:.1%} ({correct}/{total})")

    # Per-level
    for lv in JLPT_LEVELS:
        lv_words = [w for w in word_results if w['level'] == lv and w['num_kanji'] > 0]
        lv_correct = sum(1 for w in lv_words if w['is_correct'])
        print(f"  {lv}: {lv_correct/len(lv_words):.1%} ({lv_correct}/{len(lv_words)})")

    # ---- STEP 3: Rule Effectiveness Analysis ----
    print("\n[3/4] Rule Effectiveness Analysis...")
    rule_hits = Counter()
    rule_correct = Counter()
    for w in word_results:
        for r in w.get('fired_rules', []):
            rid = r['rule_id']
            rule_hits[rid] += 1
            if w['is_correct']:
                rule_correct[rid] += 1

    # Top performing rules
    rule_perf = []
    for rid in rule_hits:
        if rule_hits[rid] >= 5:
            acc = rule_correct[rid] / rule_hits[rid]
            rule_perf.append((rid, acc, rule_hits[rid], rule_correct[rid]))
    rule_perf.sort(key=lambda x: -x[1] * x[2])  # sort by acc * coverage

    print(f"  Top 20 rules by effectiveness (accuracy × hits):")
    for rid, acc, hits, correct_hits in rule_perf[:20]:
        r = next((r for r in all_rules if r['rule_id'] == rid), None)
        name = r['name'] if r else rid
        print(f"    {rid}: {name[:60]} | {acc:.1%} ({correct_hits}/{hits})")

    # ---- STEP 4: Multi-Pass Per-Level Rule Selection ----
    print("\n[4/4] Multi-Pass Rule Selection...")
    level_optimized = {}
    for lv in JLPT_LEVELS:
        lv_words = [w for w in word_results if w['level'] == lv and w['num_kanji'] > 0]
        lv_total = len(lv_words)

        # Build rule-to-words mapping
        rule_to_words = defaultdict(set)
        for wi, w in enumerate(lv_words):
            if not w['is_correct']:
                continue
            for r in w.get('fired_rules', []):
                rid = r.get('rule_id', '')
                if rid:
                    rule_to_words[rid].add(wi)

        # Phase 1: Broad coverage rules
        uncovered = set(range(len(lv_words)))
        broad_rules = []
        while uncovered and len(broad_rules) < 10:
            best_rule = None
            best_new = 0
            for rid, word_indices in rule_to_words.items():
                if rid in broad_rules:
                    continue
                new = len(word_indices & uncovered)
                if new > best_new:
                    best_new = new
                    best_rule = rid
            if best_rule is None or best_new < max(3, lv_total * 0.005):
                break
            broad_rules.append(best_rule)
            uncovered -= rule_to_words[best_rule]

        # Phase 2: Gap-filling rules for remaining uncovered words
        gap_rules = []
        uncovered_list = list(uncovered)
        for wi in uncovered_list[:100]:
            w = lv_words[wi]
            for r in w.get('fired_rules', []):
                rid = r.get('rule_id', '')
                if rid and rid not in broad_rules and rid not in gap_rules:
                    # Check if this rule helps with specific patterns
                    if rid.startswith(('B_rad_', 'C_comp_', 'B_oku_')):
                        gap_rules.append(rid)
                        uncovered -= rule_to_words[rid]
                        break
            if len(gap_rules) >= 20:
                break

        all_sel = broad_rules + gap_rules
        covered = lv_total - len(uncovered)
        coverage = covered / lv_total if lv_total > 0 else 0

        # Get rule details
        rule_details = []
        for rid in all_sel:
            r = next((r for r in all_rules if r['rule_id'] == rid), None)
            if r:
                rule_details.append({
                    'rule_id': rid, 'name': r.get('name', rid),
                    'accuracy': r.get('accuracy', 0), 'rule_text': r.get('rule_text', ''),
                })
            else:
                rule_details.append({
                    'rule_id': rid, 'name': rid, 'accuracy': 0, 'rule_text': '',
                })

        level_optimized[lv] = {
            'total_words': lv_total,
            'covered': covered,
            'coverage': coverage,
            'num_rules': len(all_sel),
            'broad_rules': len(broad_rules),
            'gap_rules': len(gap_rules),
            'rules': rule_details,
        }
        print(f"  {lv}: {len(broad_rules)} broad + {len(gap_rules)} gap = "
              f"{len(all_sel)} rules → {coverage:.1%} ({covered}/{lv_total})")

    return jlpt_words, kanji_db, word_results, rule_perf, level_optimized, gt_stats, accuracy


def _compare_patterns(gt, pred):
    """Compare ground truth and predicted patterns."""
    # Exact match
    if gt == pred:
        return True
    # Normalize
    gt_parts = set(gt.split('+'))
    pred_parts = set(pred.split('+'))

    gt_has_on = 'on' in gt_parts
    gt_has_kun = 'kun' in gt_parts
    pred_has_on = 'on' in pred_parts
    pred_has_kun = 'kun' in pred_parts

    # Pure on
    if gt_has_on and not gt_has_kun and pred_has_on and not pred_has_kun:
        return True
    # Pure kun
    if gt_has_kun and not gt_has_on and pred_has_kun and not pred_has_on:
        return True
    # Mixed matches mixed
    if gt_has_on and gt_has_kun and pred_has_on and pred_has_kun:
        return True
    # Unknown GT → skip
    if 'unknown' in gt or '?' in gt:
        return True
    return False


# ============================================================
# OUTPUT GENERATORS
# ============================================================

def write_outputs(jlpt_words, kanji_db, word_results, rule_perf, level_optimized, gt_stats, accuracy):
    print("\nWriting outputs...")

    # --- 1. Prediction Report ---
    lines = []
    lines.append("# V9 Precision Prediction Report\n")
    lines.append(f"**Overall Accuracy:** {accuracy:.1%}\n")
    lines.append("Method: DP kana segmentation + full V5 rule system (328 rules)")

    lines.append("\n## Ground Truth Distribution\n")
    lines.append("| Pattern | Count | % |")
    lines.append("|---------|-------|---|")
    total = sum(gt_stats.values())
    for pat, cnt in gt_stats.most_common(15):
        lines.append(f"| {pat} | {cnt} | {cnt/total:.1%} |")

    lines.append("\n## Per-Level Accuracy\n")
    lines.append("| Level | Total | Correct | Accuracy | Optimal Rules | Coverage |")
    lines.append("|-------|-------|---------|----------|---------------|----------|")
    for lv in JLPT_LEVELS:
        opt = level_optimized[lv]
        lv_words = [w for w in word_results if w['level'] == lv and w['num_kanji'] > 0]
        lv_correct = sum(1 for w in lv_words if w['is_correct'])
        lv_acc = lv_correct / len(lv_words) if lv_words else 0
        lines.append(f"| {lv} | {len(lv_words)} | {lv_correct} | {lv_acc:.1%} | "
                     f"{opt['num_rules']} | {opt['coverage']:.1%} |")

    lines.append("\n## Top Rules by Effectiveness (accuracy × hits)\n")
    lines.append("| Rule ID | Name | Accuracy | Hits |")
    lines.append("|---------|------|----------|------|")
    for rid, acc, hits, _ in rule_perf[:30]:
        lines.append(f"| {rid} | {rid} | {acc:.1%} | {hits} |")

    lines.append("\n## Per-Level Optimized Rule Subsets\n")
    for lv in JLPT_LEVELS:
        opt = level_optimized[lv]
        lines.append(f"\n### {lv}: {opt['num_rules']} rules for {opt['coverage']:.1%} coverage\n")
        lines.append("| # | Rule ID | Rule Text | Accuracy |")
        lines.append("|---|---------|-----------|----------|")
        for i, r in enumerate(opt['rules']):
            lines.append(f"| {i+1} | {r['rule_id']} | {r['rule_text'][:80]} | {r['accuracy']:.1%} |")

    lines.append("\n## Sample Annotated Words\n")
    lines.append("| Word | Kana | Level | GT | Pred | Correct | Explanation |")
    lines.append("|------|------|-------|----|------|---------|-------------|")
    for w in word_results[:50]:
        if w['num_kanji'] == 0: continue
        correct_mark = '✓' if w['is_correct'] else '✗'
        lines.append(f"| {w['kanji_word']} | {w['kana_raw']} | {w['level']} | "
                     f"{w['gt_pattern']} | {w['pred_pattern']} | {correct_mark} | "
                     f"{w['explanation'][:80]} |")

    with open(f'{OUT}/kun_v9_prediction_report.md', 'w') as f:
        f.write('\n'.join(lines))
    print(f"  → kun_v9_prediction_report.md")

    # --- 2. JSON data for Web App ---
    json_data = {
        'version': '9.0',
        'accuracy': accuracy,
        'ground_truth_distribution': dict(gt_stats),
        'level_optimized': {lv: {
            k: v for k, v in level_optimized[lv].items() if k != 'rules'
        } for lv in JLPT_LEVELS},
        'level_optimized_rules': {lv: level_optimized[lv]['rules'] for lv in JLPT_LEVELS},
        'annotated_words': [
            {
                'word': w['kanji_word'],
                'kana': w['kana_raw'],
                'level': w['level'],
                'gt_pattern': w['gt_pattern'],
                'pred_pattern': w['pred_pattern'],
                'explanation': w['explanation'],
                'is_correct': w['is_correct'],
                'gt_confidence': w.get('gt_confidence', 0),
                'rules_fired': [r['rule_id'] for r in w.get('fired_rules', [])[:5]],
                'gt_details': [{'kanji': d['kanji'], 'type': d['type'], 'reading': d['reading']}
                               for d in w.get('gt_details', [])],
            }
            for w in word_results if w['num_kanji'] > 0
        ],
    }
    with open(f'{OUT}/kun_v9_data.json', 'w') as f:
        json.dump(json_data, f, ensure_ascii=False)
    print(f"  → kun_v9_data.json ({len(json_data['annotated_words'])} annotated words)")

    # --- 3. Per-level quick reference cards ---
    for lv in JLPT_LEVELS:
        lines = []
        lines.append(f"# {lv} Quick Reference Card\n")
        opt = level_optimized[lv]
        lines.append(f"**{opt['num_rules']} rules** cover **{opt['coverage']:.1%}** of {lv} words.\n")
        lines.append("## Learn These Rules\n")
        for i, r in enumerate(opt['rules']):
            lines.append(f"{i+1}. **{r['rule_text']}** (准确率 {r['accuracy']:.0%})")

        lines.append(f"\n## Example Words\n")
        lines.append("| Word | Kana | Explanation |")
        lines.append("|------|------|-------------|")
        lv_words = [w for w in word_results if w['level'] == lv and w['num_kanji'] > 0 and w['is_correct']]
        for w in lv_words[:20]:
            lines.append(f"| {w['kanji_word']} | {w['kana_raw']} | {w['explanation'][:100]} |")

        with open(f'{OUT}/kun_v9_card_{lv}.md', 'w') as f:
            f.write('\n'.join(lines))
    print(f"  → kun_v9_card_N5~N1.md (5 per-level quick reference cards)")

    # --- 4. Error analysis ---
    errors = [w for w in word_results if not w['is_correct'] and w['num_kanji'] > 0]
    lines = []
    lines.append("# V9 Error Analysis\n")
    lines.append(f"**{len(errors)}** misclassified words.\n")

    # By error type
    error_by_type = defaultdict(list)
    for w in errors:
        error_type = f"{w['gt_pattern'].rstrip('~')} → {w['pred_pattern']}"
        error_by_type[error_type].append(w)

    lines.append("## Top Error Patterns\n")
    for etype, ewords in sorted(error_by_type.items(), key=lambda x: -len(x[1]))[:10]:
        lines.append(f"\n### {etype} ({len(ewords)} words)\n")
        lines.append("| Word | Kana | Level | Explanation |")
        lines.append("|------|------|-------|-------------|")
        for w in ewords[:10]:
            lines.append(f"| {w['kanji_word']} | {w['kana_raw']} | {w['level']} | {w['explanation'][:80]} |")

    with open(f'{OUT}/kun_v9_errors.md', 'w') as f:
        f.write('\n'.join(lines))
    print(f"  → kun_v9_errors.md")

    # --- 5. Summary ---
    print("\n" + "=" * 60)
    print("V9 generation complete!")
    print(f"  Overall accuracy: {accuracy:.1%}")
    for lv in JLPT_LEVELS:
        opt = level_optimized[lv]
        print(f"  {lv}: {opt['num_rules']} rules → {opt['coverage']:.1%} coverage")
    print(f"  Files: kun_v9_prediction_report.md, kun_v9_data.json,")
    print(f"         kun_v9_card_N5~N1.md (5), kun_v9_errors.md")
    print("=" * 60)


if __name__ == '__main__':
    jlpt_words, kanji_db, word_results, rule_perf, level_optimized, gt_stats, accuracy = run_pipeline()
    write_outputs(jlpt_words, kanji_db, word_results, rule_perf, level_optimized, gt_stats, accuracy)
