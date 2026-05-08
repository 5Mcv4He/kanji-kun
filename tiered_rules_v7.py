#!/usr/bin/env python3
"""
Kun-Yomi V7: Active Learning System
====================================
8 modules transforming reference data into learning materials:
1. 30-Day Study Sequence (specific daily word lists)
2. Auto-Generated Training Exercises (4 quiz types)
3. Confusion Risk Scoring (same-kun danger ranking)
4. Mnemonic Generation (Chinese homophone memory aids)
5. Mermaid Knowledge Graphs (visual relationship maps)
6. Scene-Anchored Rules (daily situation templates)
7. Error Pattern Prediction (computed confusion risks)
8. Unified On+Kun Lookup (per-kanji combined prediction)
"""

import json, re, os, random
from collections import Counter, defaultdict
import openpyxl

BASE = '/Volumes/SSD/work/kanji-kun'
OUT = f'{BASE}/output'
WORD_XLSX = f'{BASE}/word.xlsx'
KANJI_XLSM = f'{BASE}/漢字検索V2.xlsm'
V4_JSON = f'{BASE}/kunyomi_exhaustive_v4.json'

JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

# ============================================================
# DATA LOADING
# ============================================================

def load_data():
    print("Loading...")
    # JLPT words
    wb = openpyxl.load_workbook(WORD_XLSX, read_only=True)
    ws = wb['红宝书去重版']
    jlpt_words = []
    for row in ws.iter_rows(min_row=4, max_row=9575, values_only=True):
        kana = str(row[2]).strip() if row[2] else ''
        kanji = str(row[3]).strip() if row[3] else ''
        level = str(row[23]).strip() if len(row) > 23 and row[23] else ''
        if level not in JLPT_LEVELS: continue
        has_kanji = bool(re.search(r'[一-鿿㐀-䶿]', kanji))
        kanji_chars = re.findall(r'[一-鿿㐀-䶿]', kanji) if has_kanji else []
        jlpt_words.append({
            'kana': kana, 'kanji': kanji, 'level': level,
            'kanji_chars': kanji_chars, 'num_kanji': len(kanji_chars),
            'mora': len(re.sub(r'[ゃゅょっ]', '', kana)),
            'is_kun': None,  # Will be determined
        })
    wb.close()

    # Kanji DB
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

        kanji_db[ch] = {
            'radical': radical, 'components': components,
            'on_readings': on_list, 'kun_readings': kun_list,
            'meaning': meaning, 'stroke_count': stroke,
        }
    wb2.close()

    # V4
    with open(V4_JSON) as f:
        v4 = json.load(f)

    print(f"  Words: {len(jlpt_words)}, Kanji: {len(kanji_db)}")
    return jlpt_words, kanji_db, v4

# ============================================================
# BUILD INDEXES
# ============================================================

def build_indexes(jlpt_words, kanji_db, v4):
    # Kanji → words
    k2w = defaultdict(list)
    for w in jlpt_words:
        for ch in w['kanji_chars']:
            if ch in kanji_db:
                k2w[ch].append(w)

    # Stem frequency (precise)
    stem_freq = defaultdict(lambda: {'total': 0, 'by_level': defaultdict(int), 'kanji': set(), 'words': []})
    for w in jlpt_words:
        if w['num_kanji'] == 0: continue
        kana = w['kana'].replace('っ','').replace('ー','').replace('ゃ','や').replace('ゅ','ゆ').replace('ょ','よ')
        for ch in w['kanji_chars']:
            if ch not in kanji_db: continue
            info = kanji_db[ch]
            if w['num_kanji'] == 1:
                for kr in info['kun_readings']:
                    stem, oku = kr['stem'], kr['okurigana']
                    if not stem: continue
                    if oku:
                        if kana.startswith(stem) and kana.endswith(oku):
                            stem_freq[stem]['total'] += 1
                            stem_freq[stem]['by_level'][w['level']] += 1
                            stem_freq[stem]['kanji'].add(ch)
                            if len(stem_freq[stem]['words']) < 5:
                                stem_freq[stem]['words'].append(f"{w['kanji']}({w['kana']})")
                            break
                    else:
                        if kana == stem:
                            stem_freq[stem]['total'] += 1
                            stem_freq[stem]['by_level'][w['level']] += 1
                            stem_freq[stem]['kanji'].add(ch)
                            if len(stem_freq[stem]['words']) < 5:
                                stem_freq[stem]['words'].append(f"{w['kanji']}({w['kana']})")
                            break
            else:
                for kr in sorted(info['kun_readings'], key=lambda x: len(x['stem']), reverse=True):
                    stem = kr['stem']
                    if stem and len(stem) >= 2 and stem in kana:
                        stem_freq[stem]['total'] += 1
                        stem_freq[stem]['by_level'][w['level']] += 1
                        stem_freq[stem]['kanji'].add(ch)
                        break
                else:
                    for kr in info['kun_readings']:
                        stem = kr['stem']
                        if stem and len(stem) == 1 and stem in kana:
                            stem_freq[stem]['total'] += 1
                            stem_freq[stem]['by_level'][w['level']] += 1
                            stem_freq[stem]['kanji'].add(ch)
                            break

    sorted_stems = sorted(stem_freq.items(), key=lambda x: x[1]['total'], reverse=True)
    for s, d in stem_freq.items():
        d['kanji'] = sorted(list(d['kanji']))

    # Same-kun groups from v4, filtered to JLPT
    same_stem = v4.get('same_stem_groups', {})
    same_kun_jlpt = {}
    for stem, gdata in same_stem.items():
        jlpt_kanji = [k for k in gdata.get('kanji', []) if k in k2w]
        if len(jlpt_kanji) >= 2:
            same_kun_jlpt[stem] = {
                'total': gdata.get('count', len(gdata.get('kanji', []))),
                'jlpt_kanji': jlpt_kanji,
                'variants': gdata.get('okurigana_variants', []),
            }

    # Categorize each JLPT word: on-heavy, kun-heavy, or mixed
    for w in jlpt_words:
        if w['num_kanji'] == 0: continue
        kana = w['kana']
        kun_match_count = 0
        for ch in w['kanji_chars']:
            if ch in kanji_db:
                for kr in kanji_db[ch]['kun_readings']:
                    if kr['stem'] and kr['stem'] in kana:
                        kun_match_count += 1
                        break
        if w['num_kanji'] == 1:
            w['is_kun'] = kun_match_count > 0
        # For multi-kanji, determine pattern
        if w['num_kanji'] >= 2:
            k_chars = w['kanji_chars']
            types = []
            for ch in k_chars:
                if ch in kanji_db:
                    is_kun_char = any(
                        kr['stem'] and kr['stem'] in kana
                        for kr in kanji_db[ch]['kun_readings']
                    )
                    types.append('kun' if is_kun_char else 'on')
                else:
                    types.append('?')
            w['reading_pattern'] = '+'.join(types)

    # Mark single-kanji words
    for w in jlpt_words:
        if w['num_kanji'] == 1 and w['kanji_chars']:
            ch = w['kanji_chars'][0]
            if ch in kanji_db:
                kana = w['kana']
                w['is_kun'] = any(
                    kr['stem'] and kr['stem'] in kana
                    for kr in kanji_db[ch]['kun_readings']
                )

    return {
        'k2w': k2w, 'stem_freq': stem_freq, 'sorted_stems': sorted_stems,
        'same_kun_jlpt': same_kun_jlpt,
    }

# ============================================================
# MODULE 1: 30-DAY LEARNING SEQUENCE
# ============================================================

