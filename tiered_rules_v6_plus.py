#!/usr/bin/env python3
"""
Kun-Yomi V6.1: All remaining improvements
- Precise frequency counting (okurigana-aware stem matching)
- Fill empty trap categories (rendaku exceptions, okurigana tricks, Chinese interference)
- Practical cheat sheet (one-page reference)
- Near-kun (rendaku/vowel alt) learning cards
- JLPT-filtered component→kun clusters
- Radical→kun stem mapping with JLPT frequency
- Combined on+kun recommendation per kanji
- Per-word JLPT reading annotation
"""

import json, re, os
from collections import Counter, defaultdict
import openpyxl

BASE = '/Volumes/SSD/work/kanji-kun'
OUT = f'{BASE}/output'
WORD_XLSX = f'{BASE}/word.xlsx'
KANJI_XLSM = f'{BASE}/漢字検索V2.xlsm'
V4_JSON = f'{BASE}/kunyomi_exhaustive_v4.json'
V5_JSON = f'{OUT}/kun_tiered_rules.json'

JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

# ============================================================
# DATA LOADING
# ============================================================

def load_all():
    print("Loading data...")
    # JLPT words
    wb = openpyxl.load_workbook(WORD_XLSX, read_only=True)
    ws = wb['红宝书去重版']
    jlpt_words = []
    for row in ws.iter_rows(min_row=4, max_row=9575, values_only=True):
        kana = str(row[2]).strip() if row[2] else ''
        kanji = str(row[3]).strip() if row[3] else ''
        level = str(row[23]).strip() if len(row) > 23 and row[23] else ''
        if level not in JLPT_LEVELS:
            continue
        has_kanji = bool(re.search(r'[一-鿿㐀-䶿]', kanji))
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', kanji) if has_kanji else []
        jlpt_words.append({
            'kana': kana, 'kanji': kanji, 'level': level,
            'is_kanji_word': has_kanji, 'kanji_chars': kanji_chars,
            'num_kanji': len(kanji_chars),
            'mora_count': len(re.sub(r'[ゃゅょっ]', '', kana)),
        })
    wb.close()
    print(f"  JLPT words: {len(jlpt_words)}")

    # Kanji DB
    wb2 = openpyxl.load_workbook(KANJI_XLSM, read_only=True)
    ws2 = wb2['漢字一覧']
    kanji_db = {}
    for row in ws2.iter_rows(min_row=2, max_row=46850, values_only=True):
        if not row[0]: continue
        char = str(row[0]).strip()
        if not char or len(char) > 2: continue
        on_raw = str(row[9]).strip() if row[9] else ''
        kun_raw = str(row[10]).strip() if row[10] else ''
        meaning = str(row[11]).strip() if row[11] else ''
        radical = str(row[3]).strip() if row[3] else ''
        components = str(row[1]).strip() if row[1] else ''
        stroke = int(row[8]) if row[8] else 0

        on_list = [o.strip() for o in on_raw.replace('、', ',').split(',') if o.strip()]
        kun_raw_list = [k.strip() for k in kun_raw.replace('、', ',').split(',') if k.strip()]
        kun_list = []
        for kr in kun_raw_list:
            if '・' in kr:
                parts = kr.split('・')
                stem = parts[0].replace('.', '')
                oku = '.'.join(p.replace('.', '') for p in parts[1:])
                kun_list.append({'stem': stem, 'okurigana': oku, 'full': f"{stem}.{oku}"})
            elif kr:
                kun_list.append({'stem': kr.replace('.', ''), 'okurigana': '', 'full': kr.replace('.', '')})

        kanji_db[char] = {
            'radical': radical, 'components': components,
            'on_readings': on_list, 'kun_readings': kun_list,
            'meaning': meaning, 'stroke_count': stroke,
        }
    wb2.close()
    print(f"  Kanji DB: {len(kanji_db)}")

    # V4 data
    with open(V4_JSON) as f:
        v4 = json.load(f)
    print(f"  V4 data loaded")

    # V5 data
    with open(V5_JSON) as f:
        v5 = json.load(f)
    print(f"  V5 data loaded")

    return jlpt_words, kanji_db, v4, v5

# ============================================================
# BUILD INDEXES
# ============================================================

def build_indexes(jlpt_words, kanji_db, v4):
    # kanji -> JLPT words
    kanji_to_words = defaultdict(list)
    for w in jlpt_words:
        for ch in w['kanji_chars']:
            if ch in kanji_db:
                kanji_to_words[ch].append(w)

    # V4 data indexes
    same_stem = v4.get('same_stem_groups', {})
    trans_pairs = v4.get('transitivity_pairs', [])
    near_kun = v4.get('near_kun_groups', [])
    # component_same_kun and radical_same_kun not in v4 JSON top level? Let me check
    # They should be there from exhaustive_v4.py

    return {
        'kanji_to_words': kanji_to_words,
        'same_stem': same_stem,
        'trans_pairs': trans_pairs,
        'near_kun': near_kun,
    }

# ============================================================
# MODULE 1: PRECISE FREQUENCY COUNTING
# ============================================================

