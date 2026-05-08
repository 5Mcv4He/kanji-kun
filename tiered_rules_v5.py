#!/usr/bin/env python3
"""
训读分层规则系统 v5 — 贪婪集合覆盖 + 7桥特征 + 4类规则
==========================================================
目标：为汉语母语JLPT备考者，按N5-N1分层，找出最少记忆量下覆盖率最高的规则组合。

核心里程碑 vs v3/v4:
- 使用V9标注数据作为ground truth（每汉字在每词中的实际读音类型+读法）
- 7桥特征提取（送假名/语义域/部首/部件/音读参考/音系/复合词位置）
- 4类规则（A=音训判断, B=词类, C=具体词干, D=验证）
- 贪婪集合覆盖（覆盖率×准确率²/记忆成本）
- 三条学习路径（Quick 80%/Deep 92%/Complete 98%）
- kanji-on兼容JSON输出格式
"""

import json, os, re, math, time
from collections import defaultdict, Counter
import openpyxl

BASE = '/Volumes/SSD/work/kanji-kun'
OUT = f'{BASE}/output'
KANJI_XLSM = f'{BASE}/漢字検索V2.xlsm'
V9_DATA = f'{OUT}/kun_v9_data.json'

JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

# ─── Kana utilities ───
KATA_TO_HIRA = str.maketrans(
    'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'
    'ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ'
    'ャュョッァィゥェォ',
    'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'
    'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ'
    'ゃゅょっあいうえお'
)

def k2h(s):
    return s.translate(KATA_TO_HIRA)

def mora_count(s):
    s = k2h(s)
    cnt = i = 0
    while i < len(s):
        if i+1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉ':
            cnt += 1; i += 2
        elif s[i] in 'っッ': cnt += 1; i += 1
        else: cnt += 1; i += 1
    return cnt

# ═══════════════════════════════════════════
# 1. DATA LOADING
# ═══════════════════════════════════════════

def load_kanji_db():
    wb = openpyxl.load_workbook(KANJI_XLSM, read_only=True, data_only=True)
    ws = wb['漢字一覧']
    db = {}
    for row in ws.iter_rows(min_row=2, max_row=46850, values_only=True):
        if not row[0]: continue
        ch = str(row[0]).strip()
        if not ch or len(ch) > 2: continue
        components = str(row[1]).strip() if row[1] else ''
        radical = str(row[3]).strip() if row[3] else ''
        on_raw = str(row[9]).strip() if row[9] else ''
        kun_raw = str(row[10]).strip() if row[10] else ''
        meaning_raw = str(row[11]).strip() if row[11] else ''

        on_list = []
        for o in on_raw.replace('、', ',').split(','):
            o = o.strip().strip('◇◆▼▽▲△▽').strip()
            if o:
                o = re.sub(r'[（(].*?[）)]', '', o).strip()
                if o: on_list.append(k2h(o))

        kun_list = []
        for kr in kun_raw.replace('、', ',').split(','):
            kr = kr.strip().strip('◇◆▼▽▲△').strip()
            if not kr: continue
            parts = re.split(r'[・.]', kr)
            stem = k2h(parts[0]) if parts[0] else ''
            okuri = k2h(parts[-1]) if len(parts) >= 2 else ''
            wclass = classify_wc(okuri)
            kun_list.append({
                'stem': stem, 'okuri': okuri, 'wclass': wclass,
                'full': f"{stem}.{okuri}" if okuri else stem,
                'mora': mora_count(stem),
                'first_mora': stem[0] if stem else '',
                'last_mora': stem[-1] if stem else '',
            })

        db[ch] = {
            'kanji': ch, 'components': components,
            'comp_set': set(c for c in components if c != ch and c != radical),
            'radical': radical,
            'on_list': on_list, 'kun_list': kun_list,
            'meaning': meaning_raw,
            'has_kun': len(kun_list) > 0, 'has_on': len(on_list) > 0,
        }
    wb.close()
    return db


def classify_wc(okuri):
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


def load_v9_data():
    with open(V9_DATA) as f:
        v9 = json.load(f)
    return v9['annotated_words']


# ═══════════════════════════════════════════
# 2. FEATURE EXTRACTION (7 BRIDGES)
# ═══════════════════════════════════════════

SEMANTIC_KEYWORDS = {
    'body': '体手耳目口鼻頭心血骨肉歯皮毛指腕脚腹背腰胸舌爪肌髪脳肺肝首唇頬顎喉肩肘膝踵瞳眉髭',
    'nature': '木草花虫魚鳥獣山川海石土水火風雨雲空星日月天地雪雷河湖森林岩砂波島岸谷原野',
    'action': '動打持歩走言話見聞食飲書読出入開閉取与切断折割作造建泳飛流泣笑思考知忘殺投押引曲伸寝起座立乗降渡通戻返送届拾捨',
    'emotion': '心思考念意情感怒喜悲恐愛憎恨楽苦哀愁恥怯妬嫉慢傲',
    'speech': '言語話告述説論談議訓読誦唱叫喚呼問答許諾',
    'person': '人男女子父母兄弟姉妹親族王臣民君主友敵師',
    'number': '一二三四五六七八九十百千万数量多少',
    'quality': '良悪美醜善正新古強弱固柔温冷暗明高低遠近長短大小太細厚薄軽重速遅甘辛酸',
}