def build_30day_plan(jlpt_words, kanji_db, indexes):
    """Generate concrete 30-day study plan with specific words."""
    sorted_stems = indexes['sorted_stems']
    k2w = indexes['k2w']
    same_kun = indexes['same_kun_jlpt']

    plan = []
    used_words = set()

    # Priority: words that are: single kanji + kun reading + N5/N4 first
    priority_words = sorted(
        [w for w in jlpt_words if w['num_kanji'] == 1 and w.get('is_kun')],
        key=lambda w: (JLPT_LEVELS.index(w['level']), -w['mora'])
    )

    # Organize days
    # Days 1-5: Top 10 highest-frequency stems (one stem per half day)
    # Days 6-10: Okurigana system (verb conjugation patterns)
    # Days 11-15: Radical-based word class recognition
    # Days 16-20: Same-kun differentiation (most confusing groups)
    # Days 21-25: Compound word patterns
    # Days 26-30: Review + traps + transitivity

    day = 0

    # Phase 1: Top stems (Days 1-6)
    top_stems = sorted_stems[:12]  # Top 12 stems
    phase1 = []
    for stem, sdata in top_stems:
        stem_words = []
        for ch in sdata['kanji'][:8]:
            for w in k2w.get(ch, []):
                if w['kanji'] not in used_words and w['num_kanji'] == 1:
                    stem_words.append(w)
                    used_words.add(w['kanji'])
                    if len(stem_words) >= 4:
                        break
            if len(stem_words) >= 4:
                break
        if stem_words:
            phase1.append({'stem': stem, 'freq': sdata['total'], 'words': stem_words})

    # Assign to days
    for i in range(0, len(phase1), 2):
        day += 1
        batch = phase1[i:i+2]
        if batch:
            plan.append({
                'day': day, 'phase': '高频词干',
                'title': f'词干: {" + ".join(b["stem"] for b in batch)}',
                'items': [w for b in batch for w in b['words']],
                'tip': f'注意同训异字——同一个词干可以对应多个汉字',
                'exercise': '用每个词造一个句子',
            })

    # Phase 2: Okurigana system (Days 7-10)
    oku_patterns = [
        {'oku': '〜る/う/く/つ/ぶ/む/ぐ/ぬ', 'class': '五段動詞', 'tip': '五段动词占所有动词的约70%'},
        {'oku': '〜す', 'class': '五段他動詞', 'tip': '〜す几乎都是他动词（需要宾语）'},
        {'oku': '〜える/ける/いる', 'class': '一段動詞', 'tip': '一段动词的送假名总含え/い段+る'},
        {'oku': '〜い/しい', 'class': '形容詞', 'tip': '〜い结尾=形容词（イ形容词）'},
    ]
    for op in oku_patterns:
        day += 1
        # Find example words
        examples = []
        for w in priority_words:
            if w['kanji'] not in used_words:
                kana = w['kana']
                # Check okurigana ending
                for o in op['oku'].replace('〜','').split('/'):
                    if kana.endswith(o):
                        examples.append(w)
                        used_words.add(w['kanji'])
                        break
                if len(examples) >= 8:
                    break
        plan.append({
            'day': day, 'phase': '送假名体系',
            'title': f'{op["oku"]} → {op["class"]}',
            'items': examples,
            'tip': op['tip'],
            'exercise': f'找出更多{op["oku"]}结尾的词并判断词类',
        })

    # Phase 3: Radical recognition (Days 11-15)
    rad_groups = [
        {'radicals': '魚/米/牛/竹/虫/木/雨', 'predicts': '名詞', 'memo': '自然物=实物名词'},
        {'radicals': '手/言/力/足/刀', 'predicts': '動詞', 'memo': '动作部首=动词'},
        {'radicals': '金/巾/宀/广', 'predicts': '名詞', 'memo': '人造物/建筑=名词'},
        {'radicals': '心/口/日/糸', 'predicts': '混合', 'memo': '心理/口部/时间=动词名词混合'},
        {'radicals': '水/火/土/石', 'predicts': '混合', 'memo': '自然元素=动作+物质名混合'},
    ]
    for rg in rad_groups:
        day += 1
        rad_list = rg['radicals'].split('/')
        examples = []
        for ch, info in kanji_db.items():
            if info['radical'] in rad_list and ch in k2w:
                for w in k2w[ch]:
                    if w['num_kanji'] == 1 and w['kanji'] not in used_words:
                        examples.append(w)
                        used_words.add(w['kanji'])
                        break
                if len(examples) >= 10:
                    break
        plan.append({
            'day': day, 'phase': '部首识别',
            'title': f'部首: {rg["radicals"]} → {rg["predicts"]} ({rg["memo"]})',
            'items': examples[:10],
            'tip': rg['memo'],
            'exercise': '遮盖假名，只看汉字和部首，预判词类',
        })

    # Phase 4: Same-kun differentiation (Days 16-21)
    # Pick the most JLPT-relevant same-kun groups
    high_impact_kun = sorted(same_kun.items(),
                             key=lambda x: len(x[1]['jlpt_kanji']), reverse=True)[:12]
    for i in range(0, len(high_impact_kun), 2):
        day += 1
        batch = high_impact_kun[i:i+2]
        for stem, sdata in batch:
            stem_words = []
            for ch in sdata['jlpt_kanji'][:6]:
                for w in k2w.get(ch, []):
                    if w['kanji'] not in used_words:
                        stem_words.append(w)
                        used_words.add(w['kanji'])
                        break
            plan.append({
                'day': day, 'phase': '同训辨析',
                'title': f'词干「{stem}」({len(sdata["jlpt_kanji"])}个JLPT字)',
                'items': stem_words[:8],
                'tip': f'同一读音→不同汉字→不同语义侧面。JLPT汉字: {" ".join(sdata["jlpt_kanji"][:8])}',
                'exercise': '每个汉字的核心含义差别是什么？',
            })
            if len(stem_words) >= 8:
                day += 1  # One stem can take a full day

    # Phase 5: Compound patterns (Days 22-25)
    compound_days = [
        {'pattern': 'on+on', 'title': '音+音复合词', 'tip': '2拍=几乎确定音+音'},
        {'pattern': 'kun+kun', 'title': '训+训复合词', 'tip': '动词连用形+动词连用形→复合名词极常见'},
        {'pattern': 'kun+on / on+kun', 'title': '混合型复合词', 'tip': 'kun+on比on+kun常见2倍'},
        {'pattern': '5拍+长词', 'title': '长复合词中的训读', 'tip': '5拍以上复合词90%含训读'},
    ]
    for cd in compound_days:
        day += 1
        examples = []
        for w in jlpt_words:
            if w['num_kanji'] >= 2 and w['kanji'] not in used_words:
                pat = w.get('reading_pattern', '')
                if cd['pattern'] == 'on+on' and pat == 'on+on':
                    examples.append(w)
                elif cd['pattern'] == 'kun+kun' and pat == 'kun+kun':
                    examples.append(w)
                elif cd['pattern'] == 'kun+on / on+kun' and ('kun+on' in pat or 'on+kun' in pat):
                    examples.append(w)
                elif cd['pattern'] == '5拍+长词' and w['mora'] >= 5:
                    examples.append(w)
                if len(examples) >= 10:
                    break
        plan.append({
            'day': day, 'phase': '复合词',
            'title': cd['title'],
            'items': examples[:10],
            'tip': cd['tip'],
            'exercise': '标注每个汉字的音训读法',
        })

    # Phase 6: Review + Traps (Days 26-30)
    trap_exercises = [
        {'trap': '音训混淆', 'memo': '短音读→看起来像训读', 'example': '愛(あい)=音读不是训读'},
        {'trap': '送假名欺骗', 'memo': '有送假名≠一定是训读', 'example': '信じる=音读シン+じる'},
        {'trap': '多训读字', 'memo': '3+训读的汉字→优先记最常见的', 'example': '生=いきる/うまれる/なま/はえる/き'},
        {'trap': '浊音验证', 'memo': '训读词干内浊音不重复', 'example': 'が+ざ=❌ 不可能'},
        {'trap': '自然物=名词', 'memo': '魚/米/牛/竹/虫/雨→绝无动词', 'example': '魚部179字中212训读→0个五段动词'},
    ]
    for te in trap_exercises:
        day += 1
        plan.append({
            'day': day, 'phase': '陷阱与复习',
            'title': te['trap'],
            'items': [],  # Review previous words
            'tip': te['memo'],
            'exercise': f'例: {te["example"]}。找更多类似例子',
        })

    return plan