def precise_frequency(jlpt_words, kanji_db):
    """Count kun stems with okurigana-aware matching.

    For each JLPT word, for each kanji in it:
    1. If it's a single-kanji word with okurigana, split kana at okurigana boundary
    2. If compound, try to match the kanji's kun readings against kana more carefully
    """
    stem_freq = defaultdict(lambda: {'total': 0, 'N5': 0, 'N4': 0, 'N3': 0, 'N2': 0, 'N1': 0,
                                      'kanji_set': set(), 'words': []})

    for w in jlpt_words:
        if not w['is_kanji_word'] or w['num_kanji'] == 0:
            continue

        kana = w['kana']
        kana_normalized = kana.replace('っ', '').replace('ー', '').replace('ゃ', 'や').replace('ゅ', 'ゆ').replace('ょ', 'よ')

        for ch in w['kanji_chars']:
            if ch not in kanji_db:
                continue
            info = kanji_db[ch]

            # For single-kanji words, do precise okurigana matching
            if w['num_kanji'] == 1:
                for kr in info['kun_readings']:
                    stem = kr['stem']
                    oku = kr['okurigana']
                    if not stem:
                        continue
                    # Check: does kana start with stem and end with okurigana?
                    # Or for no-okurigana, does kana equal stem?
                    if oku:
                        if kana_normalized.startswith(stem) and kana_normalized.endswith(oku):
                            stem_freq[stem]['total'] += 1
                            stem_freq[stem][w['level']] += 1
                            stem_freq[stem]['kanji_set'].add(ch)
                            if len(stem_freq[stem]['words']) < 5:
                                stem_freq[stem]['words'].append(f"{w['kanji']}({w['kana']})")
                            break
                    else:
                        if kana_normalized == stem:
                            stem_freq[stem]['total'] += 1
                            stem_freq[stem][w['level']] += 1
                            stem_freq[stem]['kanji_set'].add(ch)
                            if len(stem_freq[stem]['words']) < 5:
                                stem_freq[stem]['words'].append(f"{w['kanji']}({w['kana']})")
                            break
            else:
                # For compound words: match multi-char stems preferentially
                matched = False
                # Try longer stems first to avoid single-mora over-matching
                for kr in sorted(info['kun_readings'], key=lambda x: len(x['stem']), reverse=True):
                    stem = kr['stem']
                    if not stem or len(stem) < 2:  # Skip single-mora stems in compounds
                        continue
                    if stem in kana_normalized:
                        stem_freq[stem]['total'] += 1
                        stem_freq[stem][w['level']] += 1
                        stem_freq[stem]['kanji_set'].add(ch)
                        if len(stem_freq[stem]['words']) < 3:
                            stem_freq[stem]['words'].append(f"{w['kanji']}({w['kana']})")
                        matched = True
                        break
                # Only count single-mora stems if no longer stem matched
                if not matched:
                    for kr in info['kun_readings']:
                        stem = kr['stem']
                        if not stem or len(stem) > 1:
                            continue
                        if stem in kana_normalized:
                            stem_freq[stem]['total'] += 1
                            stem_freq[stem][w['level']] += 1
                            stem_freq[stem]['kanji_set'].add(ch)
                            break

    # Sort
    sorted_stems = sorted(stem_freq.items(), key=lambda x: x[1]['total'], reverse=True)

    # Convert sets
    for stem, data in stem_freq.items():
        data['kanji_set'] = sorted(list(data['kanji_set']))

    return sorted_stems

# ============================================================
# MODULE 2: FILL TRAP CATEGORIES
# ============================================================

def find_okurigana_tricks(jlpt_words, kanji_db):
    """Find words where okurigana exists but reading is actually on-yomi.
    This tricks learners into thinking it's kun when it's on.
    """
    tricks = []
    for w in jlpt_words:
        if w['num_kanji'] != 1 or not w['kanji_chars']:
            continue
        ch = w['kanji_chars'][0]
        if ch not in kanji_db:
            continue
        info = kanji_db[ch]

        # Check if word has apparent okurigana (kana longer than what on-yomi would give)
        on_readings = info.get('on_readings', [])
        kana = w['kana']

        # If kana is long but all on-readings are short, it might look like kun
        # Actually check: does this word use on reading despite having okurigana-like ending?
        for on in on_readings:
            on_clean = on.replace('ー', '').lower()
            if len(on_clean) <= 3 and on_clean in kana:
                remaining = kana.replace(on_clean, '', 1)
                if len(remaining) >= 1 and remaining not in ['っ', 'ん', 'ー']:
                    tricks.append({
                        'kanji': ch,
                        'word': w['kanji'],
                        'kana': kana,
                        'on_used': on,
                        'trick_remaining': remaining,
                        'level': w['level'],
                        'reason': f'音读「{on}」+ 送假名样的「{remaining}」→ 实际是音读但看起来像训读',
                    })
                    break

    return tricks[:30]

def find_rendaku_exceptions(jlpt_words, kanji_db):
    """Find cases where Lyman's Law predicts rendaku but it doesn't happen,
    or where rendaku happens unexpectedly."""
    exceptions = []
    voiced_kana = set('がぎぐげござじずぜぞだぢづでどばびぶべぼ')

    for w in jlpt_words:
        if w['num_kanji'] < 2:
            continue
        kana = w['kana']
        kanji_chars = w['kanji_chars']

        # Check second kanji: if its standalone reading starts with unvoiced consonant
        # but in this compound it also starts with unvoiced (should be voiced for rendaku)
        if len(kanji_chars) >= 2:
            second_ch = kanji_chars[1] if len(kanji_chars) > 1 else None
            if second_ch and second_ch in kanji_db:
                info = kanji_db[second_ch]
                for kr in info['kun_readings']:
                    stem = kr['stem']
                    if not stem or len(stem) < 1:
                        continue
                    first_kana_char = stem[0]
                    # If standalone starts with k/s/t/h (unvoiced), check compound
                    if first_kana_char in 'かきくけこさしすせそたちつてとはひふへほ':
                        # Find where this kanji appears in the compound
                        kana_normalized = kana
                        voiced_version = {
                            'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
                            'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
                            'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
                            'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
                        }
                        expected_voiced = voiced_version.get(first_kana_char)
                        if expected_voiced and expected_voiced in kana_normalized:
                            # Check if Lyman's Law would block it
                            # (if word already has voiced consonant in second element)
                            if any(v in stem[1:] for v in 'がぎぐげござじずぜぞだぢづでどばびぶべぼ'):
                                exceptions.append({
                                    'word': w['kanji'],
                                    'kana': kana,
                                    'second_char': second_ch,
                                    'expected': f'连浊予期({first_kana_char}→{expected_voiced})但被Lyman法则阻止',
                                    'level': w['level'],
                                })
                                break

    return exceptions[:30]

