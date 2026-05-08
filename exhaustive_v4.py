#!/usr/bin/env python3
"""
v4: 穷举所有同训/近训/同词源字群
- 按训读词干穷举分组所有汉字
- 同音读分组
- 近训(音韵相近)字群
- 自他对全量清单
- 产出: 逐字分组清单 + 宏观规律总结
"""

import openpyxl, re, json, time
from collections import defaultdict, Counter
from typing import Dict, List, Tuple

BASE = '/Volumes/SSD/work/kanji-kun'

# ═══════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════

def load_all():
    wb = openpyxl.load_workbook(f'{BASE}/漢字検索V2.xlsm', read_only=True, data_only=True)
    ws = wb['漢字一覧']
    kanji_data = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None: continue
        kanji = str(row[0]).strip()
        if not kanji or len(kanji) > 2: continue

        components = str(row[1]) if row[1] else ''
        radical = str(row[3]) if row[3] else ''
        total_strokes = int(row[8]) if row[8] else 0
        on_raw = str(row[9]) if row[9] else ''
        kun_raw = str(row[10]) if row[10] else ''
        meaning = str(row[11]) if row[11] else ''

        # Parse readings
        kun_entries = []
        for entry in re.split(r'[、\s]+', kun_raw):
            entry = entry.strip().strip('◇◆▼▽▲△▼▽').strip()
            if not entry: continue
            parts = re.split(r'[・.]', entry)
            stem = parts[0]
            okuri = parts[-1] if len(parts) >= 2 else ''
            full = stem + ('.' + okuri if okuri else '')
            kun_entries.append({'stem': stem, 'okuri': okuri, 'full': full, 'mora': count_morae(stem)})

        on_entries = []
        for e in re.split(r'[、\s]+', on_raw):
            e = e.strip().strip('◇◆▼▽▲△▽').strip()
            if e and not e.startswith('◆') and e != '未詳':
                e = re.sub(r'[（(].*?[）)]', '', e).strip()
                if e and len(e) <= 4:
                    on_entries.append(e)

        kanji_data.append({
            'kanji': kanji, 'radical': radical,
            'components': components, 'strokes': total_strokes,
            'kun_list': kun_entries, 'on_list': on_entries,
            'meaning_snip': meaning[:80] if meaning else '',
        })
    wb.close()
    return kanji_data


def count_morae(s):
    cnt = i = 0
    while i < len(s):
        if i+1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉャュョァィゥェォ':
            cnt += 1; i += 2
        elif s[i] in 'っッ': cnt += 1; i += 1
        else: cnt += 1; i += 1
    return cnt


def to_hira(s):
    """Katakana to hiragana"""
    r = []
    for c in s:
        code = ord(c)
        if 0x30A1 <= code <= 0x30F6:
            r.append(chr(code - 0x60))
        else:
            r.append(c)
    return ''.join(r)


# ═══════════════════════════════════
# 1. SAME-KUN GROUPS (FULL ENUMERATION)
# ═══════════════════════════════════

def enumerate_same_kun(kanji_data):
    """Group ALL kanji by shared kun stem."""
    stem_groups = defaultdict(list)     # stem → list of kanji
    full_kun_groups = defaultdict(list) # stem.okuri → list of kanji

    for k in kanji_data:
        for ku in k['kun_list']:
            stem_groups[ku['stem']].append({
                'kanji': k['kanji'], 'okuri': ku['okuri'],
                'radical': k['radical'], 'meaning': k['meaning_snip'],
            })
            full_kun_groups[ku['full']].append({
                'kanji': k['kanji'], 'radical': k['radical'],
                'meaning': k['meaning_snip'],
            })

    # Filter to groups with 2+ kanji, sort by size
    same_stem = {s: items for s, items in stem_groups.items()
                 if len(set(it['kanji'] for it in items)) >= 2}
    same_full = {f: items for f, items in full_kun_groups.items()
                 if len(set(it['kanji'] for it in items)) >= 2}

    return same_stem, same_full


# ═══════════════════════════════════
# 2. SAME-ON GROUPS
# ═══════════════════════════════════

def enumerate_same_on(kanji_data):
    """Group ALL kanji by shared on reading (hiragana form)."""
    on_groups = defaultdict(list)
    for k in kanji_data:
        for on in k['on_list']:
            on_hira = to_hira(on)
            on_groups[on_hira].append({
                'kanji': k['kanji'], 'radical': k['radical'],
                'kun_list': [ku['full'] for ku in k['kun_list'][:3]],
                'meaning': k['meaning_snip'],
            })

    same_on = {o: items for o, items in on_groups.items()
               if len(set(it['kanji'] for it in items)) >= 3}
    return same_on