RADICAL_CATEGORIES = {
    'nature': set('日雨風雲雪雷山川水氵火木林森草艹花石金土田里'),
    'body': set('月肉骨身皮毛髪首頁面目耳鼻口歯舌唇手足爪'),
    'animal': set('魚虫鳥犬犭牛馬羊豕豸亀龍虎鹿鼠兎'),
    'plant': set('竹米麦豆瓜禾麻'),
    'action': set('手扌言口見足辶行心忄彳廴走'),
    'tool': set('刀刂弓矢車舟器皿衣糸巾革韋'),
    'person': set('人亻子女父母兄弟姉妹王帝臣'),
    'building': set('門戸宀广厂穴'),
}


def get_semantic_domains(meaning):
    if not meaning: return ['other']
    domains = []
    for domain, chars in SEMANTIC_KEYWORDS.items():
        if any(c in meaning for c in chars):
            domains.append(domain)
    return domains if domains else ['other']


def get_radical_cats(radical):
    cats = [cat for cat, rads in RADICAL_CATEGORIES.items() if radical in rads]
    return cats if cats else ['other']


def get_position(i, total_len):
    if total_len == 1: return 'alone'
    elif i == 0: return 'start'
    elif i == total_len - 1: return 'end'
    else: return 'mid'


def extract_okuri_trail(word, char_pos):
    """Extract kana after kanji at char_pos in word string."""
    after = word[char_pos+1:] if char_pos + 1 < len(word) else ''
    trail = ''
    for c in after[:4]:
        if 'ぁ' <= c <= 'ゟ' or 'ァ' <= c <= 'ヿ':
            trail += k2h(c)
        else: break
    return trail


def build_instances(v9_words, kanji_db):
    """Build per-kanji instance list from V9 annotated words."""
    instances = []
    for w in v9_words:
        word = w['word']
        level = w['level']
        gt_details = w.get('gt_details', [])
        chars = [d['kanji'] for d in gt_details]
        if not chars: continue

        for i, d in enumerate(gt_details):
            ch = d['kanji']
            gt_type = d.get('type', '?')
            gt_reading = d.get('reading', '')
            ki = kanji_db.get(ch, {})
            if not ki: continue

            # Position
            char_positions = [j for j, c in enumerate(word) if c == ch]
            pos_in_word = char_positions[min(i, len(char_positions)-1)] if char_positions else -1
            position = get_position(i, len(chars))
            is_single = len(chars) == 1

            # Okurigana
            trailing_kana = extract_okuri_trail(word, pos_in_word) if pos_in_word >= 0 else ''
            has_okuri = bool(trailing_kana)
            okuri_suffix = ''

            # Match okurigana to known kun
            matched_kun = None
            for ku in ki.get('kun_list', []):
                if ku['okuri'] and trailing_kana.startswith(ku['okuri']):
                    matched_kun = ku; okuri_suffix = ku['okuri']; break
            if not okuri_suffix: okuri_suffix = trailing_kana[:2]

            # Semantic domains
            sem_domains = get_semantic_domains(ki['meaning'])

            # Radical cats
            rad_cats = get_radical_cats(ki['radical'])

            # Entering tone
            is_entering = any(mora_count(o) <= 2 and o[-1] in 'くつちきうい'
                            for o in ki.get('on_list', []))

            # Word class
            wclass = 'unknown'
            if gt_type == 'kun':
                if matched_kun: wclass = matched_kun['wclass']
                elif okuri_suffix: wclass = classify_wc(okuri_suffix)

            # Prev/next
            prev_ch = chars[i-1] if i > 0 else None
            next_ch = chars[i+1] if i+1 < len(chars) else None
            prev_type = gt_details[i-1]['type'] if i > 0 else None
            next_type = gt_details[i+1]['type'] if i+1 < len(gt_details) else None

            instances.append({
                'word': word, 'level': level,
                'kanji': ch, 'index': i,
                'gt_type': gt_type, 'gt_reading': gt_reading,
                'position': position, 'is_single': is_single,
                'has_okuri': has_okuri, 'okuri_suffix': okuri_suffix,
                'sem_domains': sem_domains,
                'radical': ki['radical'],
                'rad_cats': rad_cats,
                'comps': ki['comp_set'],
                'has_on': ki['has_on'], 'has_kun': ki['has_kun'],
                'num_kun': len(ki.get('kun_list', [])),
                'num_on': len(ki.get('on_list', [])),
                'is_entering': is_entering,
                'wclass': wclass,
                'prev_ch': prev_ch, 'next_ch': next_ch,
                'prev_type': prev_type, 'next_type': next_type,
                'total_chars': len(chars),
                'meaning': ki['meaning'],
            })

    return instances