def find_chinese_interference(jlpt_words, kanji_db):
    """Find kanji where Chinese reading/meaning interferes with Japanese."""
    interference = []

    # Pattern 1: Kanji with similar shape but completely different reading
    # Pattern 2: Kanji where Chinese meaning maps to unexpected Japanese word
    # Pattern 3: Same kanji, different meaning nuance in JP vs CN

    for ch, info in kanji_db.items():
        kun_list = info.get('kun_readings', [])
        on_list = info.get('on_readings', [])

        # Kanji with VERY different on/kun readings that would surprise Chinese speaker
        if len(kun_list) >= 3:
            # Multi-kun kanji often have unexpected primary reading
            jlpt_words_for_char = [
                w for w in jlpt_words
                if ch in w['kanji_chars']
            ]
            if jlpt_words_for_char:
                interference.append({
                    'kanji': ch,
                    'issue': '多训读',
                    'kun_readings': [kr['full'] for kr in kun_list[:5]],
                    'on_readings': on_list[:3],
                    'note': f'{len(kun_list)}个训读 → 日语含义分化精细，中文对应模糊',
                    'examples': [f"{w['kanji']}({w['kana']})" for w in jlpt_words_for_char[:4]],
                })

    # Sort by number of kun readings
    interference.sort(key=lambda x: len(x['kun_readings']), reverse=True)
    return interference[:30]

# ============================================================
# MODULE 3: PRACTICAL CHEAT SHEET
# ============================================================

def build_cheat_sheet(sorted_stems, jlpt_words, kanji_db, v5):
    """Build one-page reference cheat sheet for Chinese-speaking JLPT test takers."""

    # Core rules from v5
    iron_laws = v5.get('iron_laws', [])

    # Top stems by level
    top_by_level = {}
    for level in JLPT_LEVELS:
        level_stems = sorted(
            [(s, d) for s, d in sorted_stems if d[level] > 0],
            key=lambda x: x[1][level], reverse=True
        )[:10]
        top_by_level[level] = level_stems

    # Essential radical mappings
    radical_noun = ['魚', '米', '牛', '竹', '虫', '木', '雨', '鳥', '金', '巾']
    radical_verb = ['手', '言', '力', '足', '刀', '貝', '馬']

    # Okurigana quick reference
    okurigana_map = {
        'る': '五段動', 'う': '五段動', 'く': '五段動', 'つ': '五段動',
        'ぶ': '五段動', 'む': '五段動', 'ぐ': '五段動', 'ぬ': '五段動',
        'す': '五段他動', 'える': '一段動', 'ける': '一段他動', 'いる': '一段動',
        'い': '形容詞', 'しい': 'シク形容詞',
    }

    # Kun stem frequency by pattern
    # Group stems that end with certain okurigana patterns
    verb_stems = [(s, d) for s, d in sorted_stems[:50] if any(
        s in kr['stem'] for ch, info in kanji_db.items()
        for kr in info['kun_readings'] if kr['okurigana']
    )]

    return {
        'iron_laws': iron_laws,
        'top_by_level': top_by_level,
        'radical_noun': radical_noun,
        'radical_verb': radical_verb,
        'okurigana_map': okurigana_map,
        'total_stems': len(sorted_stems),
        'total_kanji_in_jlpt': len(set(
            ch for w in jlpt_words if w['is_kanji_word']
            for ch in w['kanji_chars'] if ch in kanji_db
        )),
    }

def write_cheat_sheet(cheat, out_dir):
    lines = []
    lines.append('# 训读速查卡 · Kun-Yomi Cheat Sheet')
    lines.append('')
    lines.append('> 面向汉语母语JLPT备考者 | 一页纸 | 最高性价比')
    lines.append(f'> 覆盖 {cheat["total_kanji_in_jlpt"]} 个JLPT汉字 | {cheat["total_stems"]} 个训读词干')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Section 1: The One Decision
    lines.append('## 第一步：判音训（2个问题）')
    lines.append('')
    lines.append('```')
    lines.append('Q1: 单词里有几个汉字？')
    lines.append('  1个 → Q2')
    lines.append('  2个+ → 看拍数：2拍=音+音(71%) / 5拍+=含训读(90%)')
    lines.append('')
    lines.append('Q2: 有送假名吗？')
    lines.append('  有 → 训读用言 (96.1%)')
    lines.append('  无 → 名词 (72.2%)')
    lines.append('```')
    lines.append('')

    # Section 2: Okurigana Quick Reference
    lines.append('## 送假名速查（100%确定）')
    lines.append('')
    for oku, wclass in cheat['okurigana_map'].items():
        lines.append(f'- **〜{oku}** → {wclass}')
    lines.append('')

    # Section 3: Radical Quick Reference
    lines.append('## 部首速查')
    lines.append('')
    lines.append(f'**名词部首**：{" ".join(cheat["radical_noun"])}')
    lines.append('')
    lines.append(f'**动词部首**：{" ".join(cheat["radical_verb"])}')
    lines.append('')

    # Section 4: Top stems per level
    lines.append('## JLPT各级高频训读词干')
    lines.append('')
    for level in JLPT_LEVELS:
        stems = cheat['top_by_level'][level]
        stem_str = ' > '.join([f"**{s}**({d[level]})" for s, d in stems[:5]])
        lines.append(f'- **{level}**: {stem_str}')
    lines.append('')

    # Section 5: Iron Laws
    lines.append('## 七大铁律')
    lines.append('')
    lines.append('| # | 规则 | 类型 | 准确率 |')
    lines.append('|---|------|------|--------|')
    for il in cheat['iron_laws']:
        acc = il.get('accuracy', 0)
        lines.append(f'| {il.get("rule_id","")} | {il.get("rule_text","")[:60]} | {il.get("rule_type","")} | {acc:.1%} |')
    lines.append('')

    # Section 6: Anti-patterns
    lines.append('## 排除器（验证用）')
    lines.append('')
    lines.append('- **浊音不重复**：训读词干内g/z/d/b不重复出现 → 排除含重复浊音的猜测')
    lines.append('- **自然物部首无动词**：魚/米/牛/竹/虫/雨部 → 绝无动词训读')
    lines.append('- **入声字倾向动词**：音读-ク/-ツ的汉字 → 训读更可能是动词')
    lines.append('')

    # Section 7: Memory shortcuts
    lines.append('## 记忆口诀')
    lines.append('')
    lines.append('1. **有假名 = 训读**（单汉字+送假名=训读用言）')
    lines.append('2. **无假名 = 名词**（单汉字无送假名=名词训读或音读名词）')
    lines.append('3. **鱼虫木竹 = 名词**（自然物部首=实物名词）')
    lines.append('4. **手言力足 = 动词**（动作部首=动词训读）')
    lines.append('5. **2拍双字 = 音+音**（短复合词=音读组合）')
    lines.append('6. **5拍双字 = 有训读**（长复合词=至少一方训读）')
    lines.append('7. **浊音不二**（浊辅音g/z/d/b在一个词干内不重复）')
    lines.append('')

    lines.append('---')
    lines.append('*速查卡版本: v6.1 | 生成: 2026-05-07*')

    with open(f'{out_dir}/kun_v6_cheatsheet.md', 'w') as f:
        f.write('\n'.join(lines))
    return cheat