# ═══════════════════════════════════
# 3. NEAR-KUN GROUPS (PHONOLOGICALLY CLOSE)
# ═══════════════════════════════════

def find_near_kun(kanji_data):
    """Find kanji groups whose kun stems are phonologically close
    (differ by one mora, rendaku, or vowel alternation)."""
    # Build stem→kanji index
    stem_index = defaultdict(list)
    for k in kanji_data:
        for ku in k['kun_list']:
            if ku['stem']:
                stem_index[ku['stem']].append(k['kanji'])

    near_groups = []

    # 1. Rendaku pairs: voiced/unvoiced initial consonant
    rendaku_pairs_map = {
        'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご',
        'さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ',
        'た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど',
        'は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ',
    }
    for stem, kanjis in list(stem_index.items()):
        if not stem: continue
        first = stem[0]
        if len(stem) > 1 and stem[1] in 'ゃゅょ':
            first = stem[:2]
        if first in rendaku_pairs_map:
            voiced_first = rendaku_pairs_map[first]
            voiced_stem = voiced_first + stem[len(first):]
        else:
            # Reverse: voiced → unvoiced
            rev_map = {v:k for k,v in rendaku_pairs_map.items()}
            if first in rev_map:
                voiced_stem = None
                unvoiced_stem = rev_map[first] + stem[len(first):]
                if unvoiced_stem in stem_index:
                    all_kanji = set(kanjis) | set(stem_index[unvoiced_stem])
                    if len(all_kanji) >= 3:
                        near_groups.append({
                            'type': 'rendaku',
                            'stems': [unvoiced_stem, stem],
                            'kanji': sorted(all_kanji),
                            'count': len(all_kanji),
                        })
            continue

        if voiced_stem and voiced_stem in stem_index:
            all_kanji = set(kanjis) | set(stem_index[voiced_stem])
            if len(all_kanji) >= 3:
                near_groups.append({
                    'type': 'rendaku',
                    'stems': [stem, voiced_stem],
                    'kanji': sorted(all_kanji),
                    'count': len(all_kanji),
                })

    # 2. Vowel alternation: same consonants, different final vowel
    # e.g., くろ↔くら, しろ↔しら
    vowel_alt_pairs = [('あ','え'), ('あ','お'), ('い','え'), ('い','お'),
                       ('う','え'), ('う','お'), ('お','あ'), ('お','え')]
    for stem, kanjis in list(stem_index.items()):
        if len(stem) < 1: continue
        last = stem[-1]
        for v1, v2 in vowel_alt_pairs:
            if last == v1:
                alt_stem = stem[:-1] + v2
                if alt_stem in stem_index:
                    all_k = set(kanjis) | set(stem_index[alt_stem])
                    if len(all_k) >= 3:
                        near_groups.append({
                            'type': 'vowel_alt',
                            'stems': [stem, alt_stem],
                            'kanji': sorted(all_k),
                            'count': len(all_k),
                        })

    # Deduplicate near groups
    seen = set()
    unique_near = []
    for ng in near_groups:
        key = tuple(sorted(ng['stems']))
        if key not in seen:
            seen.add(key)
            unique_near.append(ng)

    unique_near.sort(key=lambda x: x['count'], reverse=True)
    return unique_near


# ═══════════════════════════════════
# 4. COMPLETE TRANSITIVITY PAIRS
# ═══════════════════════════════════

TRANS_PATTERNS = [
    # (intransitive_okuri, transitive_okuri, name)
    ('まる', 'める', '〜まる↔〜める'),
    ('がる', 'げる', '〜がる↔〜げる'),
    ('かる', 'ける', '〜かる↔〜ける'),
    ('れる', 'す', '〜れる↔〜す'),
    ('く', 'ける', '〜く↔〜ける'),
    ('む', 'める', '〜む↔〜める'),
    ('ぶ', 'べる', '〜ぶ↔〜べる'),
    ('る', 'す', '〜る↔〜す'),
    ('く', 'かす', '〜く↔〜かす'),
    ('れる', 'る', '〜れる↔〜る'),
]