def write_30day_plan(plan, out_dir):
    lines = []
    lines.append('# 30天训读学习计划 · 30-Day Kun-Yomi Study Plan')
    lines.append('')
    lines.append('> 每天30-45分钟 | 由高频到低频 | 主动练习')
    lines.append(f'> {len(plan)} 天课程')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Phase overview
    phases = {}
    for p in plan:
        ph = p['phase']
        if ph not in phases:
            phases[ph] = {'count': 0, 'days': []}
        phases[ph]['count'] += 1
        phases[ph]['days'].append(p['day'])

    lines.append('## 六阶段总览')
    lines.append('')
    for i, (ph, info) in enumerate(phases.items(), 1):
        day_range = f"Day {info['days'][0]}-{info['days'][-1]}" if len(info['days']) > 1 else f"Day {info['days'][0]}"
        lines.append(f'{i}. **{ph}**（{day_range}, {info["count"]}天）')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Daily lessons
    for p in plan:
        lines.append(f'## Day {p["day"]} — {p["title"]}')
        lines.append('')
        lines.append(f'**阶段**: {p["phase"]}  |  **要点**: {p["tip"]}')
        lines.append('')
        if p['items']:
            lines.append('| # | 汉字 | 假名 | 级别 |')
            lines.append('|---|------|------|------|')
            for i, w in enumerate(p['items'][:12], 1):
                lines.append(f'| {i} | {w["kanji"]} | {w["kana"]} | {w["level"]} |')
        lines.append('')
        lines.append(f'**今日练习**: {p["exercise"]}')
        lines.append('')
        lines.append('---')
        lines.append('')

    lines.append('')
    lines.append('*生成: 2026-05-07 | tiered_rules_v7.py*')

    with open(f'{out_dir}/kun_v7_30day_plan.md', 'w') as f:
        f.write('\n'.join(lines))
    return plan

# ============================================================
# MODULE 2: AUTO-GENERATED TRAINING EXERCISES
# ============================================================

def build_exercises(jlpt_words, kanji_db, indexes):
    """Generate 4 types of training exercises."""
    random.seed(42)
    exercises = {'type1_on_kun': [], 'type2_same_kun': [], 'type3_okurigana': [], 'type4_traps': []}

    # Type 1: On/Kun judgment
    single_kanji = [w for w in jlpt_words if w['num_kanji'] == 1]
    random.shuffle(single_kanji)
    for w in single_kanji[:50]:
        is_kun = w.get('is_kun', False)
        exercises['type1_on_kun'].append({
            'question': f'「{w["kanji"]}」({w["kana"]}) 是音读还是训读？',
            'answer': '训读' if is_kun else '音读',
            'level': w['level'],
            'hint': '单汉字+送假名=训读' if is_kun and len(w['kana']) > 2 else '短音=可能音读',
        })

    # Type 2: Same-kun character selection
    same_kun = indexes['same_kun_jlpt']
    for stem, sdata in same_kun.items():
        if len(sdata['jlpt_kanji']) < 3:
            continue
        # Find JLPT words for these kanji
        k2w = indexes['k2w']
        words_for_group = []
        for ch in sdata['jlpt_kanji'][:6]:
            for w in k2w.get(ch, []):
                if w['num_kanji'] == 1:
                    words_for_group.append(w)
                    break
        if len(words_for_group) >= 2:
            # Pick one as answer, rest as distractors
            exercises['type2_same_kun'].append({
                'stem': stem,
                'question': f'训读词干「{stem}」可以对应哪个汉字？',
                'options': [w['kanji'] for w in words_for_group[:4]],
                'answer': words_for_group[0]['kanji'],
                'explanation': f'「{stem}」可对应: {" ".join(sdata["jlpt_kanji"][:6])}',
                'level': words_for_group[0]['level'],
            })
        if len(exercises['type2_same_kun']) >= 30:
            break

    # Type 3: Okurigana prediction
    oku_exercises = [
        {'kana': 'たべる', 'kanji': '食', 'question': '「食べる」的送假名是？', 'answer': 'べる', 'class': '一段動詞'},
        {'kana': 'あるく', 'kanji': '歩', 'question': '「歩く」的送假名是？', 'answer': 'く', 'class': '五段動詞'},
        {'kana': 'うつくしい', 'kanji': '美', 'question': '「美しい」的送假名是？', 'answer': 'しい', 'class': 'シク形容詞'},
        {'kana': 'およぐ', 'kanji': '泳', 'question': '「泳ぐ」的送假名是？', 'answer': 'ぐ', 'class': '五段動詞'},
        {'kana': 'まなぶ', 'kanji': '学', 'question': '「学ぶ」的送假名是？', 'answer': 'ぶ', 'class': '五段動詞'},
        {'kana': 'しぬ', 'kanji': '死', 'question': '「死ぬ」的送假名是？', 'answer': 'ぬ', 'class': '五段動詞'},
        {'kana': 'たおれる', 'kanji': '倒', 'question': '「倒れる」的送假名是？', 'answer': 'れる', 'class': '一段動詞'},
        {'kana': 'あたえる', 'kanji': '与', 'question': '「与える」的送假名是？', 'answer': 'える', 'class': '一段動詞'},
        {'kana': 'かんがえる', 'kanji': '考', 'question': '「考える」的送假名是？', 'answer': 'える', 'class': '一段動詞'},
        {'kana': 'おきる', 'kanji': '起', 'question': '「起きる」的送假名是？', 'answer': 'きる', 'class': '一段動詞'},
    ]
    exercises['type3_okurigana'] = oku_exercises

    # Generate more from data
    for w in single_kanji[:40]:
        if w.get('is_kun') and len(w['kanji_chars']) == 1:
            ch = w['kanji_chars'][0]
            if ch in kanji_db:
                for kr in kanji_db[ch]['kun_readings']:
                    if kr['okurigana'] and kr['stem'] in w['kana']:
                        exercises['type3_okurigana'].append({
                            'kana': w['kana'], 'kanji': ch,
                            'question': f'「{ch}」(読み: {w["kana"]}) 的送假名部分是什么？',
                            'answer': kr['okurigana'],
                            'class': ('一段' if kr['okurigana'] in ['える','ける','いる','れる'] else
                                     '五段' if kr['okurigana'] in ['る','う','く','つ','ぶ','む','ぐ','ぬ','す'] else
                                     '形容詞' if kr['okurigana'] in ['い','しい'] else '名詞'),
                            'level': w['level'],
                        })
                        break
        if len(exercises['type3_okurigana']) >= 30:
            break

    # Type 4: Trap exercises
    trap_exercises = [
        {'question': '「受付」读 じゅふ 还是 うけつけ？', 'answer': 'うけつけ', 'trap': '2拍=音+音 规则不适用（实际5拍）'},
        {'question': '「愛」是音读还是训读？', 'answer': '音读（あい=呉音）', 'trap': '看起来像训读的短音读'},
        {'question': '「生」有几个训读？', 'answer': '5个以上(いきる/うまれる/なま/はえる/き)', 'trap': '多训读字'},
        {'question': '「魚部」的字会产生动词训读吗？', 'answer': '不会——魚部179字中0个五段动词', 'trap': '自然物部首无动词'},
        {'question': '浊音が和ざ能出现在同一个训读词干里吗？', 'answer': '不能——浊音不重复铁律(99.5%)', 'trap': '浊音规则'},
        {'question': '「お巡りさん」中「巡り」是动词吗？', 'answer': '不是——有送假名但是名词', 'trap': '送假名欺骗'},
        {'question': '「一日」可以读哪些音？', 'answer': 'ついたち(训)/いちにち(音)/ひとひ(训)', 'trap': '同形异读'},
        {'question': '复合词中，词头偏音读还是训读？', 'answer': '偏音读', 'trap': '位置效应'},
    ]
    exercises['type4_traps'] = trap_exercises

    return exercises