# ═══════════════════════════════════════════
# 3. RULE ENUMERATION & EVALUATION
# ═══════════════════════════════════════════

def make_rule(rid, rtype, desc, condition_fn, predicts, cost=None, subtype=None):
    """Create a rule dict with condition function."""
    if cost is None:
        cost = {'A': 1, 'B': 1, 'C': 4, 'D': 1}[rtype]
    return {'id': rid, 'type': rtype, 'description': desc, 'condition': condition_fn,
            'predicts': predicts, 'cost': cost, 'subtype': subtype,
            'by_level': {}}


def evaluate_rule(rule, instances_by_level):
    """Evaluate a rule's accuracy + coverage per JLPT level."""
    for lv in JLPT_LEVELS:
        insts = instances_by_level[lv]
        if not insts: continue

        applicable = []
        for inst in insts:
            try:
                if rule['condition'](inst):
                    applicable.append(inst)
            except Exception:
                pass

        if not applicable: continue

        rtype = rule['type']
        correct = 0
        pred = rule['predicts']

        if rtype == 'A':
            correct = sum(1 for i in applicable if i['gt_type'] == pred)
        elif rtype == 'B':
            for i in applicable:
                if i['gt_type'] != 'kun': continue
                wc = i['wclass']
                if pred == 'noun': correct += 1 if ('noun' in wc and 'verb' not in wc) else 0
                elif pred == 'verb': correct += 1 if 'verb' in wc else 0
                elif pred == 'adjective': correct += 1 if 'adj' in wc else 0
                elif pred == 'verb_or_adj': correct += 1 if ('verb' in wc or 'adj' in wc) else 0
                elif pred == 'noun_renyo': correct += 1 if ('renyo' in wc or wc == 'noun') else 0
        elif rtype == 'C':
            correct = sum(1 for i in applicable
                        if i['gt_type'] == 'kun' and i['gt_reading'] == pred)
        elif rtype == 'D':
            correct = len(applicable)  # verification: always "checked"

        acc = correct / len(applicable)
        cov = len(applicable) / len(insts)

        rule['by_level'][lv] = {
            'total': len(applicable), 'correct': correct,
            'accuracy': acc, 'coverage': cov,
            'sample': [f"{i['word']}.{i['kanji']}" for i in applicable[:5]],
        }


def enumerate_type_a():
    """Type A: Reading type (on vs kun)."""
    rules = []

    rules.append(make_rule('A1', 'A', '有送假名→训读',
        lambda i: i['has_okuri'], 'kun'))
    rules.append(make_rule('A2', 'A', '单汉字无假名→训读',
        lambda i: i['is_single'] and not i['has_okuri'], 'kun'))
    rules.append(make_rule('A3', 'A', '多汉字无假名→音读',
        lambda i: not i['is_single'] and not i['has_okuri'], 'on'))
    rules.append(make_rule('A4', 'A', '身体/自然/人域→训读',
        lambda i: bool(set(i['sem_domains']) & {'body','nature','person'}), 'kun'))
    rules.append(make_rule('A5', 'A', '抽象/数量/情感域→音读',
        lambda i: bool(set(i['sem_domains']) & {'quality','number','emotion'}), 'on'))
    rules.append(make_rule('A7', 'A', '词首+送假名→训读',
        lambda i: i['position'] == 'start' and i['has_okuri'], 'kun'))
    rules.append(make_rule('A8', 'A', '词尾无假名(非单独)→音读',
        lambda i: i['position'] == 'end' and not i['has_okuri'] and not i['is_single'], 'on'))
    rules.append(make_rule('A9', 'A', '入声字+无假名→音读',
        lambda i: i['is_entering'] and not i['has_okuri'], 'on'))

    return rules