def enumerate_transitivity_pairs(kanji_data):
    """Find ALL transitivity pairs across the entire kanji database."""
    # Index by (stem, okuri)
    stem_oku_index = defaultdict(list)
    for k in kanji_data:
        for ku in k['kun_list']:
            if ku['stem'] and ku['okuri']:
                stem_oku_index[(ku['stem'], ku['okuri'])].append({
                    'kanji': k['kanji'], 'radical': k['radical'],
                    'meaning': k['meaning_snip'],
                })

    all_pairs = []
    seen_pairs = set()

    # Method 1: Same kanji has both readings
    for k in kanji_data:
        kuns = k['kun_list']
        for i in range(len(kuns)):
            for j in range(i+1, len(kuns)):
                for pat_intr, pat_tr, pat_name in TRANS_PATTERNS:
                    okuri_i = kuns[i]['okuri']
                    okuri_j = kuns[j]['okuri']
                    if (okuri_i == pat_intr and okuri_j == pat_tr) or \
                       (okuri_i == pat_tr and okuri_j == pat_intr):
                        pair_key = (k['kanji'], pat_name)
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            stem_i = kuns[i]['stem']
                            stem_j = kuns[j]['stem']
                            all_pairs.append({
                                'kanji': k['kanji'],
                                'radical': k['radical'],
                                'pattern': pat_name,
                                'intransitive': f'{stem_i}.{kuns[i]["okuri"]}',
                                'transitive': f'{stem_j}.{kuns[j]["okuri"]}',
                                'stems': (stem_i, stem_j),
                            })

    # Method 2: Different kanji share same stem pattern (e.g., 上がる/上げる)
    # Group stems that appear with both intransitive and transitive okurigana
    for (stem, oku), items in stem_oku_index.items():
        for pat_intr, pat_tr, pat_name in TRANS_PATTERNS:
            if oku == pat_intr:
                # Look for same stem with transitive okurigana
                tr_items = stem_oku_index.get((stem, pat_tr), [])
                if tr_items:
                    for it in items:
                        for tr in tr_items:
                            pair_key = (it['kanji'], tr['kanji'], pat_name)
                            if pair_key not in seen_pairs and it['kanji'] != tr['kanji']:
                                seen_pairs.add(pair_key)
                                all_pairs.append({
                                    'kanji_intr': it['kanji'],
                                    'kanji_tr': tr['kanji'],
                                    'pattern': pat_name,
                                    'intransitive': f'{stem}.{pat_intr}',
                                    'transitive': f'{stem}.{pat_tr}',
                                    'stems': (stem, stem),
                                    'cross_kanji': True,
                                })

    return all_pairs


# ═══════════════════════════════════
# 5. ETYMOLOGICAL WORD FAMILIES
# ═══════════════════════════════════

def find_word_families(kanji_data):
    """Group kanji by underlying Japanese word root families.

    A word family is: kanji that share the same CORE root morpheme
    but with different okurigana (derivational suffixes).

    e.g., あ family: あ.がる, あ.げる, あ.かる, あ.ける, あ.く, あ.かす...
    """
    # Group by first mora + phonetic similarity
    root_groups = defaultdict(lambda: defaultdict(list))

    for k in kanji_data:
        for ku in k['kun_list']:
            stem = ku['stem']
            if not stem or len(stem) < 1: continue
            # Use first 1-2 morae as root identifier
            root = stem[0] if len(stem) == 1 or (len(stem) > 1 and stem[1] not in 'ゃゅょ') else stem[:2]
            # Further group by first mora only for larger families
            root1 = stem[0]
            root_groups[root1][stem].append({
                'kanji': k['kanji'], 'okuri': ku['okuri'],
                'full': ku['full'], 'radical': k['radical'],
            })

    # Find roots with many kanji
    families = {}
    for root1, stem_map in root_groups.items():
        # Collect all unique kanji under this root
        all_kanji = set()
        for stem, items in stem_map.items():
            for it in items:
                all_kanji.add(it['kanji'])

        if len(all_kanji) >= 5:
            # Get all the stems and their kanji
            stem_details = {}
            for stem, items in sorted(stem_map.items()):
                unique_k = list(set(it['kanji'] for it in items))
                if len(unique_k) >= 1:
                    stem_details[stem] = {
                        'kanji_count': len(unique_k),
                        'kanji': sorted(unique_k)[:15],
                        'okurigana_variants': list(set(it['okuri'] for it in items)),
                    }

            families[root1] = {
                'total_kanji': len(all_kanji),
                'total_stems': len(stem_details),
                'stems': stem_details,
                'sample_kanji': sorted(all_kanji)[:20],
            }

    # Sort by size
    return dict(sorted(families.items(), key=lambda x: x[1]['total_kanji'], reverse=True))