def write_exercises(exercises, out_dir):
    lines = []
    lines.append('# 训读训练题集 · Kun-Yomi Training Exercises')
    lines.append('')
    lines.append('> 4种题型 | 主动提取 > 被动阅读 | 自动生成')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Type 1
    lines.append('## 题型一：音训判定（50题）')
    lines.append('')
    lines.append('> 判断以下单词是音读还是训读')
    lines.append('')
    lines.append('<details><summary>点击展开题目</summary>')
    lines.append('')
    for i, e in enumerate(exercises['type1_on_kun'][:50], 1):
        lines.append(f'{i}. {e["question"]}  <br/>**答案**: {e["answer"]}（{e["hint"]}）  ')
    lines.append('')
    lines.append('</details>')
    lines.append('')

    # Type 2
    lines.append('## 题型二：同训选字（30题）')
    lines.append('')
    lines.append('> 同一训读词干对应不同汉字——选正确的')
    lines.append('')
    lines.append('<details><summary>点击展开题目</summary>')
    lines.append('')
    for i, e in enumerate(exercises['type2_same_kun'][:30], 1):
        opts = ' / '.join(e['options'])
        lines.append(f'{i}. {e["question"]} ({opts})  <br/>**答案**: {e["answer"]} — {e["explanation"]}  ')
    lines.append('')
    lines.append('</details>')
    lines.append('')

    # Type 3
    lines.append('## 题型三：送假名识别（30题）')
    lines.append('')
    lines.append('> 识别送假名部分并判断词类')
    lines.append('')
    lines.append('<details><summary>点击展开题目</summary>')
    lines.append('')
    for i, e in enumerate(exercises['type3_okurigana'][:30], 1):
        lines.append(f'{i}. {e["question"]}  <br/>**答案**: {e["answer"]}（{e["class"]}）  ')
    lines.append('')
    lines.append('</details>')
    lines.append('')

    # Type 4
    lines.append('## 题型四：陷阱识别（8题）')
    lines.append('')
    lines.append('> 专门针对汉语母语者容易踩的坑')
    lines.append('')
    for i, e in enumerate(exercises['type4_traps'], 1):
        lines.append(f'{i}. {e["question"]}  <br/>**答案**: {e["answer"]}  ')
    lines.append('')

    lines.append('---')
    lines.append('*生成: 2026-05-07 | tiered_rules_v7.py*')

    with open(f'{out_dir}/kun_v7_exercises.md', 'w') as f:
        f.write('\n'.join(lines))
    return exercises

# ============================================================
# MODULE 3: CONFUSION RISK SCORING
# ============================================================

def build_confusion_scores(kanji_db, indexes):
    """Score same-kun groups by how likely learners are to confuse them."""
    same_kun = indexes['same_kun_jlpt']
    k2w = indexes['k2w']

    scored_groups = []
    for stem, sdata in same_kun.items():
        jlpt_kanji = sdata['jlpt_kanji']
        if len(jlpt_kanji) < 2:
            continue

        # For each pair in the group, compute confusion risk
        pairs = []
        for i, ch1 in enumerate(jlpt_kanji):
            for ch2 in jlpt_kanji[i+1:]:
                info1 = kanji_db.get(ch1, {})
                info2 = kanji_db.get(ch2, {})

                # Risk factors:
                risk = 0
                reasons = []

                # Same radical? +20
                if info1.get('radical') == info2.get('radical'):
                    risk += 20
                    reasons.append('同部首')

                # Similar meaning? (crude: check first 3 chars of meaning)
                m1 = info1.get('meaning', '')[:30]
                m2 = info2.get('meaning', '')[:30]
                if m1 and m2 and any(c in m2 for c in m1 if c not in '◆ '):
                    risk += 15
                    reasons.append('含义相近')

                # Both have same okurigana pattern? +25
                kun1 = [kr['okurigana'] for kr in info1.get('kun_readings', []) if kr['stem'] == stem]
                kun2 = [kr['okurigana'] for kr in info2.get('kun_readings', []) if kr['stem'] == stem]
                if kun1 == kun2 and kun1:
                    risk += 25
                    reasons.append('送假名完全相同')

                # Similar JLPT level? +10
                levels1 = set(w['level'] for w in k2w.get(ch1, []))
                levels2 = set(w['level'] for w in k2w.get(ch2, []))
                if levels1 & levels2:
                    risk += 10
                    reasons.append(f'同级({"".join(sorted(levels1 & levels2))})')

                # Both common kanji? +15
                freq1 = len(k2w.get(ch1, []))
                freq2 = len(k2w.get(ch2, []))
                if freq1 >= 5 and freq2 >= 5:
                    risk += 15
                    reasons.append('均为高频字')

                pairs.append({
                    'kanji1': ch1, 'kanji2': ch2,
                    'risk_score': risk,
                    'risk_level': '🔴 极高' if risk >= 50 else '🟠 高' if risk >= 35 else '🟡 中' if risk >= 20 else '🟢 低',
                    'reasons': reasons,
                })

        # Group-level score = average of top pairs
        pairs.sort(key=lambda x: x['risk_score'], reverse=True)
        avg_risk = sum(p['risk_score'] for p in pairs[:5]) / min(5, len(pairs)) if pairs else 0

        scored_groups.append({
            'stem': stem,
            'jlpt_count': len(jlpt_kanji),
            'total_count': sdata['total'],
            'avg_risk': avg_risk,
            'top_confusion_pairs': pairs[:10],
        })

    scored_groups.sort(key=lambda x: x['avg_risk'], reverse=True)
    return scored_groups