def enumerate_type_b():
    """Type B: Word class prediction for kun readings."""
    rules = []

    rules.append(make_rule('B1', 'B', '部首=魚虫木竹鳥→名词',
        lambda i: i['gt_type'] == 'kun' and i['radical'] in '魚虫木竹鳥米豆瓜禾麻艸艹', 'noun'))
    rules.append(make_rule('B2', 'B', '部首=手扌言足→动词',
        lambda i: i['gt_type'] == 'kun' and i['radical'] in '手扌言足辶行走彳廴', 'verb'))
    rules.append(make_rule('B3', 'B', '部首=日月山石雨→名词',
        lambda i: i['gt_type'] == 'kun' and i['radical'] in '日月山石雨風雲雪雷', 'noun'))
    rules.append(make_rule('B4', 'B', '部首=心忄→动词/形容词',
        lambda i: i['gt_type'] == 'kun' and i['radical'] in '心忄', 'verb_or_adj'))
    rules.append(make_rule('B5', 'B', '送假名=る→动词',
        lambda i: i['gt_type'] == 'kun' and i['okuri_suffix'].endswith('る'), 'verb'))
    rules.append(make_rule('B6', 'B', '送假名=い→形容词',
        lambda i: i['gt_type'] == 'kun' and i['okuri_suffix'].endswith('い') and not i['okuri_suffix'].endswith('しい'), 'adjective'))
    rules.append(make_rule('B7', 'B', '送假名=しい→形容词',
        lambda i: i['gt_type'] == 'kun' and i['okuri_suffix'].endswith('しい'), 'adjective'))
    rules.append(make_rule('B8', 'B', '送假名=く/ぐ/す/む/ぶ/ぬ→动词',
        lambda i: i['gt_type'] == 'kun' and any(i['okuri_suffix'].endswith(e) for e in ['く','ぐ','す','む','ぶ','ぬ']), 'verb'))
    rules.append(make_rule('B9', 'B', '无送假名→名词',
        lambda i: i['gt_type'] == 'kun' and not i['has_okuri'], 'noun'))
    rules.append(make_rule('B10', 'B', '送假名=り/き/み/し/ち/け→名词(连用)',
        lambda i: i['gt_type'] == 'kun' and any(i['okuri_suffix'].endswith(e) for e in ['り','き','み','し','ち','け']), 'noun_renyo'))
    rules.append(make_rule('B11', 'B', '身体/自然域+无假名→名词(确认)',
        lambda i: i['gt_type'] == 'kun' and not i['has_okuri'] and bool(set(i['sem_domains']) & {'body','nature'}), 'noun'))

    return rules


def enumerate_type_c(instances_by_level, kanji_db):
    """Type C: Specific kun stem prediction."""
    rules = []

    # C1: Component → stem
    all_kun_insts = []
    for lv in JLPT_LEVELS:
        all_kun_insts.extend([i for i in instances_by_level[lv] if i['gt_type'] == 'kun'])

    comp_to_stems = defaultdict(lambda: defaultdict(int))
    comp_to_total = defaultdict(int)
    for inst in all_kun_insts:
        for comp in inst['comps']:
            if len(comp) == 1 and '一' <= comp <= '鿿':
                comp_to_stems[comp][inst['gt_reading']] += 1
                comp_to_total[comp] += 1

    comp_rules = []
    for comp, stem_counts in comp_to_stems.items():
        total = comp_to_total[comp]
        if total < 4: continue
        best = max(stem_counts, key=stem_counts.get)
        acc = stem_counts[best] / total
        if acc >= 0.30:
            cfn = None  # capture comp in closure
            def make_cfn(c):
                return lambda i: i['gt_type'] == 'kun' and c in i['comps']
            comp_rules.append((comp, best, acc, total))

    comp_rules.sort(key=lambda x: -x[2] * math.log(x[3]))
    for comp, stem, acc, total in comp_rules[:50]:
        rules.append(make_rule(f'C_c_{comp}', 'C', f'部件「{comp}」→词干「{stem}」',
            make_cfn(comp), stem, cost=3, subtype='component'))

    # C2: Okurigana → stem patterns
    oku_to_stems = defaultdict(lambda: defaultdict(int))
    for inst in all_kun_insts:
        if inst['okuri_suffix']:
            oku_to_stems[inst['okuri_suffix']][inst['gt_reading']] += 1

    oku_rules = []
    for oku, stem_counts in oku_to_stems.items():
        total = sum(stem_counts.values())
        if total < 4: continue
        best = max(stem_counts, key=stem_counts.get)
        acc = stem_counts[best] / total
        if acc >= 0.28:
            oku_rules.append((oku, best, acc, total))

    oku_rules.sort(key=lambda x: -x[2] * math.log(x[3]))
    for oku, stem, acc, total in oku_rules[:60]:
        def make_ofn(o):
            return lambda i: i['gt_type'] == 'kun' and i['okuri_suffix'] == o
        rules.append(make_rule(f'C_o_{oku}', 'C', f'送假名「{oku}」→词干「{stem}」',
            make_ofn(oku), stem, cost=3, subtype='okurigana'))

    # C3: Semantic + Position → stem
    sem_pos = defaultdict(lambda: defaultdict(int))
    for inst in all_kun_insts:
        key = (tuple(sorted(inst['sem_domains'])), inst['position'])
        sem_pos[key][inst['gt_reading']] += 1

    sem_rules = []
    for (doms, pos), stem_counts in sem_pos.items():
        total = sum(stem_counts.values())
        if total < 5: continue
        best = max(stem_counts, key=stem_counts.get)
        acc = stem_counts[best] / total
        if acc >= 0.25:
            dom_str = '+'.join(doms)
            sem_rules.append((doms, pos, best, acc, total))

    sem_rules.sort(key=lambda x: -x[3] * math.log(x[4]))
    for doms, pos, stem, acc, total in sem_rules[:30]:
        dom_set = set(doms)
        def make_sfn(ds, p):
            return lambda i: (i['gt_type'] == 'kun' and set(i['sem_domains']) == ds
                            and i['position'] == p)
        rules.append(make_rule(f'C_s_{"+".join(doms)}_{pos}', 'C',
            f'语义域[{",".join(doms)}]+位置[{pos}]→词干「{stem}」',
            make_sfn(dom_set, pos), stem, cost=4, subtype='semantic'))

    return rules