# ═══════════════════════════════════
# 6. SAME-RADICAL KUN CLUSTERS
# ═══════════════════════════════════

def enumerate_radical_kun_clusters(kanji_data):
    """Within each radical, group kanji by their kun stem patterns."""
    rad_stem_groups = defaultdict(lambda: defaultdict(list))

    for k in kanji_data:
        if not k['radical']: continue
        for ku in k['kun_list']:
            if ku['stem']:
                rad_stem_groups[k['radical']][ku['stem']].append(k['kanji'])

    # Find radicals where one stem dominates
    clusters = {}
    for rad, stem_map in rad_stem_groups.items():
        total_kanji = len(set(
            k for stems in stem_map.values() for k in stems
        ))
        if total_kanji < 5: continue

        dominant_stems = []
        for stem, kanjis in sorted(stem_map.items(), key=lambda x: len(set(x[1])), reverse=True):
            unique_k = len(set(kanjis))
            if unique_k >= 2:
                dominant_stems.append({
                    'stem': stem,
                    'kanji_count': unique_k,
                    'kanji': sorted(set(kanjis))[:10],
                })

        if dominant_stems:
            clusters[rad] = {
                'total_kanji': total_kanji,
                'stems': dominant_stems[:10],
            }

    return clusters


# ═══════════════════════════════════
# 7. SAME-COMPONENT KUN CLUSTERS
# ═══════════════════════════════════

def enumerate_component_kun_clusters(kanji_data):
    """For each component (構字部件), group kanji by shared kun stems."""
    comp_groups = defaultdict(lambda: defaultdict(list))

    for k in kanji_data:
        if not k['components']: continue
        comps = set(c for c in k['components'] if c != k['kanji'] and len(c) == 1)
        for comp in comps:
            for ku in k['kun_list']:
                if ku['stem']:
                    comp_groups[comp][ku['stem']].append(k['kanji'])

    # Find components with concentrated kun stems
    clusters = {}
    for comp, stem_map in comp_groups.items():
        total = sum(len(set(v)) for v in stem_map.values())
        if total < 5: continue

        dom_stems = []
        for stem, kanjis in sorted(stem_map.items(), key=lambda x: len(set(x[1])), reverse=True):
            uk = len(set(kanjis))
            if uk >= 2:
                dom_stems.append({'stem': stem, 'kanji_count': uk, 'kanji': sorted(set(kanjis))[:8]})

        if dom_stems and dom_stems[0]['kanji_count'] >= 2:
            concentration = dom_stems[0]['kanji_count'] / total if total else 0
            clusters[comp] = {
                'total_kanji': total,
                'top_stems': dom_stems[:5],
                'concentration': round(concentration, 3),
            }

    return clusters


# ═══════════════════════════════════
# 8. FORMAT OUTPUT
# ═══════════════════════════════════

def format_same_kun_md(same_stem, same_full):
    lines = []
    lines.append('# 同训字穷举清单')
    lines.append('')
    lines.append('## 一、同训读词干（相同词干→不同汉字）')
    lines.append('')
    lines.append('> 同一个和语词根，用不同汉字书写来表达不同语义侧面。')
    lines.append('> 这是训读体系中最核心的"一词多字"现象。')
    lines.append('')

    sorted_stems = sorted(same_stem.items(), key=lambda x: len(set(it['kanji'] for it in x[1])), reverse=True)

    for stem, items in sorted_stems:
        unique_kanji = {}
        for it in items:
            k = it['kanji']
            if k not in unique_kanji:
                unique_kanji[k] = it

        if len(unique_kanji) < 3:
            continue

        # Group by okurigana
        by_oku = defaultdict(list)
        for it in unique_kanji.values():
            by_oku[it['okuri']].append(it['kanji'])

        oku_summary = ' / '.join(f"{o}({len(ks)})" for o, ks in sorted(by_oku.items()))

        kanji_list = sorted(unique_kanji.keys())
        # Show first 20, note if more
        display_kanji = kanji_list[:20]
        more = f' ...+{len(kanji_list)-20}字' if len(kanji_list) > 20 else ''

        lines.append(f'### 词根「{stem}」→ {len(kanji_list)}个汉字')
        lines.append(f'送假名变体: {oku_summary}')
        lines.append(f'汉字: {" ".join(display_kanji)}{more}')
        lines.append('')

    # Same FULL kun (stem + okurigana)
    lines.append('---')
    lines.append('')
    lines.append('## 二、完全同训（相同词干+相同送假名→不同汉字）')
    lines.append('')
    lines.append('> 读音完全相同，但用不同汉字区分语义。是最容易混淆的组。')
    lines.append('')

    sorted_full = sorted(same_full.items(), key=lambda x: len(set(it['kanji'] for it in x[1])), reverse=True)

    for full_kun, items in sorted_full:
        unique_k = list(set(it['kanji'] for it in items))
        if len(unique_k) < 2:
            continue

        radicals = Counter(it['radical'] for it in items if it['radical'])
        rad_str = ', '.join(f'{r}({n})' for r,n in radicals.most_common(3))

        lines.append(f'### 「{full_kun}」→ {len(unique_k)}字')
        lines.append(f'主要部首: {rad_str}')
        lines.append(f'汉字: {" ".join(sorted(unique_k))}')

        # Show meaning differentiation
        meanings = []
        for it in items:
            if it['meaning']:
                meanings.append(f"{it['kanji']}={it['meaning'][:40]}")
        if meanings:
            lines.append(f'含义区分: {"; ".join(meanings[:5])}')
        lines.append('')

    return '\n'.join(lines)