def write_confusion_scores(scored_groups, out_dir):
    lines = []
    lines.append('# 同训混淆风险排行 · Confusion Risk Ranking')
    lines.append('')
    lines.append('> 预测哪些同训组最容易记混——优先推送对比学习')
    lines.append('> 风险分 = 同部首+20 + 含义近+15 + 送假名同+25 + 同级+10 + 高频+15')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 最高混淆风险 Top 20')
    lines.append('')
    for i, sg in enumerate(scored_groups[:20], 1):
        risk_emoji = '🔴' if sg['avg_risk'] >= 50 else '🟠' if sg['avg_risk'] >= 35 else '🟡'
        lines.append(f'### {i}. 词干「{sg["stem"]}」{risk_emoji} 风险={sg["avg_risk"]:.0f}（{sg["jlpt_count"]}个JLPT字）')
        lines.append('')
        lines.append('| 混淆对 | 风险 | 原因 |')
        lines.append('|--------|------|------|')
        for p in sg['top_confusion_pairs'][:8]:
            lines.append(f'| {p["kanji1"]} ↔ {p["kanji2"]} | {p["risk_level"]} ({p["risk_score"]}) | {", ".join(p["reasons"])} |')
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## 完整混淆风险列表')
    lines.append('')
    lines.append('| 排名 | 词干 | JLPT字数 | 平均风险 | 最高风险对 |')
    lines.append('|------|------|---------|---------|----------|')
    for i, sg in enumerate(scored_groups, 1):
        top_pair = sg['top_confusion_pairs'][0] if sg['top_confusion_pairs'] else None
        top_str = f'{top_pair["kanji1"]}↔{top_pair["kanji2"]}({top_pair["risk_score"]})' if top_pair else '-'
        lines.append(f'| {i} | **{sg["stem"]}** | {sg["jlpt_count"]} | {sg["avg_risk"]:.0f} | {top_str} |')

    lines.append('')
    lines.append('*生成: 2026-05-07 | tiered_rules_v7.py*')

    with open(f'{out_dir}/kun_v7_confusion_risk.md', 'w') as f:
        f.write('\n'.join(lines))
    return scored_groups

# ============================================================
# MODULE 4: MNEMONIC GENERATION
# ============================================================

# Japanese mora → closest Chinese pinyin mapping
MORA_TO_PINYIN = {
    'あ': 'a', 'い': 'yi', 'う': 'wu', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'xi', 'す': 'si', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'qi', 'つ': 'ci', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'you', 'よ': 'yo',
    'ら': 'la', 'り': 'li', 'る': 'lu', 'れ': 'lei', 'ろ': 'lo',
    'わ': 'wa', 'を': 'wo', 'ん': 'n',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': 'ji', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': 'ji', 'づ': 'zu', 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'bei', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pei', 'ぽ': 'po',
    'きゃ': 'kia', 'きゅ': 'kiu', 'きょ': 'kio',
    'しゃ': 'xia', 'しゅ': 'xiu', 'しょ': 'xio',
    'ちゃ': 'qia', 'ちゅ': 'qiu', 'ちょ': 'qio',
    'にゃ': 'nia', 'にゅ': 'niu', 'にょ': 'nio',
    'ひゃ': 'hia', 'ひゅ': 'hiu', 'ひょ': 'hio',
    'みゃ': 'mia', 'みゅ': 'miu', 'みょ': 'mio',
    'りゃ': 'lia', 'りゅ': 'liu', 'りょ': 'lio',
    'ぎゃ': 'gia', 'ぎゅ': 'giu', 'ぎょ': 'gio',
    'じゃ': 'jia', 'じゅ': 'jiu', 'じょ': 'jio',
    'びゃ': 'bia', 'びゅ': 'biu', 'びょ': 'bio',
    'ぴゃ': 'pia', 'ぴゅ': 'piu', 'ぴょ': 'pio',
}

# Chinese characters commonly used in mnemonics (sorted by simplicity)
MNEMONIC_CHARS = {
    'a': '阿', 'yi': '一', 'wu': '乌', 'e': '俄', 'o': '哦',
    'ka': '卡', 'ki': '奇', 'ku': '哭', 'ke': '可', 'ko': '扣',
    'sa': '撒', 'xi': '西', 'si': '斯', 'se': '塞', 'so': '索',
    'ta': '他', 'qi': '七', 'ci': '次', 'te': '特', 'to': '托',
    'na': '那', 'ni': '尼', 'nu': '努', 'ne': '呢', 'no': '诺',
    'ha': '哈', 'hi': '嘻', 'fu': '夫', 'he': '喝', 'ho': '吼',
    'ma': '马', 'mi': '米', 'mu': '木', 'me': '么', 'mo': '莫',
    'ya': '鸭', 'you': '由', 'yo': '哟',
    'ra': '拉', 'li': '里', 'lu': '路', 'lei': '雷', 'lo': '洛',
    'wa': '哇', 'wo': '我', 'n': '嗯',
}

def kana_to_pinyin(kana_str):
    """Convert kana string to approximate pinyin syllables."""
    # Remove small chars for clean parsing
    result = []
    i = 0
    while i < len(kana_str):
        matched = False
        # Try 2-char match first (small kana combos)
        for length in [3, 2, 1]:
            if i + length <= len(kana_str):
                chunk = kana_str[i:i+length]
                if chunk in MORA_TO_PINYIN:
                    result.append(MORA_TO_PINYIN[chunk])
                    i += length
                    matched = True
                    break
        if not matched:
            i += 1
    return result

def generate_mnemonic(kana_str, kanji_meaning_hint=''):
    """Generate a memorable Chinese phrase for a Japanese kun reading."""
    pinyin_list = kana_to_pinyin(kana_str)
    if not pinyin_list:
        return None

    chars = []
    for py in pinyin_list:
        if py in MNEMONIC_CHARS:
            chars.append(MNEMONIC_CHARS[py])
        else:
            chars.append(py)

    mnemonic = ''.join(chars)
    kana_repr = '.'.join([m for m in pinyin_list])

    return {
        'kana': kana_str,
        'pinyin': kana_repr,
        'mnemonic_chars': mnemonic,
        'example_phrase': f'"{mnemonic}" → 谐音"{kana_str}"',
    }

def build_mnemonics(kanji_db, indexes):
    """Generate mnemonics for top kun stems."""
    sorted_stems = indexes['sorted_stems']
    mnemonics = []

    for stem, sdata in sorted_stems[:100]:
        mn = generate_mnemonic(stem)
        if mn:
            mn['stem'] = stem
            mn['frequency'] = sdata['total']
            mn['kanji_examples'] = sdata['kanji'][:8]
            mn['words'] = sdata.get('words', [])[:3]
            mnemonics.append(mn)

    return mnemonics

def write_mnemonics(mnemonics, out_dir):
    lines = []
    lines.append('# 训读谐音记忆法 · Kun-Yomi Mnemonic Aids')
    lines.append('')
    lines.append('> 利用汉语母语音系为日语音节赋予语义锚点')
    lines.append('> 中文谐音→日语发音——用于辅助记忆，不是精确音译')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 五十音谐音映射表')
    lines.append('')
    lines.append('> 每个日语音节→最接近的中文谐音字')
    lines.append('')
    # Group by consonant
    groups = [('あ行', 'あいうえお'), ('か行', 'かきくけこ'), ('さ行', 'さしすせそ'),
              ('た行', 'たちつてと'), ('な行', 'なにぬねの'), ('は行', 'はひふへほ'),
              ('ま行', 'まみむめも'), ('や行', 'やゆよ'), ('ら行', 'らりるれろ'),
              ('わ行', 'わをん'), ('が行', 'がぎぐげご'), ('ざ行', 'ざじずぜぞ'),
              ('だ行', 'だぢづでど'), ('ば行', 'ばびぶべぼ'), ('ぱ行', 'ぱぴぷぺぽ')]
    for gname, chars in groups:
        mapping = []
        for c in list(chars):
            py = MORA_TO_PINYIN.get(c, '?')
            hz = MNEMONIC_CHARS.get(py, '?')
            mapping.append(f'{c}→{hz}({py})')
        lines.append(f'- **{gname}**: {" / ".join(mapping)}')
    lines.append('')

    lines.append('---')
    lines.append('')

    lines.append('## Top 50 高频词干谐音助记')
    lines.append('')
    for i, mn in enumerate(mnemonics[:50], 1):
        lines.append(f'### {i}. {mn["stem"]}（频次: {mn["frequency"]}）')
        lines.append(f'- **谐音**: 「{mn["mnemonic_chars"]}」({mn["pinyin"]}) → 读作「{mn["kana"]}」')
        lines.append(f'- **关联字**: {" ".join(mn["kanji_examples"][:8])}')
        if mn.get('words'):
            lines.append(f'- **例词**: {", ".join(mn["words"][:3])}')
        lines.append('')

    lines.append('*生成: 2026-05-07 | tiered_rules_v7.py*')

    with open(f'{out_dir}/kun_v7_mnemonics.md', 'w') as f:
        f.write('\n'.join(lines))
    return mnemonics