def enumerate_type_d():
    """Type D: Verification rules."""
    rules = []
    rules.append(make_rule('D1', 'D', '浊音不重复(同一词干内)',
        lambda i: i['gt_type'] == 'kun' and i['gt_reading'] and
        any(c in 'がぎぐげござじずぜぞだぢづでどばびぶべぼ' for c in i['gt_reading']),
        'verify:no_voiced_repeat'))
    rules.append(make_rule('D2', 'D', '促音只在入声字后',
        lambda i: i['gt_type'] == 'on' and 'っ' in i.get('gt_reading', ''),
        'verify:entering_only'))
    rules.append(make_rule('D3', 'D', '连浊只在非首位',
        lambda i: i['gt_type'] == 'kun' and i['position'] != 'start' and not i['is_single'],
        'verify:rendaku_position'))
    rules.append(make_rule('D4', 'D', '训读动词必有送假名',
        lambda i: i['gt_type'] == 'kun' and 'verb' in i['wclass'],
        'verify:verb_has_okuri'))
    rules.append(make_rule('D5', 'D', '入声字音读必为短音',
        lambda i: i['gt_type'] == 'on' and i['is_entering'],
        'verify:short_on_only'))
    return rules


# ═══════════════════════════════════════════
# 4. GREEDY SET-COVER
# ═══════════════════════════════════════════

def greedy_set_cover(instances, rules, level, max_rules=120):
    """Select rules maximizing coverage across multiple prediction targets.

    Uses separate coverage tracking per rule type since Type A (on/kun),
    Type B (word class), and Type C (specific stem) answer different questions.
    Type A's coverage pool = all instances (N_total).
    Type B's coverage pool = kun instances (N_kun).
    Type C's coverage pool = kun instances (N_kun).

    Score normalizes by pool size so that a Type B rule covering 50% of kun
    instances can compete with a Type A rule covering 50% of all instances.
    """
    level_insts = instances[level]
    if not level_insts: return [], set(), set(), set()

    kun_idxs = {idx for idx, inst in enumerate(level_insts) if inst['gt_type'] == 'kun'}
    all_idxs = set(range(len(level_insts)))
    N_kun = len(kun_idxs)
    N_all = len(all_idxs)

    # Precompute hits per rule per coverage pool
    rule_info = {}  # rid -> {'rule': r, 'hits_A': set, 'hits_B': set, 'hits_C': set}
    for r in rules:
        lv_data = r['by_level'].get(level)
        if not lv_data or lv_data['total'] == 0: continue
        hA = set(); hB = set(); hC = set()
        for idx, inst in enumerate(level_insts):
            try:
                if not r['condition'](inst): continue
            except Exception:
                continue
            if r['type'] == 'A' and inst['gt_type'] == r['predicts']:
                hA.add(idx)
            elif r['type'] == 'B' and inst['gt_type'] == 'kun':
                wc = inst['wclass']
                p = r['predicts']
                ok = False
                if p == 'noun': ok = 'noun' in wc and 'verb' not in wc
                elif p == 'verb': ok = 'verb' in wc
                elif p == 'adjective': ok = 'adj' in wc
                elif p == 'verb_or_adj': ok = ('verb' in wc or 'adj' in wc)
                elif p == 'noun_renyo': ok = ('renyo' in wc or wc == 'noun')
                if ok: hB.add(idx)
            elif r['type'] == 'C' and inst['gt_type'] == 'kun':
                if inst['gt_reading'] == r['predicts']:
                    hC.add(idx)
        if hA or hB or hC:
            rule_info[r['id']] = (r, hA, hB, hC)

    covered_A = set(); covered_B = set(); covered_C = set()
    selected = []

    while rule_info and len(selected) < max_rules:
        best_id = None; best_score = -1; best_delA = set(); best_delB = set(); best_delC = set()

        for rid, (rule, hA, hB, hC) in list(rule_info.items()):
            newA = hA - covered_A
            newB = hB - covered_B
            newC = hC - covered_C

            if not newA and not newB and not newC:
                del rule_info[rid]; continue

            acc = rule['by_level'][level]['accuracy']
            # Normalize by pool size so types compete fairly
            scoreA = (len(newA) / N_all) * acc * acc / rule['cost'] if N_all > 0 else 0
            scoreB = (len(newB) / N_kun) * acc * acc / rule['cost'] * 1.2 if N_kun > 0 else 0  # slight bonus for kun-specific rules
            scoreC = (len(newC) / N_kun) * acc * acc / rule['cost'] * 1.5 if N_kun > 0 else 0  # higher bonus for stem precision
            total_score = scoreA + scoreB + scoreC

            if total_score > best_score:
                best_score = total_score; best_id = rid
                best_delA = newA; best_delB = newB; best_delC = newC

        if best_id is None: break
        rule, _, _, _ = rule_info[best_id]
        del rule_info[best_id]

        covered_A |= best_delA; covered_B |= best_delB; covered_C |= best_delC

        combined_new = len(best_delA) + len(best_delB) + len(best_delC)
        combined_covered = len(covered_A) + len(covered_B) + len(covered_C)

        selected.append({
            'rule': rule,
            'newA': len(best_delA), 'newB': len(best_delB), 'newC': len(best_delC),
            'newly_covered': combined_new,
            'cumulative': combined_covered,
            'cum_A': len(covered_A), 'cum_B': len(covered_B), 'cum_C': len(covered_C),
            'score': best_score,
        })

    return selected, covered_A, covered_B, covered_C