def format_word_families_md(families, kanji_data):
    lines = []
    lines.append('# 词源家族：同词根→多汉字派生')
    lines.append('')
    lines.append('> 日语固有词根(和語語根)在汉字书写系统中的展开方式。')
    lines.append('> 同一词根通过添加不同送假名(活用词尾)派生为动词/名词/形容词，')
    lines.append('> 再根据语义侧重点选择不同汉字书写。')
    lines.append('')

    for root, fam in list(families.items())[:60]:
        lines.append(f'## 词根族「{root}」— {fam["total_kanji"]}个汉字, {fam["total_stems"]}个词干变体')
        lines.append('')

        # List all stems and their kanji
        for stem, detail in sorted(fam['stems'].items()):
            oku_variants = detail.get('okurigana_variants', [])
            oku_str = '/'.join(oku_variants[:4]) if oku_variants else ''
            kanji_str = ' '.join(detail['kanji'][:10])
            lines.append(f'- **{stem}**({oku_str}): {kanji_str} ({detail["kanji_count"]}字)')

        lines.append(f'\n代表字: {" ".join(fam["sample_kanji"][:15])}')
        lines.append('')

    return '\n'.join(lines)


def format_trans_pairs_md(all_pairs):
    lines = []
    lines.append('# 自他动词对全量清单')
    lines.append('')
    lines.append(f'共发现 {len(all_pairs)} 对自他动词关系。')
    lines.append('')

    # Group by pattern
    by_pattern = defaultdict(list)
    for p in all_pairs:
        by_pattern[p.get('pattern', 'unknown')].append(p)

    for pattern, pairs in sorted(by_pattern.items()):
        lines.append(f'## {pattern}（{len(pairs)}对）')
        lines.append('')
        lines.append('| 汉字 | 自动词 | 他动词 | 部首 |')
        lines.append('|------|--------|--------|------|')

        for p in pairs[:50]:  # Show up to 50 per pattern
            if 'cross_kanji' in p:
                intr = f'{p["kanji_intr"]}({p["intransitive"]})'
                tr = f'{p["kanji_tr"]}({p["transitive"]})'
                lines.append(f'| {p["kanji_intr"]}↔{p["kanji_tr"]} | {intr} | {tr} | - |')
            else:
                lines.append(f'| {p["kanji"]} | {p["intransitive"]} | {p["transitive"]} | {p.get("radical","")} |')

        if len(pairs) > 50:
            lines.append(f'| ... | +{len(pairs)-50}对省略 | | |')
        lines.append('')

    return '\n'.join(lines)


def format_near_kun_md(near_groups):
    lines = []
    lines.append('# 近训字群（音韵相近的训读词干群）')
    lines.append('')
    lines.append('> 词干之间仅差一个浊音(连浊关系)或一个元音(元音交替关系)的字群。')
    lines.append('> 这些是日语词源学的核心证据，也是记忆关联的天然锚点。')
    lines.append('')

    by_type = defaultdict(list)
    for ng in near_groups:
        by_type[ng['type']].append(ng)

    for ntype, groups in by_type.items():
        type_name = {'rendaku': '连浊关系(清⇔浊)', 'vowel_alt': '元音交替关系'}[ntype]
        lines.append(f'## {type_name}')
        lines.append('')

        for ng in groups[:40]:
            lines.append(f'- **{"⇔".join(ng["stems"])}**: {" ".join(ng["kanji"][:15])} ({ng["count"]}字)')
        lines.append('')

    return '\n'.join(lines)