# ============================================================
# MODULE 5: MERMAID KNOWLEDGE GRAPHS
# ============================================================

def build_mermaid_graphs(kanji_db, indexes, v4):
    """Generate mermaid diagram source for key knowledge graphs."""
    sorted_stems = indexes['sorted_stems']
    same_kun = indexes['same_kun_jlpt']
    k2w = indexes['k2w']

    graphs = {}

    # Graph 1: Decision tree
    graphs['decision_tree'] = '''```mermaid
graph TD
    START[看到汉字词] --> Q1{几个汉字?}
    Q1 -->|1个| Q2{有送假名?}
    Q1 -->|2个+| Q3{几拍?}
    Q2 -->|有| KUN1[训读用言 96.1%]
    Q2 -->|无| NOUN[名词 72.2%]
    Q3 -->|2拍| ON_ON[音+音 71.2%]
    Q3 -->|5拍+| KUN_MIX[含训读 90.4%]
    Q3 -->|3-4拍| MIXED[混合 看具体情况]
    KUN1 --> OKU{送假名尾音?}
    OKU -->|る/う/く/つ/ぶ/む/ぐ/ぬ| GODAN[五段動詞 100%]
    OKU -->|す| TADOU[五段他動詞 100%]
    OKU -->|える/ける/いる| ICHIDAN[一段動詞 100%]
    OKU -->|い/しい| KEIYOU[形容詞 100%]
```'''

    # Graph 2: Top same-kun network (most connected stems)
    top_stems_for_graph = sorted_stems[:8]
    graph2_lines = ['```mermaid', 'graph LR']
    for stem, sdata in top_stems_for_graph:
        kanji_str = ' '.join(sdata['kanji'][:5])
        graph2_lines.append(f'    {stem}[{stem} / {sdata["total"]}次]')
        graph2_lines.append(f'    {stem} --> "{kanji_str}"')
    graph2_lines.append('```')
    graphs['top_stems'] = '\n'.join(graph2_lines)

    # Graph 3: Word family tree for the biggest family
    word_families = v4.get('word_families', {})
    biggest_fam = max(word_families.items(), key=lambda x: x[1].get('total_kanji', 0)) if word_families else None
    if biggest_fam:
        mora, fam_data = biggest_fam
        sample = fam_data.get('sample_kanji', [])[:25]
        # Filter to JLPT
        jlpt_sample = [k for k in sample if k in k2w][:15]
        graph3_lines = ['```mermaid', f'graph TD', f'    {mora}[{mora}族 / {fam_data.get("total_kanji",0)}字 / {fam_data.get("total_stems",0)}词干]']
        for k in jlpt_sample:
            info = kanji_db.get(k, {})
            kuns = [kr['full'] for kr in info.get('kun_readings', [])[:2]]
            kun_str = ' / '.join(kuns) if kuns else ''
            graph3_lines.append(f'    {mora} --> {k}[{k} / {kun_str}]')
        graph3_lines.append('```')
        graphs['word_family'] = '\n'.join(graph3_lines)

    # Graph 4: Transitivity pattern overview
    trans = v4.get('transitivity_pairs', [])
    # Group by pattern
    patterns = defaultdict(list)
    for tp in trans:
        patterns[tp.get('pattern', 'other')].append(tp)
    graph4_lines = ['```mermaid', 'graph LR']
    top_patterns = sorted(patterns.items(), key=lambda x: len(x[1]), reverse=True)[:6]
    for pat, pairs in top_patterns:
        graph4_lines.append(f'    {pat}[{pat} / {len(pairs)}对]')
    graph4_lines.append('```')
    graphs['transitivity'] = '\n'.join(graph4_lines)

    # Graph 5: Radical → word class
    graph5_lines = ['```mermaid', 'graph LR']
    graph5_lines.append('    部首 --> 名词[名词部首]')
    graph5_lines.append('    部首 --> 动词[动词部首]')
    graph5_lines.append('    名词 --> N1[魚/米/牛/竹/虫/木/雨 100%]')
    graph5_lines.append('    名词 --> N2[金/巾/宀/广 >80%]')
    graph5_lines.append('    动词 --> V1[手/言/力/足/刀/貝 >60%]')
    graph5_lines.append('    动词 --> V2[馬/廴 70%+]')
    graph5_lines.append('```')
    graphs['radicals'] = '\n'.join(graph5_lines)

    return graphs

def write_mermaid_graphs(graphs, out_dir):
    lines = []
    lines.append('# 训读知识图谱可视化 · Kun-Yomi Knowledge Graphs')
    lines.append('')
    lines.append('> Mermaid 图表——可视化记忆 > 文字表格')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 1. 训读判定决策树')
    lines.append('')
    lines.append(graphs['decision_tree'])
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 2. 最高频训读词干网络')
    lines.append('')
    lines.append(graphs['top_stems'])
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 3. 最大词源家族')
    lines.append('')
    lines.append(graphs.get('word_family', '*(暂无)*'))
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 4. 自他动词模式分布')
    lines.append('')
    lines.append(graphs['transitivity'])
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 5. 部首→词类预判')
    lines.append('')
    lines.append(graphs['radicals'])
    lines.append('')
    lines.append('*Mermaid图表可在支持Mermaid的Markdown阅读器中渲染*')

    with open(f'{out_dir}/kun_v7_mermaid_graphs.md', 'w') as f:
        f.write('\n'.join(lines))
    return graphs

# ============================================================
# MODULE 6: SCENE-ANCHORED RULES
# ============================================================

def build_scene_rules():
    """Template-based scene anchoring for key rules."""
    scenes = [
        {
            'rule': '送假名→训读用言',
            'accuracy': '96.1%',
            'scenes': [
                {'place': '便利店的收银台', 'when': '结账时', 'example': '「お預かりします」(あずかる=五段動) —— 有送假名"る"→训读动词'},
                {'place': '餐厅', 'when': '点菜时', 'example': '「注文をお決めになりましたか」(きめる=一段他動) —— 有送假名"める"→训读动词'},
                {'place': '电车广播', 'when': '到站时', 'example': '「お降りの方は...」(おりる=一段動) —— 有送假名"りる"→训读动词'},
            ]
        },
        {
            'rule': '2拍复合词→音+音',
            'accuracy': '71.2%',
            'scenes': [
                {'place': '考试', 'when': '读题时', 'example': '「試験」(しけん=2拍=音+音) —— 短复合词大概率音读'},
                {'place': '新闻', 'when': '看标题时', 'example': '「経済」(けいざい=4拍=有训读可能? 不，经济=音+音) —— 注意4拍例外'},
            ]
        },
        {
            'rule': '自然物部首→名词',
            'accuracy': '95%+',
            'scenes': [
                {'place': '超市', 'when': '看食品标签', 'example': '「鰻」(うなぎ=魚部)「鮭」(さけ=魚部) —— 鱼部100%名词'},
                {'place': '公园', 'when': '看植物牌', 'example': '「桜」(さくら=木部)「梅」(うめ=木部) —— 木部>80%名词'},
            ]
        },
        {
            'rule': '浊音不重复铁律',
            'accuracy': '99.5%',
            'scenes': [
                {'place': '任何地方', 'when': '猜读音时', 'example': '如果猜"がざ"→错。同一个训读词干内g/z/d/b绝不重复。就像中文不会说"嘎扎"是一个字。'},
            ]
        },
        {
            'rule': '手部→动词',
            'accuracy': '74.9%',
            'scenes': [
                {'place': '厨房', 'when': '看菜谱', 'example': '「掻き混ぜる」(かく=手部)「捩る」(よじる=手部)「捻る」(ひねる=手部) —— 全是动词'},
            ]
        },
    ]
    return scenes