# ═══════════════════════════════════════════
# 5. OUTPUT GENERATION
# ═══════════════════════════════════════════

def generate_per_level_json(level, selected, instances, total_n):
    kun_n = sum(1 for i in instances if i['gt_type'] == 'kun')
    rules_out = []
    for sr in selected:
        r = sr['rule']
        rd = r['by_level'].get(level, {})
        rules_out.append({
            'id': r['id'], 'type': r['type'],
            'description': r['description'],
            'predicts': r['predicts'], 'cost': r['cost'],
            'accuracy': rd.get('accuracy', 0),
            'newA': sr.get('newA', sr.get('newly_covered', 0)),
            'newB': sr.get('newB', 0), 'newC': sr.get('newC', 0),
            'cum_A': sr.get('cum_A', 0), 'cum_B': sr.get('cum_B', 0), 'cum_C': sr.get('cum_C', 0),
            'samples': rd.get('sample', []),
        })

    # Compute composite coverage
    if selected:
        last = selected[-1]
        cov_A = last.get('cum_A', 0) / total_n if total_n > 0 else 0
        cov_B = last.get('cum_B', 0) / kun_n if kun_n > 0 else 0
        cov_C = last.get('cum_C', 0) / kun_n if kun_n > 0 else 0
    else:
        cov_A = cov_B = cov_C = 0

    return {
        'level': level, 'total_instances': total_n,
        'kun_instances': kun_n,
        'on_instances': sum(1 for i in instances if i['gt_type'] == 'on'),
        'num_rules': len(selected),
        'coverage': {'on_kun': cov_A, 'word_class': cov_B, 'specific_stem': cov_C},
        'rules': rules_out,
    }


def generate_per_level_md(level, json_data, selected, instances):
    lines = []
    lines.append(f"# JLPT {level} 训读分层规则\n")
    lines.append(f"> {json_data['total_instances']}实例（{json_data['kun_instances']}训+{json_data['on_instances']}音）\n")

    kun_n = json_data['kun_instances']
    total_n = json_data['total_instances']
    cov = json_data['coverage']
    lines.append("## 覆盖总览\n")
    lines.append(f"- **音训判断(Type A)**: {cov['on_kun']:.1%} 覆盖所有实例")
    lines.append(f"- **词类预测(Type B)**: {cov['word_class']:.1%} 覆盖训读实例")
    lines.append(f"- **具体词干(Type C)**: {cov['specific_stem']:.1%} 覆盖训读实例")
    lines.append("")

    lines.append("## 学习路径\n")
    lines.append("| 路径 | 规则数 | 音训(A) | 词类(B) | 词干(C) | 综合 | 记忆项 |")
    lines.append("|------|--------|---------|---------|---------|------|--------|")
    total_decisions = total_n + 2 * max(kun_n, 1)
    for path_name, min_gain in [('Quick', 0.005), ('Deep', 0.001), ('Complete', 0)]:
        cnt = 0; mem = 0; cA = cB = cC = comp = 0
        for sr in selected:
            cnt += 1; mem += sr['rule']['cost']
            new_decisions = (sr.get('newA', 0) + sr.get('newB', 0) + sr.get('newC', 0))
            marginal = new_decisions / total_decisions if total_decisions > 0 else 0
            cA = sr.get('cum_A', 0) / total_n if total_n > 0 else 0
            cB = sr.get('cum_B', 0) / kun_n if kun_n > 0 else 0
            cC = sr.get('cum_C', 0) / kun_n if kun_n > 0 else 0
            covered_decisions = sr.get('cum_A', 0) + sr.get('cum_B', 0) + sr.get('cum_C', 0)
            comp = covered_decisions / total_decisions if total_decisions > 0 else 0
            if marginal < min_gain and cnt > 3:
                break
        lines.append(f"| {path_name} | {cnt} | {cA:.0%} | {cB:.0%} | {cC:.0%} | {comp:.0%} | ~{mem} |")
    lines.append("")

    lines.append("## 规则详情\n")
    for i, sr in enumerate(selected):
        r = sr['rule']
        rd = r['by_level'].get(level, {})
        nA = sr.get('newA', 0); nB = sr.get('newB', 0); nC = sr.get('newC', 0)
        parts = []
        if nA: parts.append(f"音训+{nA}")
        if nB: parts.append(f"词类+{nB}")
        if nC: parts.append(f"词干+{nC}")
        detail = ', '.join(parts)
        cA = sr.get('cum_A', 0); cB = sr.get('cum_B', 0); cC = sr.get('cum_C', 0)
        lines.append(f"### {i+1}. {r['id']}: {r['description']}")
        lines.append(f"- **类型**: Type {r['type']} | **准确率**: {rd.get('accuracy',0):.1%} | **成本**: {r['cost']}")
        lines.append(f"- **新增覆盖**: {detail} | **累计**: A={cA}/{total_n} B={cB}/{kun_n} C={cC}/{kun_n}")
        lines.append(f"- **示例**: {', '.join(rd.get('sample', [])[:6])}")
        lines.append("")

    return '\n'.join(lines)