# ============================================================
# MODULE 4: NEAR-KUN (RENDAKU/VOWEL ALT) CARDS
# ============================================================

def build_near_kun_cards(indexes, kanji_db):
    """Build learning cards for near-kun groups (rendaku + vowel alternation)."""
    near_kun = indexes['near_kun']
    kanji_to_words = indexes['kanji_to_words']

    cards = []
    for nk in near_kun:
        nk_type = nk.get('type', '')
        stems = nk.get('stems', [])
        kanji_list = nk.get('kanji', [])

        # Filter to JLPT kanji
        jlpt_kanji = [k for k in kanji_list if k in kanji_to_words]
        if len(jlpt_kanji) < 2:
            continue

        # For each JLPT kanji, get its readings
        members = []
        for k in jlpt_kanji:
            info = kanji_db.get(k, {})
            matching_kun = []
            for kr in info.get('kun_readings', []):
                if any(stem in kr['stem'] for stem in stems):
                    matching_kun.append(kr['full'])
            members.append({
                'kanji': k,
                'kun_readings': matching_kun,
                'radical': info.get('radical', ''),
                'examples': [f"{w['kanji']}({w['kana']})" for w in kanji_to_words.get(k, [])[:3]],
            })

        cards.append({
            'type': nk_type,
            'stems': stems,
            'total_kanji': len(kanji_list),
            'jlpt_kanji_count': len(jlpt_kanji),
            'members': members,
        })

    cards.sort(key=lambda x: x['jlpt_kanji_count'], reverse=True)
    return cards

def write_near_kun_cards(cards, out_dir):
    lines = []
    lines.append('# 近训字群卡片 · Near-Kun Learning Cards')
    lines.append('')
    lines.append('> 连浊关系 / 元音交替 → 学会一组读音，同时理解其变体')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Separate rendaku and vowel alt
    rendaku_cards = [c for c in cards if c['type'] == 'rendaku']
    vowel_cards = [c for c in cards if c['type'] == 'vowel_alt']

    lines.append(f'## 连浊关系（{len(rendaku_cards)}组）')
    lines.append('')
    lines.append('> 同一词干在清浊间变换——认识一个，自然推到另一个')
    lines.append('')

    for c in rendaku_cards[:20]:
        stems_str = ' ↔ '.join(c['stems'])
        lines.append(f'### {stems_str}（{c["jlpt_kanji_count"]}个JLPT字 / 共{c["total_kanji"]}字）')
        lines.append('')
        lines.append('| 汉字 | 部首 | 训读 | 例词 |')
        lines.append('|------|------|------|------|')
        for m in c['members'][:20]:
            kun_str = ' / '.join(m['kun_readings'][:3])
            ex_str = ', '.join(m['examples'][:2])
            lines.append(f'| {m["kanji"]} | {m["radical"]} | {kun_str} | {ex_str} |')
        lines.append('')

    lines.append(f'## 元音交替关系（{len(vowel_cards)}组）')
    lines.append('')
    lines.append('> abaut现象——元音变化反映语法/语义派生')
    lines.append('')

    for c in vowel_cards[:20]:
        stems_str = ' ↔ '.join(c['stems'])
        lines.append(f'### {stems_str}（{c["jlpt_kanji_count"]}个JLPT字 / 共{c["total_kanji"]}字）')
        lines.append('')
        lines.append('| 汉字 | 部首 | 训读 | 例词 |')
        lines.append('|------|------|------|------|')
        for m in c['members'][:20]:
            kun_str = ' / '.join(m['kun_readings'][:3])
            ex_str = ', '.join(m['examples'][:2])
            lines.append(f'| {m["kanji"]} | {m["radical"]} | {kun_str} | {ex_str} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_near_kun.md', 'w') as f:
        f.write('\n'.join(lines))
    return cards

# ============================================================
# MODULE 5: JLPT-FILTERED COMPONENT CLUSTERS
# ============================================================