def format_radical_clusters_md(clusters):
    lines = []
    lines.append('# 部内同训群（同部首内共享训读词干的汉字群）')
    lines.append('')
    lines.append('> 同属一个部首的汉字中，哪些共享相同训读词干？')
    lines.append('> 这揭示了部首内部更细致的语义-读音对应关系。')
    lines.append('')

    sorted_clusters = sorted(clusters.items(), key=lambda x: x[1]['total_kanji'], reverse=True)

    for rad, data in sorted_clusters[:80]:
        lines.append(f'## {rad}部（{data["total_kanji"]}字）')
        lines.append('')
        for stem_info in data['stems'][:5]:
            lines.append(f'- **{stem_info["stem"]}**: {" ".join(stem_info["kanji"])} ({stem_info["kanji_count"]}字)')
        lines.append('')

    return '\n'.join(lines)


def format_component_clusters_md(clusters):
    lines = []
    lines.append('# 部件同训群（同部件汉字共享的训读）')
    lines.append('')
    lines.append('> 含有相同构字部件的汉字，在训读上的集中规律。')
    lines.append('> 集中度 = 该部件下最频词干的汉字数 / 该部件总汉字数')
    lines.append('')

    sorted_clusters = sorted(clusters.items(), key=lambda x: x[1]['concentration'], reverse=True)

    lines.append('| 部件 | 集中度 | 总字数 | 首选词干 | 字数 | 例字 |')
    lines.append('|------|--------|--------|---------|------|------|')

    for comp, data in sorted_clusters[:100]:
        if data['concentration'] >= 0.2:
            top = data['top_stems'][0]
            lines.append(f'| {comp} | {data["concentration"]:.0%} | {data["total_kanji"]} | {top["stem"]} | {top["kanji_count"]} | {" ".join(top["kanji"][:5])} |')

    return '\n'.join(lines)


def format_on_groups_md(same_on):
    lines = []
    lines.append('# 音读同音字群')
    lines.append('')
    lines.append('> 共享同一音读的汉字群。对中国人特别有用——')
    lines.append('> 汉字的音读往往与中文读音相关，同音读字群可以帮助批量记忆。')
    lines.append('')

    sorted_on = sorted(same_on.items(), key=lambda x: len(set(it['kanji'] for it in x[1])), reverse=True)

    for on_reading, items in sorted_on[:80]:
        unique_k = sorted(set(it['kanji'] for it in items))
        if len(unique_k) < 3:
            continue

        radicals = Counter(it['radical'] for it in items if it['radical'])
        rad_str = ', '.join(f'{r}({n})' for r,n in radicals.most_common(5))

        lines.append(f'### 音读「{on_reading}」→ {len(unique_k)}字')
        lines.append(f'部首分布: {rad_str}')
        lines.append(f'汉字: {" ".join(unique_k[:25])}')
        if len(unique_k) > 25:
            lines.append(f'  ...+{len(unique_k)-25}字')

        # Show some example kun readings
        kun_samples = []
        for it in items[:5]:
            if it['kun_list']:
                kun_samples.append(f'{it["kanji"]}({"/".join(it["kun_list"][:2])})')
        if kun_samples:
            lines.append(f'训读例: {"; ".join(kun_samples)}')
        lines.append('')

    return '\n'.join(lines)