def generate_iron_laws(instances_by_level, all_rules):
    lines = []
    lines.append("# Kun-Yomi 铁律 (Iron Laws)\n")
    lines.append("训读领域的绝对规律 — 接近100%准确率，零或极低记忆成本。\n")

    iron_ids = ['A1', 'A2', 'A3', 'A4', 'D1', 'D2', 'D4']
    iron_rules = [r for r in all_rules if r['id'] in iron_ids]

    lines.append("| # | 铁律 | 预测 | 类型 |")
    lines.append("|---|------|------|------|")
    for r in iron_rules:
        lines.append(f"| {r['id']} | {r['description']} | {r['predicts']} | Type {r['type']} |")

    lines.append("")
    lines.append("## 与 kanji-on 五鉄則 对比\n")
    lines.append("| kanji-on | kun-yomi 对应 |")
    lines.append("|----------|-------------|")
    lines.append("| 1. 同声旁=同音读 | A4: 同语义域=同读法 |")
    lines.append("| 2. 拼音→音读映射 | A1: 送假名→训读用言 |")
    lines.append("| 3. 入声=短音 | D1: 浊音不重复(训读验证) |")
    lines.append("| 4. 词频默认=93% | A3: 多汉字无假名=音读 |")
    lines.append("| 5. 复合词位置消歧 | A2: 单汉字词=训读 |")

    return '\n'.join(lines)


def generate_learning_map(selected_by_level, instances_by_level):
    lines = []
    lines.append("# Kun-Yomi 学习地图\n")
    lines.append("基于贪婪集合覆盖结果，按性价比排序。\n")

    for lv in JLPT_LEVELS:
        selected = selected_by_level[lv]
        total = len(instances_by_level[lv])
        kun_n = sum(1 for i in instances_by_level[lv] if i['gt_type'] == 'kun')
        lines.append(f"## {lv} ({total}实例, {kun_n}训读)\n")
        lines.append("| # | 规则 | 类型 | 成本 | 准确率 | 覆盖(A/B/C) |")
        lines.append("|---|------|------|------|--------|-------------|")
        for i, sr in enumerate(selected[:25]):
            r = sr['rule']
            rd = r['by_level'].get(lv, {})
            nA = sr.get('newA', 0); nB = sr.get('newB', 0); nC = sr.get('newC', 0)
            cov_str = f"+{nA}/+{nB}/+{nC}"
            lines.append(f"| {i+1} | {r['description']} | {r['type']} | {r['cost']} | {rd.get('accuracy',0):.1%} | {cov_str} |")
        lines.append("")

    return '\n'.join(lines)