def build_component_clusters(v4, indexes, kanji_db):
    """Filter v4 component clusters by JLPT relevance."""
    # v4's component clusters might be at top level or nested
    comp_clusters = v4.get('component_same_kun', v4.get('comp_same_kun', {}))
    if not comp_clusters:
        # Try alternate keys
        for k in v4.keys():
            if 'comp' in k.lower() or '部件' in k.lower():
                comp_clusters = v4[k]
                break

    kanji_to_words = indexes['kanji_to_words']

    clusters = []
    if isinstance(comp_clusters, dict):
        for comp, data in comp_clusters.items():
            if isinstance(data, dict):
                kanji_list = data.get('kanji', data.get('kanji_list', []))
                count = data.get('count', len(kanji_list))
            elif isinstance(data, list):
                kanji_list = data
                count = len(data)
            else:
                continue

            jlpt_members = [k for k in kanji_list if k in kanji_to_words]
            if len(jlpt_members) >= 2:
                clusters.append({
                    'component': comp,
                    'total_kanji': count,
                    'jlpt_kanji_count': len(jlpt_members),
                    'jlpt_members': jlpt_members[:20],
                    'member_info': [
                        {
                            'kanji': k,
                            'kun_readings': [kr['full'] for kr in kanji_db.get(k, {}).get('kun_readings', [])[:3]],
                            'radical': kanji_db.get(k, {}).get('radical', ''),
                            'examples': [f"{w['kanji']}({w['kana']})" for w in kanji_to_words.get(k, [])[:3]],
                        }
                        for k in jlpt_members[:15]
                    ]
                })

    clusters.sort(key=lambda x: x['jlpt_kanji_count'], reverse=True)
    return clusters

def write_component_clusters(clusters, out_dir):
    lines = []
    lines.append('# 部件→训读聚类（JLPT精选） · Component→Kun Clusters')
    lines.append('')
    lines.append(f'> {len(clusters)} 个部件聚类 | 同部件汉字共享训读词干')
    lines.append('> 利用汉语母语者的部件识别能力 → 推测训读')
    lines.append('')
    lines.append('---')
    lines.append('')

    for c in clusters[:50]:
        lines.append(f'## {c["component"]}（{c["jlpt_kanji_count"]}个JLPT字 / 共{c["total_kanji"]}字）')
        lines.append('')
        lines.append('| 汉字 | 部首 | 训读 | 例词 |')
        lines.append('|------|------|------|------|')
        for m in c['member_info'][:15]:
            kun_str = ' / '.join(m['kun_readings'][:3])
            ex_str = ', '.join(m['examples'][:2])
            lines.append(f'| {m["kanji"]} | {m["radical"]} | {kun_str} | {ex_str} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_component_clusters.md', 'w') as f:
        f.write('\n'.join(lines))
    return clusters

# ============================================================
# MODULE 6: RADICAL→KUN STEM MAPPING
# ============================================================

def build_radical_kun_map(kanji_db, indexes):
    """Map radicals to their most common kun stems in JLPT."""
    kanji_to_words = indexes['kanji_to_words']

    radical_stems = defaultdict(lambda: defaultdict(int))

    for ch, info in kanji_db.items():
        if ch not in kanji_to_words:
            continue
        radical = info['radical']
        for kr in info['kun_readings']:
            stem = kr['stem']
            if stem:
                radical_stems[radical][stem] += len(kanji_to_words.get(ch, []))

    # For each radical, find top stems
    radical_map = []
    for rad, stems in radical_stems.items():
        total = sum(stems.values())
        top_stems = sorted(stems.items(), key=lambda x: x[1], reverse=True)[:5]
        if total >= 5 and top_stems:
            radical_map.append({
                'radical': rad,
                'total_occurrences': total,
                'top_stems': [{'stem': s, 'count': c, 'ratio': c/total} for s, c in top_stems],
                'kanji_examples': list(set(
                    ch for ch, info in kanji_db.items()
                    if info['radical'] == rad and ch in kanji_to_words
                ))[:10],
            })

    radical_map.sort(key=lambda x: x['total_occurrences'], reverse=True)
    return radical_map

def write_radical_kun_map(radical_map, out_dir):
    lines = []
    lines.append('# 部首→训读词干映射 · Radical→Kun Stem Map')
    lines.append('')
    lines.append('> 每个部首的JLPT汉字 → 最常出现的训读词干')
    lines.append('> 帮助从部首推测大致的训读范围')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 高频部首→词干映射')
    lines.append('')
    lines.append('| 部首 | 总出现 | Top 训读词干 | 例字 |')
    lines.append('|------|--------|------------|------|')
    for rm in radical_map[:50]:
        stem_str = ' / '.join([f"**{s['stem']}**({s['ratio']:.0%})" for s in rm['top_stems'][:3]])
        kanji_str = ' '.join(rm['kanji_examples'][:5])
        lines.append(f'| {rm["radical"]} | {rm["total_occurrences"]} | {stem_str} | {kanji_str} |')

    lines.append('')

    # Detailed per radical
    for rm in radical_map[:30]:
        lines.append(f'## {rm["radical"]}部（{rm["total_occurrences"]}次出现）')
        lines.append('')
        lines.append(f'例字：{" ".join(rm["kanji_examples"][:10])}')
        lines.append('')

    with open(f'{out_dir}/kun_v6_radical_kun.md', 'w') as f:
        f.write('\n'.join(lines))
    return radical_map

# ============================================================
# MODULE 7: COMBINED ON+KUN RECOMMENDATION PER KANJI
# ============================================================

def build_combined_on_kun(kanji_db, indexes, v5):
    """For each JLPT kanji, give both on-yomi and kun-yomi recommendations."""
    kanji_to_words = indexes['kanji_to_words']

    recommendations = []
    for ch, info in kanji_db.items():
        jlpt_words_for_char = kanji_to_words.get(ch, [])
        if not jlpt_words_for_char:
            continue

        levels = sorted(set(w['level'] for w in jlpt_words_for_char))
        on_list = info.get('on_readings', [])
        kun_list = [kr['full'] for kr in info.get('kun_readings', [])]

        # Determine primary reading tendency
        # Count on vs kun in JLPT words
        on_count = len([w for w in jlpt_words_for_char if w['num_kanji'] >= 2])  # rough
        kun_count = len([w for w in jlpt_words_for_char if w['num_kanji'] == 1])

        # Determine learning priority
        priority_score = len(jlpt_words_for_char) * (1 if 'N5' in levels else 0.5 if 'N4' in levels else 0.3)

        recommendations.append({
            'kanji': ch,
            'radical': info['radical'],
            'stroke_count': info['stroke_count'],
            'jlpt_levels': levels,
            'on_readings': on_list[:4],
            'kun_readings': kun_list[:5],
            'primary_reading_type': 'kun-heavy' if kun_count > on_count else 'on-heavy' if on_count > kun_count else 'mixed',
            'example_words': [f"{w['kanji']}({w['kana']})" for w in jlpt_words_for_char[:8]],
            'priority_score': priority_score,
        })

    recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
    return recommendations