def generate_macro_summary(same_stem, families, all_pairs, near_groups):
    """Generate macro patterns from the exhaustive enumeration."""
    lines = []
    lines.append('# 宏观规律总结（从穷举数据中提炼）')
    lines.append('')

    # 1. Most common kun stems
    lines.append('## 1. 最高频训读词干（跨汉字最多的词根）')
    lines.append('')
    sorted_stems = sorted(same_stem.items(), key=lambda x: len(set(it['kanji'] for it in x[1])), reverse=True)
    lines.append('| 词根 | 汉字数 | 代表字 |')
    lines.append('|------|--------|--------|')
    for stem, items in sorted_stems[:30]:
        unique_k = sorted(set(it['kanji'] for it in items))
        lines.append(f'| {stem} | {len(unique_k)} | {" ".join(unique_k[:8])} |')

    lines.append('')
    lines.append('**规律**：日语中最基础的和语词根（か/お/あ/す/は/よ/と/う/な）各自对应50-141个汉字。')
    lines.append('这些词根不是"多音字"——它们是一个和语词根用不同汉字书写来区分语义侧重点。')
    lines.append('')

    # 2. Word family structure
    lines.append('## 2. 词源家族结构')
    lines.append('')
    lines.append(f'共识别 {len(families)} 个词源家族（词根首拍级别）。')
    lines.append('')
    top_families = list(families.items())[:10]
    for root, fam in top_families:
        lines.append(f'- **{root}族**: {fam["total_kanji"]}字, {fam["total_stems"]}种词干变体')
        # Show the most common stems
        top_stems = sorted(fam['stems'].items(), key=lambda x: x[1]['kanji_count'], reverse=True)[:5]
        stem_str = ', '.join(f'{s}({d["kanji_count"]})' for s, d in top_stems)
        lines.append(f'  高频词干: {stem_str}')
    lines.append('')

    # 3. Transitivity patterns
    lines.append('## 3. 自他对系统')
    lines.append('')
    by_pat = defaultdict(list)
    for p in all_pairs:
        by_pat[p.get('pattern', 'unknown')].append(p)
    lines.append('| 模式 | 对数 | 规律说明 |')
    lines.append('|------|------|---------|')
    for pat, pairs in sorted(by_pat.items(), key=lambda x: len(x[1]), reverse=True):
        lines.append(f'| {pat} | {len(pairs)} | |')
    lines.append('')

    # 4. Near-kun summary
    lines.append('## 4. 近训字群（音韵关联）')
    lines.append('')
    lines.append(f'共发现 {len(near_groups)} 组音韵相近的训读词干群。')
    lines.append('其中连浊关系占主导，元音交替关系次之。')
    lines.append('')

    # 5. Key insight
    lines.append('## 5. 核心洞察')
    lines.append('')
    lines.append('1. **训读的本质是一词多字**：不是"一个汉字有多个训读"，而是"一个和语词根用多个汉字书写"')
    lines.append('2. **同训字群的规律**：共享同一训读的汉字群，通过部首差异来区分语义侧重点')
    lines.append('   例如：みる→見(目部=视觉)/観(見部=观赏)/視(見部=注视)/診(言部=诊断)/看(目部=照看)')
    lines.append('3. **近训字群的规律**：连浊(清⇔浊)和元音交替(あ⇔え/お等)是日语词源的两大音韵机制')
    lines.append('   这两大机制导致了"看似不同实则同源"的近训字群')
    lines.append('4. **汉字选择规律**：同一词根选哪个汉字，取决于')
    lines.append('   - 部首(语义场)：手部→动作、水部→液体、心部→情感')
    lines.append('   - 送假名(语法功能)：〜る→五段动词、〜える→一段他动词、〜れる→自动词')
    lines.append('   - 语境搭配(复合词中的位置)')
    lines.append('')

    return '\n'.join(lines)


# ═══════════════════════════════════
# MAIN
# ═══════════════════════════════════