def write_scene_rules(scenes, out_dir):
    lines = []
    lines.append('# 场景锚定规则 · Scene-Anchored Rules')
    lines.append('')
    lines.append('> 每条规则绑一个你会在生活中遇到的场景')
    lines.append('> 场景提取记忆 > 抽象规则记忆')
    lines.append('')
    lines.append('---')
    lines.append('')

    for s in scenes:
        lines.append(f'## {s["rule"]}（准确率 {s["accuracy"]}）')
        lines.append('')
        for scene in s['scenes']:
            lines.append(f'### 📍 {scene["place"]} — {scene["when"]}')
            lines.append(f'> {scene["example"]}')
            lines.append('')
        lines.append('---')
        lines.append('')

    lines.append('*生成: 2026-05-07 | tiered_rules_v7.py*')

    with open(f'{out_dir}/kun_v7_scene_rules.md', 'w') as f:
        f.write('\n'.join(lines))
    return scenes

# ============================================================
# MODULE 7: ERROR PATTERN PREDICTION
# ============================================================

def build_error_prediction(kanji_db, indexes):
    """Predict what errors learners will make based on data patterns."""
    k2w = indexes['k2w']

    errors = {
        'on_kun_misread': [],       # Will misread on as kun or vice versa
        'kun_confusion_pairs': [],  # Will confuse two different kun readings
        'radical_misleading': [],   # Radical suggests wrong word class
        'length_deception': [],     # Word length deceives on/kun judgment
    }

    # on/kun misread risk: short on readings
    for ch, info in kanji_db.items():
        if ch not in k2w: continue
        on_list = info.get('on_readings', [])
        kun_list = info.get('kun_readings', [])
        for on in on_list:
            on_clean = on.replace('ー','').replace('ッ','つ')
            if len(on_clean) <= 2:
                words = [f"{w['kanji']}({w['kana']})" for w in k2w[ch][:3]]
                errors['on_kun_misread'].append({
                    'kanji': ch,
                    'risk': f'音读「{on}」太短→可能被误判为训读',
                    'examples': words,
                })
                break

    errors['on_kun_misread'].sort(key=lambda x: len(x['examples']), reverse=True)
    errors['on_kun_misread'] = errors['on_kun_misread'][:30]

    # Kun confusion pairs: same radical + different stems + similar meaning
    radical_groups = defaultdict(list)
    for ch, info in kanji_db.items():
        if ch in k2w and info.get('kun_readings'):
            radical_groups[info['radical']].append(ch)

    for rad, chars in radical_groups.items():
        if len(chars) < 2: continue
        for i, ch1 in enumerate(chars):
            for ch2 in chars[i+1:]:
                info1 = kanji_db.get(ch1, {})
                info2 = kanji_db.get(ch2, {})
                stems1 = {kr['stem'] for kr in info1.get('kun_readings', [])}
                stems2 = {kr['stem'] for kr in info2.get('kun_readings', [])}
                # Different stems but same radical = confusion risk
                if stems1 and stems2 and not (stems1 & stems2):
                    shared_stems = stems1 & stems2
                    if not shared_stems:
                        errors['kun_confusion_pairs'].append({
                            'pair': f'{ch1} ↔ {ch2}',
                            'radical': rad,
                            'stems1': list(stems1)[:3],
                            'stems2': list(stems2)[:3],
                            'risk': '同部首+不同训读→容易互相干扰',
                        })
        if len(errors['kun_confusion_pairs']) >= 50:
            break

    # Radical misleading: radical suggests wrong class
    misleading = [
        {'radical': '手', 'expects': '动词', 'but': '手紙(てがみ)=名词', 'note': '手部也有名词'},
        {'radical': '心', 'expects': '心理动词', 'but': '心(こころ)=名词', 'note': '心部名词也不少'},
        {'radical': '日', 'expects': '时间', 'but': '日(ひ)=名词/量词', 'note': '日部名词占多数'},
        {'radical': '口', 'expects': '口部动作', 'but': '口(くち)=名词', 'note': '口部49.6%动词/37.6%名词→混合'},
    ]
    errors['radical_misleading'] = misleading

    # Length deception
    length_deceptions = [
        {'pattern': '3拍双字词', 'risk': '恰好3拍→on+on和kun混在一起无法判断', 'examples': '受付(うけつけ=kun+kun) vs 医者(いしゃ=on+on)'},
        {'pattern': '4拍双字词', 'risk': '4拍也无法确定', 'examples': '学生(がくせい=on+on) vs 受付中(うけつけちゅう)'},
    ]
    errors['length_deception'] = length_deceptions

    return errors

def write_error_prediction(errors, out_dir):
    lines = []
    lines.append('# 错误模式预测 · Predicted Error Patterns')
    lines.append('')
    lines.append('> 从数据中推导学习者最可能犯的错误——不等真实数据，先预测')
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 1. 音训误判高风险字（30字）')
    lines.append('')
    for e in errors['on_kun_misread'][:20]:
        lines.append(f'- **{e["kanji"]}**：{e["risk"]}  (例: {", ".join(e["examples"][:3])})')
    lines.append('')

    lines.append('## 2. 同部首异训读混淆对')
    lines.append('')
    for e in errors['kun_confusion_pairs'][:20]:
        lines.append(f'- **{e["pair"]}**（{e["radical"]}部）：{", ".join(e["stems1"])} vs {", ".join(e["stems2"])} — {e["risk"]}')
    lines.append('')

    lines.append('## 3. 部首误导')
    lines.append('')
    for e in errors['radical_misleading']:
        lines.append(f'- **{e["radical"]}部** → 你以为都是{e["expects"]} → 但{e["but"]}——{e["note"]}')
    lines.append('')

    lines.append('## 4. 词长欺骗')
    lines.append('')
    for e in errors['length_deception']:
        lines.append(f'- **{e["pattern"]}**: {e["risk"]}（{e["examples"]}）')
    lines.append('')

    lines.append('*生成: 2026-05-07 | tiered_rules_v7.py*')

    with open(f'{out_dir}/kun_v7_error_prediction.md', 'w') as f:
        f.write('\n'.join(lines))
    return errors

# ============================================================
# MODULE 8: UNIFIED ON+KUN LOOKUP
# ============================================================