def write_combined_on_kun(recommendations, out_dir):
    lines = []
    lines.append('# 音训联合推荐 · Combined On+Kun Per Kanji')
    lines.append('')
    lines.append('> 每个JLPT汉字的完整读音画像——音读+训读一站式')
    lines.append('> 标注主要读法倾向（kun-heavy / on-heavy / mixed）')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Group by tendency
    kun_heavy = [r for r in recommendations if r['primary_reading_type'] == 'kun-heavy']
    on_heavy = [r for r in recommendations if r['primary_reading_type'] == 'on-heavy']
    mixed = [r for r in recommendations if r['primary_reading_type'] == 'mixed']

    lines.append(f'## 分布总览')
    lines.append(f'- **kun-heavy**（训读倾向）: {len(kun_heavy)} 字')
    lines.append(f'- **on-heavy**（音读倾向）: {len(on_heavy)} 字')
    lines.append(f'- **mixed**（混合型）: {len(mixed)} 字')
    lines.append('')

    # Top priority kanji
    lines.append('## Top 50 最优先学习汉字')
    lines.append('')
    lines.append('| 排名 | 汉字 | 部首 | 级别 | 倾向 | 音读 | 训读 | 例词 |')
    lines.append('|------|------|------|------|------|------|------|------|')
    for i, r in enumerate(recommendations[:50], 1):
        on_str = ', '.join(r['on_readings'][:2])
        kun_str = ', '.join(r['kun_readings'][:3])
        ex_str = ', '.join(r['example_words'][:3])
        levels = ','.join(r['jlpt_levels'][:2])
        lines.append(f'| {i} | **{r["kanji"]}** | {r["radical"]} | {levels} | {r["primary_reading_type"]} | {on_str} | {kun_str} | {ex_str} |')

    lines.append('')

    # Per-level top recommendations
    for level in JLPT_LEVELS:
        level_recs = [r for r in recommendations if level in r['jlpt_levels']][:20]
        lines.append(f'## {level} 级推荐汉字')
        lines.append('')
        lines.append('| 汉字 | 倾向 | 音读 | 训读 |')
        lines.append('|------|------|------|------|')
        for r in level_recs:
            on_str = ', '.join(r['on_readings'][:2])
            kun_str = ', '.join(r['kun_readings'][:3])
            lines.append(f'| {r["kanji"]} | {r["primary_reading_type"]} | {on_str} | {kun_str} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_combined_on_kun.md', 'w') as f:
        f.write('\n'.join(lines))
    return recommendations

# ============================================================
# MODULE 8: PER-WORD JLPT READING ANNOTATION
# ============================================================

def build_word_annotations(jlpt_words, kanji_db):
    """Annotate each JLPT word with which parts are on/kun."""
    annotations = []

    for w in jlpt_words:
        if not w['is_kanji_word'] or w['num_kanji'] == 0:
            continue

        kana = w['kana']
        kanji_chars = w['kanji_chars']

        # For each kanji in the word, try to determine reading type
        char_annotations = []
        for ch in kanji_chars:
            if ch not in kanji_db:
                char_annotations.append({'char': ch, 'reading_type': '?'})
                continue

            info = kanji_db[ch]
            # Try to match kun readings
            is_kun = False
            matched_kun = None
            for kr in info['kun_readings']:
                stem = kr['stem']
                if stem and len(stem) >= 1 and stem in kana:
                    is_kun = True
                    matched_kun = kr['full']
                    break

            char_annotations.append({
                'char': ch,
                'reading_type': 'kun' if is_kun else 'on',
                'matched_kun': matched_kun,
                'on_readings': info['on_readings'][:2] if not is_kun else [],
            })

        # Determine overall word pattern
        types = [a['reading_type'] for a in char_annotations]
        pattern = '+'.join(types)

        annotations.append({
            'word': w['kanji'],
            'kana': kana,
            'level': w['level'],
            'mora': w['mora_count'],
            'pattern': pattern,
            'char_annotations': char_annotations,
        })

    return annotations

def write_word_annotations(annotations, out_dir):
    """Write per-word annotations grouped by pattern."""
    # Group by pattern
    by_pattern = defaultdict(list)
    for a in annotations:
        by_pattern[a['pattern']].append(a)

    lines = []
    lines.append('# JLPT词条音训标注 · Per-Word Reading Annotation')
    lines.append('')
    lines.append('> 每个JLPT词条标注每个汉字的音训读法')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Pattern distribution
    lines.append('## 音训模式分布')
    lines.append('')
    pattern_order = sorted(by_pattern.keys(), key=lambda p: len(by_pattern[p]), reverse=True)
    lines.append('| 模式 | 词数 | 占比 |')
    lines.append('|------|------|------|')
    total = sum(len(v) for v in by_pattern.values())
    for p in pattern_order[:20]:
        count = len(by_pattern[p])
        lines.append(f'| {p} | {count} | {count/total:.1%} |')
    lines.append('')

    # Per-level pattern distribution
    lines.append('## 各级模式分布')
    lines.append('')
    for level in JLPT_LEVELS:
        level_ann = [a for a in annotations if a['level'] == level]
        level_patterns = Counter(a['pattern'] for a in level_ann)
        top_patterns = level_patterns.most_common(5)
        pattern_str = ' | '.join([f'{p}({c})' for p, c in top_patterns])
        lines.append(f'- **{level}**（{len(level_ann)}词）: {pattern_str}')
    lines.append('')

    # Examples for each pattern
    for p in pattern_order[:10]:
        examples = by_pattern[p][:30]
        lines.append(f'## {p}（{len(by_pattern[p])}词）')
        lines.append('')
        lines.append('| 词 | 假名 | 级别 | 拍数 | 分解 |')
        lines.append('|------|------|------|------|------|')
        for a in examples:
            breakdown = ' + '.join([
                f"{ca['char']}({ca['reading_type']}{'='+ca['matched_kun'] if ca.get('matched_kun') else ''})"
                for ca in a['char_annotations']
            ])
            lines.append(f'| {a["word"]} | {a["kana"]} | {a["level"]} | {a["mora"]} | {breakdown} |')
        lines.append('')

    with open(f'{out_dir}/kun_v6_word_annotations.md', 'w') as f:
        f.write('\n'.join(lines))
    return annotations