def main():
    t0 = time.time()
    print('=' * 60)
    print('v4: 穷举所有同训字/近训字/词源家族')
    print('=' * 60)

    print('\n[1/6] Loading data...')
    kanji_data = load_all()
    print(f'  {len(kanji_data)} kanji loaded')
    print(f'  {sum(1 for k in kanji_data if k["kun_list"])} have kun')
    print(f'  {sum(1 for k in kanji_data if k["on_list"])} have on')

    print('\n[2/6] Enumerating same-kun groups...')
    same_stem, same_full = enumerate_same_kun(kanji_data)
    print(f'  {len(same_stem)} stem groups with 2+ kanji')
    print(f'  {len(same_full)} full-kun groups with 2+ kanji')

    print('\n[3/6] Finding near-kun groups & transitivity pairs...')
    near_groups = find_near_kun(kanji_data)
    print(f'  {len(near_groups)} near-kun groups')

    all_pairs = enumerate_transitivity_pairs(kanji_data)
    print(f'  {len(all_pairs)} transitivity pairs')

    print('\n[4/6] Building word families & clusters...')
    families = find_word_families(kanji_data)
    print(f'  {len(families)} word families (root level)')

    rad_clusters = enumerate_radical_kun_clusters(kanji_data)
    print(f'  {len(rad_clusters)} radical kun clusters')

    comp_clusters = enumerate_component_kun_clusters(kanji_data)
    print(f'  {len(comp_clusters)} component kun clusters')

    print('\n[5/6] Enumerating same-on groups...')
    same_on = enumerate_same_on(kanji_data)
    print(f'  {len(same_on)} on-reading groups with 3+ kanji')

    print('\n[6/6] Generating output...')

    # Build the complete document
    parts = []
    parts.append('# 训读穷举v4：同训字·近训字·词源家族·逐字清单\n')
    parts.append(f'> 数据：漢字検索V2 46,849字\n')
    parts.append(f'> 生成：{time.strftime("%Y-%m-%d %H:%M")}\n')
    parts.append('\n---\n\n')

    # Part 1: Same-kun groups (THE main deliverable)
    parts.append(format_same_kun_md(same_stem, same_full))
    parts.append('\n---\n\n')

    # Part 2: Word families
    parts.append(format_word_families_md(families, kanji_data))
    parts.append('\n---\n\n')

    # Part 3: Near-kun groups
    parts.append(format_near_kun_md(near_groups))
    parts.append('\n---\n\n')

    # Part 4: Transitivity pairs
    parts.append(format_trans_pairs_md(all_pairs))
    parts.append('\n---\n\n')

    # Part 5: Radical clusters
    parts.append(format_radical_clusters_md(rad_clusters))
    parts.append('\n---\n\n')

    # Part 6: Component clusters
    parts.append(format_component_clusters_md(comp_clusters))
    parts.append('\n---\n\n')

    # Part 7: Same-on groups
    parts.append(format_on_groups_md(same_on))
    parts.append('\n---\n\n')

    # Part 8: Macro summary
    parts.append(generate_macro_summary(same_stem, families, all_pairs, near_groups))

    full_doc = '\n'.join(parts)

    output_path = f'{BASE}/KUNYOMI_EXHAUSTIVE_V4.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_doc)

    # Also save structured data
    json_data = {
        'same_stem_groups': {
            stem: {
                'count': len(set(it['kanji'] for it in items)),
                'kanji': sorted(set(it['kanji'] for it in items)),
                'okurigana_variants': list(set(it['okuri'] for it in items)),
            }
            for stem, items in sorted(same_stem.items(), key=lambda x: len(set(it['kanji'] for it in x[1])), reverse=True)
            if len(set(it['kanji'] for it in items)) >= 3
        },
        'same_full_kun_groups': {
            full: {
                'count': len(set(it['kanji'] for it in items)),
                'kanji': sorted(set(it['kanji'] for it in items)),
            }
            for full, items in sorted(same_full.items(), key=lambda x: len(set(it['kanji'] for it in x[1])), reverse=True)
            if len(set(it['kanji'] for it in items)) >= 2
        },
        'word_families': {
            root: {'total_kanji': fam['total_kanji'], 'total_stems': fam['total_stems'],
                   'sample_kanji': fam['sample_kanji']}
            for root, fam in families.items()
        },
        'transitivity_pairs': all_pairs,
        'near_kun_groups': [
            {'type': ng['type'], 'stems': ng['stems'], 'kanji_count': ng['count'],
             'kanji': ng['kanji'][:20]}
            for ng in near_groups[:200]
        ],
        'same_on_groups': {
            on: {'count': len(set(it['kanji'] for it in items)),
                 'kanji': sorted(set(it['kanji'] for it in items))}
            for on, items in sorted(same_on.items(), key=lambda x: len(set(it['kanji'] for it in x[1])), reverse=True)[:100]
        },
    }

    json_path = f'{BASE}/kunyomi_exhaustive_v4.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # Stats
    wc = len(full_doc.split('\n'))
    print(f'\n{"="*60}')
    print(f'DONE')
    print(f'{"="*60}')
    print(f'Output: {output_path} ({wc} lines)')
    print(f'JSON: {json_path}')
    print(f'Time: {time.time()-t0:.1f}s')
    print(f'\nKey counts:')
    print(f'  Same-stem groups (3+ kanji): {sum(1 for s,items in same_stem.items() if len(set(it["kanji"] for it in items))>=3)}')
    print(f'  Same-full-kun groups (2+ kanji): {len(same_full)}')
    print(f'  Near-kun groups: {len(near_groups)}')
    print(f'  Transitivity pairs: {len(all_pairs)}')
    print(f'  Word families: {len(families)}')
    print(f'  Radical clusters: {len(rad_clusters)}')
    print(f'  Component clusters: {len(comp_clusters)}')
    print(f'  Same-on groups (3+): {len(same_on)}')


if __name__ == '__main__':
    main()