# ═══════════════════════════════════════════
# 6. MAIN
# ═══════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 60)
    print("训读分层规则系统 v5 · Greedy Set-Cover")
    print("=" * 60)

    # 1. Load
    print("\n[1/6] 加载数据...")
    kanji_db = load_kanji_db()
    print(f"  Kanji DB: {len(kanji_db)} entries")
    v9_words = load_v9_data()
    print(f"  V9 annotated: {len(v9_words)} words")

    # 2. Build instances
    print("\n[2/6] 提取7桥特征，构建实例集...")
    all_insts = build_instances(v9_words, kanji_db)
    instances_by_level = {lv: [] for lv in JLPT_LEVELS}
    for inst in all_insts:
        if inst['level'] in JLPT_LEVELS:
            instances_by_level[inst['level']].append(inst)

    for lv in JLPT_LEVELS:
        kun_n = sum(1 for i in instances_by_level[lv] if i['gt_type'] == 'kun')
        on_n = sum(1 for i in instances_by_level[lv] if i['gt_type'] == 'on')
        print(f"  {lv}: {len(instances_by_level[lv])} instances ({kun_n} kun + {on_n} on)")

    # 3. Enumerate & evaluate
    print("\n[3/6] 枚举规则...")
    type_a = enumerate_type_a()
    type_b = enumerate_type_b()
    type_c = enumerate_type_c(instances_by_level, kanji_db)
    type_d = enumerate_type_d()
    all_rules = type_a + type_b + type_c + type_d
    print(f"  A={len(type_a)} B={len(type_b)} C={len(type_c)} D={len(type_d)} = {len(all_rules)} total")

    print("  评估规则...")
    for rule in all_rules:
        evaluate_rule(rule, instances_by_level)

    # Show top rules by score per level
    for lv in JLPT_LEVELS:
        scored = []
        for r in all_rules:
            d = r['by_level'].get(lv)
            if d and d['total'] >= 3:
                score = d['correct'] * d['accuracy'] / r['cost']
                scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        top5 = [(s, r['id'], r['by_level'][lv]['accuracy'])
                for s, r in scored[:5]]
        print(f"  {lv} top: {' | '.join(f'{rid}(acc={acc:.1%})' for _, rid, acc in top5)}")

    # 4. Greedy set-cover
    print("\n[4/6] 贪婪集合覆盖(多目标)...")
    selected_by_level = {}
    for lv in JLPT_LEVELS:
        selected, covA, covB, covC = greedy_set_cover(instances_by_level, all_rules, lv)
        total = len(instances_by_level[lv])
        kun_n = sum(1 for i in instances_by_level[lv] if i['gt_type'] == 'kun')
        print(f"  {lv}: {len(selected)} rules → "
              f"A={len(covA)}/{total}={len(covA)/total:.1%} "
              f"B={len(covB)}/{kun_n}={len(covB)/max(kun_n,1):.1%} "
              f"C={len(covC)}/{kun_n}={len(covC)/max(kun_n,1):.1%}")

        # Path counts (Quick: high-impact only, Deep: all worthwhile, Complete: everything)
        total_decisions = total + 2 * max(kun_n, 1)
        for path_name, min_gain in [('Quick', 0.005), ('Deep', 0.001), ('Complete', 0)]:
            cnt = 0; mem = 0; composite = 0
            for sr in selected:
                cnt += 1; mem += sr['rule']['cost']
                new_decisions = (sr.get('newA', 0) + sr.get('newB', 0) + sr.get('newC', 0))
                marginal = new_decisions / total_decisions if total_decisions > 0 else 0
                covered_decisions = sr.get('cum_A', 0) + sr.get('cum_B', 0) + sr.get('cum_C', 0)
                composite = covered_decisions / total_decisions if total_decisions > 0 else 0
                if marginal < min_gain and cnt > 3:
                    break
            print(f"    {path_name}: {cnt} rules, cost={mem}, composite={composite:.1%}")

        selected_by_level[lv] = selected

    # 5. Generate outputs
    print("\n[5/6] 生成输出文件...")

    for lv in JLPT_LEVELS:
        insts = instances_by_level[lv]
        json_data = generate_per_level_json(lv, selected_by_level[lv], insts, len(insts))
        with open(f'{OUT}/kun_{lv}_tiered_rules.json', 'w') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        md_text = generate_per_level_md(lv, json_data, selected_by_level[lv], insts)
        with open(f'{OUT}/kun_{lv}_tiered_rules.md', 'w') as f:
            f.write(md_text)
        print(f"  → kun_{lv}_tiered_rules.json + .md")

    iron_text = generate_iron_laws(instances_by_level, all_rules)
    with open(f'{OUT}/kun_iron_laws.md', 'w') as f:
        f.write(iron_text)
    print(f"  → kun_iron_laws.md")

    learn_text = generate_learning_map(selected_by_level, instances_by_level)
    with open(f'{OUT}/kun_learning_map.md', 'w') as f:
        f.write(learn_text)
    print(f"  → kun_learning_map.md")

    # 6. Summary
    t1 = time.time()
    print(f"\n[6/6] 完成 ({(t1-t0):.1f}s)")
    print("=" * 60)
    for lv in JLPT_LEVELS:
        sel = selected_by_level[lv]
        insts = instances_by_level[lv]
        total = len(insts)
        kun_n = sum(1 for i in insts if i['gt_type'] == 'kun')
        if sel:
            last = sel[-1]
            cA = last.get('cum_A',0)/total; cB = last.get('cum_B',0)/max(kun_n,1); cC = last.get('cum_C',0)/max(kun_n,1)
        else:
            cA = cB = cC = 0
        print(f"  {lv}: {total}实例({kun_n}训), {len(sel)}规则, "
              f"A={cA:.1%} B={cB:.1%} C={cC:.1%}")


if __name__ == '__main__':
    main()