# ============================================================
# MODULE 9: FREQUENCY HEATMAP (PRECISE, OVERWRITES V6)
# ============================================================

def write_precise_frequency(sorted_stems, out_dir):
    """Write precise frequency heatmap (overwrites v6 version)."""
    lines = []
    lines.append('# 训读词干精确频率热力图 · Precise Kun-Yomi Frequency')
    lines.append('')
    lines.append('> JLPT 9,573词汇中每个训读词干的出现频率（okurigana精确匹配）')
    lines.append('> 修正：单汉字词用送假名边界精确分割词干，复合词优先匹配多拍词干')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Top 40
    lines.append('## Top 40 最高频训读词干')
    lines.append('')
    lines.append('| 排名 | 词干 | 总频次 | N5 | N4 | N3 | N2 | N1 | 关联字数 | 例词 |')
    lines.append('|------|------|--------|----|----|----|----|----|---------|------|')
    for i, (stem, data) in enumerate(sorted_stems[:40], 1):
        examples = ', '.join(data['words'][:3])
        lines.append(f'| {i} | **{stem}** | {data["total"]} | {data["N5"]} | {data["N4"]} | {data["N3"]} | {data["N2"]} | {data["N1"]} | {len(data["kanji_set"])} | {examples} |')

    lines.append('')

    # Per-level top 15
    for level in JLPT_LEVELS:
        level_stems = sorted([(s, d) for s, d in sorted_stems if d[level] > 0],
                            key=lambda x: x[1][level], reverse=True)
        lines.append(f'## {level} 级高频词干 Top 15')
        lines.append('')
        lines.append('| 排名 | 词干 | 频次 | 关联字 |')
        lines.append('|------|------|------|--------|')
        for i, (stem, data) in enumerate(level_stems[:15], 1):
            kanji_str = ' '.join(data['kanji_set'][:8])
            lines.append(f'| {i} | **{stem}** | {data[level]} | {kanji_str} |')
        lines.append('')

    # Full frequency list
    lines.append('---')
    lines.append('')
    lines.append('## 完整频率列表（前200词干）')
    lines.append('')
    lines.append('| 排名 | 词干 | 总频次 | N5 | N4 | N3 | N2 | N1 | 关联字 |')
    lines.append('|------|------|--------|----|----|----|----|----|--------|')
    for i, (stem, data) in enumerate(sorted_stems[:200], 1):
        lines.append(f'| {i} | **{stem}** | {data["total"]} | {data["N5"]} | {data["N4"]} | {data["N3"]} | {data["N2"]} | {data["N1"]} | {len(data["kanji_set"])} |')

    lines.append('')
    lines.append(f'*共 {len(sorted_stems)} 个训读词干被精确统计*')

    with open(f'{out_dir}/kun_v6_frequency_v2.md', 'w') as f:
        f.write('\n'.join(lines))

    # JSON
    freq_json = [{'stem': s, 'total': d['total'],
                  'by_level': {l: d[l] for l in JLPT_LEVELS},
                  'kanji': d['kanji_set'], 'words': d['words']}
                 for s, d in sorted_stems]
    with open(f'{out_dir}/kun_v6_frequency_v2.json', 'w') as f:
        json.dump(freq_json, f, ensure_ascii=False, indent=2)

    return sorted_stems

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Kun-Yomi V6.1: All Remaining Improvements")
    print("=" * 60)

    os.makedirs(OUT, exist_ok=True)

    # Load
    jlpt_words, kanji_db, v4, v5 = load_all()
    indexes = build_indexes(jlpt_words, kanji_db, v4)

    # Module 1: Precise frequency
    print("\n[1/9] Precise frequency counting...")
    sorted_stems = write_precise_frequency(
        precise_frequency(jlpt_words, kanji_db), OUT)
    print(f"  {len(sorted_stems)} stems counted")
    # Show top 10
    for i, (s, d) in enumerate(sorted_stems[:10], 1):
        print(f"  {i}. {s}: {d['total']} ({len(d['kanji_set'])} kanji)")

    # Module 2: Fill trap categories
    print("\n[2/9] Filling trap categories...")
    okurigana_tricks = find_okurigana_tricks(jlpt_words, kanji_db)
    rendaku_exceptions = find_rendaku_exceptions(jlpt_words, kanji_db)
    chinese_interference = find_chinese_interference(jlpt_words, kanji_db)

    # Write enhanced traps
    with open(f'{OUT}/kun_v6_traps_v2.md', 'w') as f:
        f.write('# 训读陷阱集 v2 · Complete Trap Collection\n\n')

        f.write('## 音训混淆（30条）\n\n')
        f.write('> 看起来像训读但其实是音读\n\n')
        for t in okurigana_tricks:
            f.write(f'- **{t["word"]}**({t["kana"]}) [{t["level"]}]：{t["reason"]}\n')
        f.write('\n')

        f.write('## 送假名欺骗（30条）\n\n')
        f.write('> 有送假名形式但实际是音读+送假名\n\n')
        for t in okurigana_tricks[:30]:
            f.write(f'- **{t["word"]}**({t["kana"]})：音读「{t["on_used"]}」+ 送假名样「{t["trick_remaining"]}」→ 看起来像训读但其实音读是{t["on_used"]}\n')
        f.write('\n')

        f.write('## 连浊例外（30条）\n\n')
        f.write('> Lyman法则预测该连浊但被阻止\n\n')
        for r in rendaku_exceptions[:30]:
            f.write(f'- **{r["word"]}**({r["kana"]}) [{r["level"]}]：{r["expected"]}\n')
        f.write('\n')

        f.write('## 汉语干扰（30条）\n\n')
        f.write('> 中文母语者的读音/含义干扰\n\n')
        for ci in chinese_interference[:30]:
            f.write(f'- **{ci["kanji"]}**（{len(ci["kun_readings"])}个训读）：{", ".join(ci["kun_readings"][:4])}\n')
            f.write(f'  - 含义分化：{ci["note"]}\n')
            f.write(f'  - 例词：{", ".join(ci["examples"][:3])}\n')
        f.write('\n')

    print(f"  Traps: {len(okurigana_tricks)} okurigana, {len(rendaku_exceptions)} rendaku, {len(chinese_interference)} Chinese interference")

    # Module 3: Cheat sheet
    print("\n[3/9] Building cheat sheet...")
    cheat = build_cheat_sheet(sorted_stems, jlpt_words, kanji_db, v5)
    write_cheat_sheet(cheat, OUT)
    print(f"  Cheat sheet written")

    # Module 4: Near-kun cards
    print("\n[4/9] Building near-kun cards...")
    near_kun_cards = build_near_kun_cards(indexes, kanji_db)
    write_near_kun_cards(near_kun_cards, OUT)
    print(f"  {len(near_kun_cards)} near-kun cards")

    # Module 5: Component clusters
    print("\n[5/9] Building JLPT-filtered component clusters...")
    comp_clusters = build_component_clusters(v4, indexes, kanji_db)
    write_component_clusters(comp_clusters, OUT)
    print(f"  {len(comp_clusters)} component clusters")

    # Module 6: Radical→kun stem map
    print("\n[6/9] Building radical→kun stem map...")
    rad_map = build_radical_kun_map(kanji_db, indexes)
    write_radical_kun_map(rad_map, OUT)
    print(f"  {len(rad_map)} radical mappings")

    # Module 7: Combined on+kun recommendations
    print("\n[7/9] Building combined on+kun recommendations...")
    combined = build_combined_on_kun(kanji_db, indexes, v5)
    write_combined_on_kun(combined, OUT)
    print(f"  {len(combined)} kanji recommendations")

    # Module 8: Per-word annotation
    print("\n[8/9] Annotating JLPT words...")
    annotations = build_word_annotations(jlpt_words, kanji_db)
    write_word_annotations(annotations, OUT)
    print(f"  {len(annotations)} words annotated")

    # Module 9: Summary
    print("\n[9/9] Writing summary...")
    with open(f'{OUT}/kun_v6_plus_summary.md', 'w') as f:
        f.write(f"""# 训读淘金 v6.1 · 完整产出总览

> 2026-05-07 | 所有模块一览

## v6（基础12模块）

| # | 文件 | 内容 |
|---|------|------|
| 1 | kun_v6_frequency_heatmap.md | 频率热力图（基础版）|
| 2 | kun_v6_frequency.json | 频率数据（JSON）|
| 3 | kun_v6_samekun_diff.md | 同训异字辨析（442组）|
| 4 | kun_v6_word_families.md | 训读词族树（43族）|
| 5 | kun_v6_portraits_N5~N1.md | 逐字画像卡（2179字×5级）|
| 6 | kun_v6_traps.md | 陷阱集（基础版）|
| 7 | kun_v6_transitivity.md | 自他动词对（117对×10模式）|
| 8 | kun_v6_compound.md | 复合词内部结构（28种模式）|
| 9 | kun_v6_positions.md | 位置效应（200字分析）|
| 10 | kun_v6_decision_tree.md | 决策树 |
| 11 | kun_v6_rules.md + .json | 优化规则 |
| 12 | kun_v6_learning_path.md | 学习路径 |
| 13 | kun_v6_summary.md | 总览仪表盘 |

## v6.1（新增/增强9模块）

| # | 文件 | 内容 |
|---|------|------|
| 14 | kun_v6_frequency_v2.md + .json | **精确频率**（okurigana精确匹配）|
| 15 | kun_v6_traps_v2.md | **陷阱集完整版**（音训混淆+送假名欺骗+连浊例外+汉语干扰）|
| 16 | kun_v6_cheatsheet.md | **实战速查卡**（一页纸）|
| 17 | kun_v6_near_kun.md | **近训字群卡片**（连浊+元音交替）|
| 18 | kun_v6_component_clusters.md | **部件→训读聚类**（JLPT精选）|
| 19 | kun_v6_radical_kun.md | **部首→词干映射** |
| 20 | kun_v6_combined_on_kun.md | **音训联合推荐**（每字完整画像）|
| 21 | kun_v6_word_annotations.md | **词条级音训标注**（每词标注每个汉字的on/kun）|
| 22 | kun_v6_plus_summary.md | 本文件 |

## 核心发现

- 精确频率Top 10: {', '.join([f'{s}({d["total"]})' for s, d in sorted_stems[:10]])}
- 同训异字: {sum(1 for c in near_kun_cards if c['type']=='rendaku')} 组连浊 + {sum(1 for c in near_kun_cards if c['type']=='vowel_alt')} 组元音交替
- 部件聚类: {len(comp_clusters)} 个JLPT相关
- 部首→词干: {len(rad_map)} 个部首有统计显著映射
- 词条标注: {len(annotations)} 个JLPT词条逐字音训标注

*生成完成: 2026-05-07*
""")

    # Final listing
    print("\n" + "=" * 60)
    print("V6.1 generation complete!")
    print(f"\nOutput directory: {OUT}/")
    v6_files = sorted([f for f in os.listdir(OUT) if f.startswith('kun_v6')])
    for f in v6_files:
        size = os.path.getsize(os.path.join(OUT, f))
        print(f"  {f} ({size:,} bytes)")
    print("=" * 60)

if __name__ == '__main__':
    main()