def build_unified_lookup(kanji_db, indexes):
    """Per-kanji combined on+kun prediction card."""
    k2w = indexes['k2w']

    lookup = {}
    for ch, info in kanji_db.items():
        if ch not in k2w: continue

        on_list = info.get('on_readings', [])
        kun_list = info.get('kun_readings', [])
        words = k2w[ch]
        levels = sorted(set(w['level'] for w in words))

        # Determine primary reading type
        solo_words = [w for w in words if w['num_kanji'] == 1]
        compound_words = [w for w in words if w['num_kanji'] >= 2]

        kun_solo = sum(1 for w in solo_words if w.get('is_kun'))
        on_solo = len(solo_words) - kun_solo

        # Find which on/kun rules would fire for this kanji
        applicable_rules = []

        # Rule: okurigana check
        if kun_list:
            for kr in kun_list:
                if kr['okurigana']:
                    applicable_rules.append({
                        'rule': '送假名→训读动词',
                        'type': 'A',
                        'prediction': f'训读[{kr["full"]}]',
                        'confidence': 'very_high' if kr['okurigana'] in ['る','う','く','つ','ぶ','む','ぐ','ぬ','す'] else 'high',
                    })
                    break
            else:
                applicable_rules.append({
                    'rule': '送假名无→名词',
                    'type': 'B',
                    'prediction': '名词(训读)',
                    'confidence': 'high',
                })

        # Rule: radical check
        rad = info['radical']
        if rad in ['魚','米','牛','竹','虫','木','雨','鳥']:
            applicable_rules.append({'rule': '自然物部首→名词', 'type': 'B', 'prediction': '名词', 'confidence': 'very_high'})
        elif rad in ['手','言','力','足','刀','貝','馬']:
            applicable_rules.append({'rule': '动作部首→动词', 'type': 'B', 'prediction': '动词', 'confidence': 'high'})

        # Rule: solo kanji
        if solo_words:
            applicable_rules.append({'rule': '单汉字→训读(82.7%)', 'type': 'A', 'prediction': '训读', 'confidence': 'high'})

        # Compound pattern
        if compound_words:
            short_compounds = [w for w in compound_words if w['mora'] <= 2]
            long_compounds = [w for w in compound_words if w['mora'] >= 5]
            if short_compounds:
                applicable_rules.append({'rule': '短复合词→音+音(71.2%)', 'type': 'A', 'prediction': '音读', 'confidence': 'high'})
            if long_compounds:
                applicable_rules.append({'rule': '长复合词→含训读(90.4%)', 'type': 'A', 'prediction': '含训读', 'confidence': 'very_high'})

        lookup[ch] = {
            'kanji': ch,
            'radical': rad,
            'stroke': info['stroke_count'],
            'on': on_list[:3],
            'kun': [kr['full'] for kr in kun_list[:5]],
            'jlpt_levels': levels,
            'solo_kun_rate': kun_solo / len(solo_words) if solo_words else 0,
            'total_words': len(words),
            'applicable_rules': applicable_rules,
            'example_words': [f"{w['kanji']}({w['kana']})" for w in words[:6]],
        }

    return lookup

def write_unified_lookup(lookup, out_dir):
    """Write per-level lookup files."""
    for level in JLPT_LEVELS:
        level_chars = {ch: info for ch, info in lookup.items() if level in info['jlpt_levels']}
        sorted_chars = sorted(level_chars.items(), key=lambda x: x[1]['total_words'], reverse=True)

        lines = []
        lines.append(f'# JLPT {level} 统一音训查卡 · Unified On+Kun Lookup')
        lines.append('')
        lines.append(f'> {len(sorted_chars)} 字 | 每字=音读预测+训读预测+判定规则')
        lines.append('')
        lines.append('---')
        lines.append('')

        for ch, info in sorted_chars[:100]:
            lines.append(f'## {ch}')
            lines.append('')
            lines.append(f'| 属性 | 值 |')
            lines.append(f'|------|----|')
            lines.append(f'| 部首 | {info["radical"]} |')
            lines.append(f'| 画数 | {info["stroke"]} |')
            lines.append(f'| 音读 | {", ".join(info["on"])} |')
            lines.append(f'| 训读 | {", ".join(info["kun"])} |')
            lines.append(f'| 单字训读率 | {info["solo_kun_rate"]:.0%} |')
            lines.append(f'| 出现词数 | {info["total_words"]} |')
            lines.append(f'| 例词 | {", ".join(info["example_words"][:5])} |')
            lines.append('')

            if info['applicable_rules']:
                lines.append('**适用规则**:')
                for r in info['applicable_rules']:
                    conf_badge = '🟢' if r['confidence'] == 'very_high' else '🔵' if r['confidence'] == 'high' else '🟡'
                    lines.append(f'- {conf_badge} [{r["type"]}] {r["rule"]} → {r["prediction"]}')
            lines.append('')
            lines.append('---')
            lines.append('')

        with open(f'{out_dir}/kun_v7_lookup_{level}.md', 'w') as f:
            f.write('\n'.join(lines))

    return lookup

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Kun-Yomi V7: Active Learning System")
    print("=" * 60)

    os.makedirs(OUT, exist_ok=True)

    # Load data
    jlpt_words, kanji_db, v4 = load_data()
    indexes = build_indexes(jlpt_words, kanji_db, v4)
    print(f"  {len(indexes['sorted_stems'])} stems indexed")
    print(f"  {len(indexes['same_kun_jlpt'])} JLPT same-kun groups")

    # Module 1: 30-day plan
    print("\n[1/8] Building 30-day study plan...")
    plan = build_30day_plan(jlpt_words, kanji_db, indexes)
    write_30day_plan(plan, OUT)
    print(f"  {len(plan)} days planned")

    # Module 2: Training exercises
    print("[2/8] Generating training exercises...")
    exercises = build_exercises(jlpt_words, kanji_db, indexes)
    write_exercises(exercises, OUT)
    for t, ex in exercises.items():
        print(f"  {t}: {len(ex)} questions")

    # Module 3: Confusion risk
    print("[3/8] Computing confusion risk scores...")
    confusion = build_confusion_scores(kanji_db, indexes)
    write_confusion_scores(confusion, OUT)
    high_risk = [s for s in confusion if s['avg_risk'] >= 35]
    print(f"  {len(confusion)} groups scored, {len(high_risk)} high-risk (≥35)")

    # Module 4: Mnemonics
    print("[4/8] Generating mnemonics...")
    mnemonics = build_mnemonics(kanji_db, indexes)
    write_mnemonics(mnemonics, OUT)
    print(f"  {len(mnemonics)} mnemonics generated")

    # Module 5: Mermaid graphs
    print("[5/8] Building Mermaid graphs...")
    graphs = build_mermaid_graphs(kanji_db, indexes, v4)
    write_mermaid_graphs(graphs, OUT)
    print(f"  {len(graphs)} graphs generated")

    # Module 6: Scene-anchored rules
    print("[6/8] Building scene-anchored rules...")
    scenes = build_scene_rules()
    write_scene_rules(scenes, OUT)
    print(f"  {len(scenes)} rules with scenes")

    # Module 7: Error prediction
    print("[7/8] Predicting error patterns...")
    errors = build_error_prediction(kanji_db, indexes)
    write_error_prediction(errors, OUT)
    print(f"  {sum(len(v) for v in errors.values())} total error predictions")

    # Module 8: Unified lookup
    print("[8/8] Building unified lookup...")
    lookup = build_unified_lookup(kanji_db, indexes)
    write_unified_lookup(lookup, OUT)
    print(f"  {len(lookup)} kanji entries, 5 per-level files")

    # Summary
    print("\n" + "=" * 60)
    print("V7 generation complete!")
    v7_files = sorted([f for f in os.listdir(OUT) if f.startswith('kun_v7')])
    for f in v7_files:
        size = os.path.getsize(os.path.join(OUT, f))
        print(f"  {f} ({size:,} bytes)")
    print("=" * 60)

if __name__ == '__main__':
    main()
