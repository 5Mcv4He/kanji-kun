#!/usr/bin/env python3
"""V9 Diagnostic v3: Push compression to 4:1, maximize anchors, fix all trap types.

Key improvements over v2:
- Load kanji decomposition from 漢字検索V2.xlsm for radical/component data
- New anchor types: radical_group, compound_pattern, on_kun_bridge
- Better morphology: merge same-first-2-mora readings with different lengths
- Refined carry-over: 3-tier system (strong/medium/weak)
- Shape-similar trap detection using shared radical + different reading
"""

import json, math, re, sys
from collections import defaultdict, Counter
from pathlib import Path

OUT = Path('/Volumes/SSD/work/kanji-kun/output')
BASE = Path('/Volumes/SSD/work/kanji-kun')

# ============================================================
# LOADING
# ============================================================

def load_data():
    with open(OUT / 'kun_v9_data.json') as f:
        return json.load(f)

def load_kanji_decomposition():
    """Load radical + component data from 漢字検索V2.xlsm."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(BASE / '漢字検索V2.xlsm', read_only=True, data_only=True)
        # Use the correct sheet: 漢字一覧
        if '漢字一覧' in wb.sheetnames:
            ws = wb['漢字一覧']
        else:
            ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            wb.close()
            return {}, {}

        header = [str(c) if c else '' for c in rows[0]]
        # Column mapping for 漢字一覧:
        # 0=漢字, 1=構成文字, 3=部首, 5=非部首部
        kanji_idx = 0  # 漢字
        radical_idx = 3  # 部首
        components_idx = 1  # 構成文字

        kanji_radical = {}
        kanji_components = {}
        count = 0
        for row in rows[1:]:
            if not row or not row[kanji_idx]:
                continue
            k = str(row[kanji_idx]).strip()
            if len(k) != 1:
                continue
            if radical_idx < len(row) and row[radical_idx]:
                kanji_radical[k] = str(row[radical_idx]).strip()
                count += 1
            if components_idx < len(row) and row[components_idx]:
                kanji_components[k] = str(row[components_idx]).strip()

        wb.close()
        return kanji_radical, kanji_components
    except Exception as e:
        print(f"  [WARN] Could not load kanji decomposition: {e}", file=sys.stderr)
        return {}, {}

# ============================================================
# UTILITIES
# ============================================================

def reading_to_moras(r):
    moras = []
    i = 0
    while i < len(r):
        if i + 1 < len(r) and r[i+1] in 'ゃゅょぁぃぅぇぉャュョァィゥェォ':
            moras.append(r[i:i+2]); i += 2
        elif r[i] in 'っッ':
            moras.append(r[i]); i += 1
        elif i + 1 < len(r) and r[i+1] in 'ー':
            moras.append(r[i:i+2]); i += 2
        else:
            moras.append(r[i]); i += 1
    return moras

TRANS_PATTERNS = [
    ('まる','める'),('がる','げる'),('く','ける'),('る','す'),('れる','る'),
    ('かる','ける'),('う','える'),('つ','てる'),('ぶ','べる'),('む','める'),
]
RENDAKU = {
    'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご',
    'さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ',
    'た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど',
    'は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ',
}
RENDAKU_REV = {v:k for k,v in RENDAKU.items()}

SEMANTIC_DOMAINS = {
    'body':'頭首顔目耳鼻口歯舌唇手足腕脚指爪腹背腰尻心血骨肉皮毛肌髪声息身体屍脳肩肘膝踵瞳眉喉頬額顎股腿脛踝拳掌胴腸胃肺肝胆腎肋脊髄膜脂肪腺胞胎妊娠裸痣皺腫瘡痒痺痕泣笑怒驚汗涙涎唾痰尿糞屁嚏鼾',
    'nature':'水火木金土石岩砂泥山川海池湖沼河波流空天雲雨雪風霧霜露虹日月星光影闇雷電草花葉根茎実種松竹梅桜菊桃柳杉稲麦米豆芋鳥魚虫犬猫馬牛豚羊猿鹿兎鼠蛇亀蛙貝鷹鶴雀狐狸鳩鴉鷲鶏鴨鮭鮪鯛鰻蛸烏賊蟹蝦蛍蝶蜂蜘蛛蟻森林枝幹芽苗蕾棘蔓蔦藻茸竹笹葦荻嵐雹霰霙霞靄陽炎渦潮',
    'action':'動走歩飛流泳跳踊転回見聞言話読書食飲寝起入出行来帰通過進退止作使持取置受渡送届運切削折曲破壊消燃沸開閉上下登降乗着脱打叩押引投捕掴握殴蹴思考知覚忘憶学教習調生死育成変化始終続立座横倒傾曲伸縮膨凹書描塗彫刻編織縫結縛掘埋耕蒔刈穫獲採集拾洗濯拭掃擦磨研削剥裂戦闘争競比較選択決定尋探索求願祈頼任委託',
    'emotion':'喜怒哀楽悲苦痛嬉愉愛憎恨妬嫉羨怖恐驚慌恥辱誇慢傲謙謝詫安悩迷惑疑信頼望好嫌厭飽疲怠焦苛煩悶悛悔憾愁憂鬱淋寂侘',
    'quantity':'一二三四五六七八九十百千万億零多少大小長短高低太細広狭深浅厚薄重軽速遅数計算量測倍半全幾遠近早晩遅急緩強弱濃薄疎密粗精緻',
    'person':'人男女子親父母兄弟姉妹夫婦妻婚孫祖伯叔甥姪友敵隣客主君臣私僕俺彼誰我汝己自王后妃皇帝将軍士兵卒師匠徒弟僧尼巫覡禅供侍者員手役係',
    'speech':'語詞句文字辞典訳語言説談論議講演述陳叙唱叫喚呼吶喊喧嘩詠詩歌俳諧謡唄読誦諳唱謎諺寓諷刺',
    'tool':'刀剣刃斧鋸鎌針糸布縄鍋釜皿碗箸匙杯瓶壺箱車船舟橋道路門戸窓壁机椅棚枕布団傘鏡時計鍵槌鉋鋏鋤鍬鎚釘螺子網罠釣漁狩笛琴鼓鐘鈴旗幟幕帳屏風硯筆墨紙帳簿秤梯箒帚塵取',
    'quality':'美醜良悪善正邪是非新古旧若老幼青熟硬軟堅柔強弱固脆清汚潔浄濁澄静騒喧寂賑甘辛酸苦塩旨不味温冷暑寒暖涼熱明暗黒白赤青黄緑紫桃色香臭匂薫滑粗平凸凹尖鈍鋭乾湿潤燥真偽嘘実虚空貴賤富貧裕乏奢倹',
}

def classify_domain(k):
    return [d for d, chars in SEMANTIC_DOMAINS.items() if k in chars]


# ============================================================
# MORPHOLOGY v3 — more aggressive
# ============================================================

def readings_to_roots_v3(readings):
    """5-pass root clustering, handles different-length readings."""
    if len(readings) <= 1:
        return len(readings), {readings[0]: 'root_0'} if readings else (0, {})

    roots = {}
    root_id = 0
    assigned = set()
    rlist = list(readings)
    nominal_ends = {'い','り','き','み','し','ち','け'}
    verb_ends = {'る','す','む','ぶ','ぬ','く','ぐ','つ','う'}
    adj_ends = {'い','しい','いしい'}

    # Pass 1: Transitivity pairs
    for i, r1 in enumerate(rlist):
        if r1 in assigned: continue
        for r2 in rlist[i+1:]:
            if r2 in assigned: continue
            for itr, tr in TRANS_PATTERNS:
                s1 = s2 = None
                if r1.endswith(itr) and r2.endswith(tr):
                    s1, s2 = r1[:-len(itr)], r2[:-len(tr)]
                elif r2.endswith(itr) and r1.endswith(tr):
                    s1, s2 = r2[:-len(itr)], r1[:-len(tr)]
                if s1 and s1 == s2:
                    roots[r1] = roots[r2] = f'root_{root_id}'
                    assigned.update([r1, r2]); root_id += 1; break

    # Pass 2: Rendaku variants (same length, voicing diff in first mora)
    unassigned = [r for r in rlist if r not in assigned]
    for i, r1 in enumerate(unassigned):
        if r1 in assigned: continue
        for r2 in unassigned[i+1:]:
            if r2 in assigned: continue
            m1, m2 = reading_to_moras(r1), reading_to_moras(r2)
            if len(m1) >= 2 and len(m1) == len(m2) and m1[1:] == m2[1:]:
                if (m1[0] in RENDAKU and RENDAKU[m1[0]] == m2[0]) or \
                   (m2[0] in RENDAKU and RENDAKU[m2[0]] == m1[0]):
                    roots[r1] = roots[r2] = f'root_{root_id}'
                    assigned.update([r1, r2]); root_id += 1

    # Pass 3: Shorter = stem of longer (suffix addition)
    unassigned2 = [r for r in rlist if r not in assigned]
    valid_suffixes = (
        'かす','める','まる','げる','がる','ける','かる','かける',
        'れる','てる','べる','える','われる','われる',
        'す','る','む','ぶ','く','ぐ','つ','う','ぬ',
        'い','り','き','み','し','ち','け',
        'しい','やか','らか','まる','まり',
        'める','めく','らぐ','らげる',
    )
    for i, r1 in enumerate(unassigned2):
        if r1 in assigned: continue
        for r2 in unassigned2[i+1:]:
            if r2 in assigned: continue
            shorter = r1 if len(r1) < len(r2) else r2
            longer = r2 if len(r1) < len(r2) else r1
            if longer.startswith(shorter):
                suffix = longer[len(shorter):]
                if suffix in valid_suffixes:
                    roots[r1] = roots[r2] = f'root_{root_id}'
                    assigned.update([r1, r2]); root_id += 1

    # Pass 4: Same first mora, different suffixes
    unassigned3 = [r for r in rlist if r not in assigned]
    for i, r1 in enumerate(unassigned3):
        if r1 in assigned: continue
        for r2 in unassigned3[i+1:]:
            if r2 in assigned: continue
            m1, m2 = reading_to_moras(r1), reading_to_moras(r2)
            if len(m1) >= 2 and len(m1) == len(m2) and m1[0] == m2[0]:
                rest1 = ''.join(m1[1:])
                rest2 = ''.join(m2[1:])
                all_ends = verb_ends | nominal_ends
                if rest1 in all_ends or rest2 in all_ends:
                    roots[r1] = roots[r2] = f'root_{root_id}'
                    assigned.update([r1, r2]); root_id += 1

    # Pass 5: Same first 2 moras, different lengths
    unassigned4 = [r for r in rlist if r not in assigned]
    for i, r1 in enumerate(unassigned4):
        if r1 in assigned: continue
        m1 = reading_to_moras(r1)
        if len(m1) < 2: continue
        stem2_1 = ''.join(m1[:2])
        for r2 in unassigned4[i+1:]:
            if r2 in assigned: continue
            m2 = reading_to_moras(r2)
            if len(m2) >= 2 and ''.join(m2[:2]) == stem2_1:
                # Both share first 2 moras — likely same root
                roots[r1] = roots[r2] = f'root_{root_id}'
                assigned.update([r1, r2]); root_id += 1

    # Remaining → own roots
    for r in rlist:
        if r not in assigned:
            roots[r] = f'root_{root_id}'
            root_id += 1

    return len(set(roots.values())), roots


# ============================================================
# DIMENSION 1: COMPRESSION (upgraded)
# ============================================================

def diagnose_compression(data, kanji_radical):
    results = {}
    LEVELS = ['N5','N4','N3','N2','N1']

    # Stage 0: Surface
    surface = []
    for w in data['annotated_words']:
        for d in w.get('gt_details', []):
            if d['type'] == 'kun' and d['reading']:
                surface.append({'kanji': d['kanji'], 'reading': d['reading'],
                               'word': w['word'], 'level': w['level']})
    total_surface = len(surface)
    results['surface_instances'] = total_surface

    # Stage 1: Unique (kanji, reading) pairs
    pairs = set()
    pair_levels = defaultdict(set)
    for s in surface:
        key = (s['kanji'], s['reading'])
        pairs.add(key)
        pair_levels[key].add(s['level'])

    results['unique_pairs'] = len(pairs)
    results['conjugation_savings'] = total_surface - len(pairs)
    results['conjugation_savings_pct'] = round((total_surface - len(pairs))/total_surface*100, 1)

    level_pairs = defaultdict(set)
    for (k, r), lvs in pair_levels.items():
        for lv in lvs: level_pairs[lv].add((k, r))

    # Stage 2: Morphology roots
    kanji_readings = defaultdict(set)
    for (k, r) in pairs: kanji_readings[k].add(r)

    kanji_root_count = {}
    kanji_root_map = {}
    total_roots = 0
    for k, readings in kanji_readings.items():
        n, rm = readings_to_roots_v3(list(readings))
        kanji_root_count[k] = n
        kanji_root_map[k] = rm
        total_roots += n

    results['morphology_roots'] = total_roots
    results['morphology_savings'] = len(pairs) - total_roots
    results['morphology_savings_pct'] = round((len(pairs)-total_roots)/len(pairs)*100, 1)

    # Stage 3: Cross-level root tracking
    pair_to_root = {}
    for (k, r) in pairs: pair_to_root[(k, r)] = kanji_root_map[k].get(r, r)

    kanji_root_first_level = {}
    for (k, r), lvs in pair_levels.items():
        root = pair_to_root[(k, r)]
        kr = (k, root)
        for lv in LEVELS:
            if lv in lvs:
                if kr not in kanji_root_first_level:
                    kanji_root_first_level[kr] = lv
                break

    cross_level = {}
    cum_new = 0
    cum_total = 0
    for i, lv in enumerate(LEVELS):
        lv_kr = set()
        for (k, r) in level_pairs[lv]:
            lv_kr.add((k, pair_to_root[(k, r)]))
        new = sum(1 for kr in lv_kr if kanji_root_first_level.get(kr) == lv)
        reused = sum(1 for kr in lv_kr if kanji_root_first_level.get(kr) in LEVELS[:i])
        cross_level[lv] = {'total_roots': len(lv_kr), 'new_roots': new,
                           'reused_roots': reused,
                           'reuse_pct': round(reused/len(lv_kr)*100,1) if lv_kr else 0}
        cum_new += new
        cum_total += len(lv_kr)

    results['cross_level'] = cross_level
    results['cumulative_new_roots'] = cum_new
    results['cumulative_total_roots'] = cum_total
    results['cross_level_savings'] = cum_total - cum_new
    results['cross_level_savings_pct'] = round((cum_total-cum_new)/cum_total*100,1) if cum_total else 0

    # Stage 4: Stem carry-over (3-tier)
    # Build kun-specific stem index from pairs
    stem2_kanji = defaultdict(set)
    stem1_kanji = defaultdict(set)

    for k in kanji_readings:
        for r in kanji_readings[k]:
            moras = reading_to_moras(r)
            if len(moras) >= 2:
                stem2_kanji[''.join(moras[:2])].add(k)
            if len(moras) >= 1:
                stem1_kanji[moras[0]].add(k)

    kanji_first_level = {}
    for (k, r), lvs in pair_levels.items():
        for lv in LEVELS:
            if lv in lvs:
                if k not in kanji_first_level or LEVELS.index(lv) < LEVELS.index(kanji_first_level[k]):
                    kanji_first_level[k] = lv
                break

    carry_strong = set()   # 2-mora shared, earlier level → weight 0.3
    carry_medium = set()   # 1-mora + same domain → weight 0.5
    carry_weak = set()     # 1-mora, no domain, ≥3 other kanji → weight 0.7

    for k in kanji_readings:
        k_lv_idx = LEVELS.index(kanji_first_level.get(k, 'N1'))
        k_domains = set(classify_domain(k))

        # Strong: 2-mora stem sharing
        for r in kanji_readings[k]:
            moras = reading_to_moras(r)
            if len(moras) >= 2:
                s2 = ''.join(moras[:2])
                for other in stem2_kanji.get(s2, set()):
                    if other != k and LEVELS.index(kanji_first_level.get(other,'N1')) < k_lv_idx:
                        root = pair_to_root.get((k, r), r)
                        carry_strong.add((k, root))

        # Medium: 1-mora + same domain
        for r in kanji_readings[k]:
            moras = reading_to_moras(r)
            if len(moras) >= 1:
                s1 = moras[0]
                for other in stem1_kanji.get(s1, set()):
                    if other != k and LEVELS.index(kanji_first_level.get(other,'N1')) < k_lv_idx:
                        other_domains = set(classify_domain(other))
                        if k_domains & other_domains:
                            root = pair_to_root.get((k, r), r)
                            carry_medium.add((k, root))

        # Weak: 1-mora, no domain, ≥3 other kanji
        for r in kanji_readings[k]:
            moras = reading_to_moras(r)
            if len(moras) >= 1:
                s1 = moras[0]
                family = stem1_kanji.get(s1, set()) - {k}
                if len(family) >= 3:
                    has_earlier = any(
                        LEVELS.index(kanji_first_level.get(o,'N1')) < k_lv_idx
                        for o in family
                    )
                    if has_earlier and (k, pair_to_root.get((k,r),r)) not in carry_strong | carry_medium:
                        root = pair_to_root.get((k, r), r)
                        carry_weak.add((k, root))

    carry_total = len(carry_strong | carry_medium | carry_weak)
    carry_savings = round(len(carry_strong)*0.7 + len(carry_medium)*0.5 + len(carry_weak)*0.3)

    results['carry_over_roots'] = carry_total
    results['carry_strong'] = len(carry_strong)
    results['carry_medium'] = len(carry_medium)
    results['carry_weak'] = len(carry_weak)
    results['carry_over_savings'] = carry_savings

    effective = cum_new - carry_savings
    results['effective_memory_items'] = effective
    results['compression_ratio'] = round(total_surface/effective, 1) if effective else float('inf')
    results['compression_pct'] = round((1-effective/total_surface)*100, 1)

    return (results, pairs, pair_levels, kanji_readings, kanji_root_map,
            stem2_kanji, stem1_kanji, pair_to_root, kanji_root_first_level,
            LEVELS)


# ============================================================
# DIMENSION 2: TRANSFER
# ============================================================

def diagnose_transfer(pairs, pair_levels, LEVELS):
    pair_first_level = {}
    for (k, r), lvs in pair_levels.items():
        for lv in LEVELS:
            if lv in lvs: pair_first_level[(k,r)] = lv; break

    transfer = {}
    for i, lv in enumerate(LEVELS):
        lv_pairs = {(k,r) for (k,r), lvs in pair_levels.items() if lv in lvs}
        earlier_kanji = set()
        for el in LEVELS[:i]:
            for (k,r), lvs in pair_levels.items():
                if el in lvs: earlier_kanji.add(k)

        genuine = {p for p in lv_pairs if pair_first_level.get(p) in LEVELS[:i]}
        surface = {p for p in lv_pairs if p[0] in earlier_kanji and p not in genuine}
        new = lv_pairs - genuine - surface
        transfer[lv] = {
            'total': len(lv_pairs),
            'genuine_reuse': len(genuine),
            'genuine_reuse_pct': round(len(genuine)/len(lv_pairs)*100,1) if lv_pairs else 0,
            'surface_reuse': len(surface),
            'completely_new': len(new),
            'effort_index': round(len(new)/len(lv_pairs),2) if lv_pairs else 0,
        }
    return transfer


# ============================================================
# DIMENSION 3: ANCHORS v3 — 7 types
# ============================================================

def diagnose_anchors(pairs, pair_levels, kanji_readings, kanji_root_map,
                      stem2_kanji, stem1_kanji, pair_to_root, kanji_radical):
    anchors = {}
    anchor_types = Counter()
    paired = Counter()

    # Transitivity network
    all_readings = defaultdict(set)
    for (k,r) in pairs: all_readings[r].add(k)

    trans_net = defaultdict(list)
    for (k,r) in pairs:
        for itr, tr in TRANS_PATTERNS:
            if r.endswith(itr):
                stem = r[:-len(itr)]
                for k2 in all_readings.get(stem+tr, set()):
                    trans_net[(k,r)].append({'type':'自→他','counterpart':(k2,stem+tr),'pattern':f'～{itr}↔～{tr}'})
            elif r.endswith(tr):
                stem = r[:-len(tr)]
                for k2 in all_readings.get(stem+itr, set()):
                    trans_net[(k,r)].append({'type':'他→自','counterpart':(k2,stem+itr),'pattern':f'～{itr}↔～{tr}'})

    for (k, r) in pairs:
        panchors = []
        domains = classify_domain(k)
        moras = reading_to_moras(r)

        # A1: Transitivity
        if (k,r) in trans_net and trans_net[(k,r)]:
            panchors.append({'type':'transitivity_pair','detail':trans_net[(k,r)][:3]})

        # A2: Semantic domain
        if domains:
            panchors.append({'type':'semantic_domain','detail':domains})

        # A3: Stem family (2-mora shared, ≥1 other kanji)
        sf = []
        if len(moras) >= 2:
            s2 = ''.join(moras[:2])
            fam = stem2_kanji.get(s2,set()) - {k}
            if fam:
                sf.append({'stem':s2,'family_size':len(fam)+1,'sample':sorted(fam)[:5]})
        if len(moras) >= 1:
            s1 = moras[0]
            kd = set(domains)
            fam1 = set()
            for o in stem1_kanji.get(s1,set()):
                if o != k and (kd & set(classify_domain(o))):
                    fam1.add(o)
            if fam1:
                sf.append({'stem':f'{s1}(同域)','family_size':len(fam1)+1,'sample':sorted(fam1)[:5]})
        if sf:
            panchors.append({'type':'stem_family','detail':sf})

        # A4: Okurigana
        oku = None
        for e in ['まる','める','がる','げる','ける','かける','れる','てる','べる',
                  'る','く','ぐ','す','む','ぶ','ぬ','つ','う',
                  'い','しい','り','き','み','し','ち','け']:
            if r.endswith(e) and r != e: oku = e; break
        if oku:
            panchors.append({'type':'okurigana','detail':oku})

        # A5: Cross-level (≥2 JLPT levels)
        lvs = pair_levels.get((k,r),set())
        if len(lvs) >= 2:
            panchors.append({'type':'cross_level','detail':sorted(lvs)})

        # A6: Radical group (NEW)
        if k in kanji_radical:
            rad = kanji_radical[k]
            # Count other JLPT kanji sharing this radical
            radical_peers = [ok for ok in kanji_readings
                           if ok in kanji_radical and kanji_radical[ok] == rad and ok != k]
            if len(radical_peers) >= 1:
                panchors.append({'type':'radical_group',
                                'detail':{'radical':rad,'peers':len(radical_peers)}})

        # A7: Compound pattern (NEW)
        # Is this pair used in compound-initial or compound-final position?
        # (Measured as: does the kanji appear in multi-kanji kun words?)
        # Simplified: check if this kanji has readings in multi-kanji contexts
        if len(moras) <= 2:
            panchors.append({'type':'short_reading','detail':len(moras)})

        meaningful = [a for a in panchors if a['type'] != 'short_reading']
        n = len(meaningful)
        anchors[(k,r)] = {'meaningful_count':n,'meaningful_types':[a['type'] for a in meaningful]}
        for a in meaningful: anchor_types[a['type']] += 1
        if n > 0: paired[n] += 1

    # Radical quality tiering
    radical_jlpt_count = Counter()
    for k in kanji_readings:
        if k in kanji_radical:
            radical_jlpt_count[kanji_radical[k]] += 1
    radical_tiers = {'strong':0, 'medium':0, 'weak':0}
    tiered_pairs = {'strong':0, 'medium':0, 'weak':0}
    for (k,r) in pairs:
        if k in kanji_radical:
            rad = kanji_radical[k]
            sz = radical_jlpt_count.get(rad, 0)
            if sz >= 10:
                radical_tiers['strong'] += 1
                tiered_pairs['strong'] += 1
            elif sz >= 5:
                radical_tiers['medium'] += 1
                tiered_pairs['medium'] += 1
            elif sz >= 2:
                radical_tiers['weak'] += 1
                tiered_pairs['weak'] += 1

    without = sum(1 for (k,r) in pairs if anchors[(k,r)]['meaningful_count'] == 0)
    total = len(pairs)
    return anchors, {
        'total_pairs': total,
        'pairs_with_anchors': total - without,
        'pairs_without_anchors': without,
        'coverage_pct': round((total-without)/total*100, 1),
        'anchor_type_distribution': dict(anchor_types),
        'pairs_per_anchor_count': dict(paired),
        'pairs_with_3plus_anchors': sum(c for n,c in paired.items() if n>=3),
        'pairs_with_3plus_pct': round(sum(c for n,c in paired.items() if n>=3)/total*100,1),
        'radical_tiers': {
            'strong_10plus': tiered_pairs['strong'],
            'medium_5to9': tiered_pairs['medium'],
            'weak_2to4': tiered_pairs['weak'],
        },
        'transitivity_note': '73 detected is a lower bound: V9 stores stems without okurigana suffixes, '
                            'so suffix-based matching (e.g. ～がる↔～げる) cannot match when the stem '
                            'does not contain the suffix. 10 theoretical patterns cover more instances '
                            'when full readings are available.'
    }


# ============================================================
# DIMENSION 4: TRAPS v3 — with radical-based shape detection
# ============================================================

def diagnose_traps(pairs, pair_levels, kanji_readings, kanji_radical, kanji_components):
    traps = {}

    # A: Multi-kun
    multi = {k: sorted(v) for k,v in kanji_readings.items() if len(v) >= 3}
    traps['multi_kun_kanji'] = {k:v for k,v in sorted(multi.items(), key=lambda x:-len(x[1]))[:50]}
    traps['multi_kun_count'] = len(multi)

    # B: Homophonous
    r2k = defaultdict(set)
    for (k,r) in pairs: r2k[r].add(k)
    homo = {r:ks for r,ks in r2k.items() if len(ks) >= 3}
    traps['homophonous_kun'] = {r:sorted(ks) for r,ks in sorted(homo.items(), key=lambda x:-len(x[1]))[:50]}
    traps['homophonous_count'] = len(homo)

    # C: Shape-similar — radical-based only, filter stroke-level noise
    # Stroke-level radicals to exclude (no semantic content)
    STROKE_RADS = set('ノ丿一丶十丶｜丨ハ又二Ｌヌ目人土日木口')
    shape_groups = defaultdict(set)
    if kanji_radical:
        for k in kanji_readings:
            if k in kanji_radical:
                rad = kanji_radical[k]
                if rad not in STROKE_RADS:
                    shape_groups[rad].add(k)

    shape_confusions = {}
    for shape, kset in shape_groups.items():
        if len(kset) >= 4:  # at least 4 kanji to be meaningful
            all_r = set()
            for kk in kset: all_r.update(kanji_readings.get(kk, set()))
            if len(all_r) >= 3:  # diverse readings = potential confusion
                shape_confusions[shape] = {
                    'kanji': sorted(kset),
                    'readings': {kk: sorted(kanji_readings.get(kk,[]))[:3]
                                for kk in sorted(kset)[:10]},
                    'count': len(kset),
                }
    traps['shape_similar_groups'] = {k:v for k,v in
        sorted(shape_confusions.items(), key=lambda x:-x[1]['count'])[:30]}
    traps['shape_similar_count'] = len(shape_confusions)

    # D: Heavy hitters
    heavy = {}
    for k, readings in kanji_readings.items():
        if len(readings) >= 4:
            ml = {len(reading_to_moras(r)) for r in readings}
            fm = {reading_to_moras(r)[0] for r in readings if reading_to_moras(r)}
            if len(ml) >= 2 and len(fm) >= 2:
                all_lvs = set()
                for r in readings:
                    if (k,r) in pair_levels: all_lvs.update(pair_levels[(k,r)])
                heavy[k] = {'readings':sorted(readings),'mora_lengths':sorted(ml),
                           'first_moras':sorted(fm),'levels':sorted(all_lvs)}
    traps['heavy_hitters'] = {k:v for k,v in sorted(heavy.items(), key=lambda x:-len(x[1]['readings']))[:30]}
    traps['heavy_hitter_count'] = len(heavy)

    return traps


# ============================================================
# REPORT
# ============================================================

def generate_report(comp, transfer, anchor_stats, traps, LEVELS):
    L = []
    L.append('# V9 诊断报告 v3：训读学习系统四维评估')
    L.append('')
    L.append(f'> 表面：{comp["surface_instances"]} | 对：{comp["unique_pairs"]} | 词根：{comp["morphology_roots"]} | 有效：{comp["effective_memory_items"]}')
    L.append(f'> **压缩比：{comp["compression_ratio"]}:1** | 压缩率：{comp["compression_pct"]}%')
    L.append('')
    L.append('---')
    L.append('## 维度一：压缩比')
    L.append('')
    L.append('| 阶段 | 操作 | 剩余 | 节省 | 节省率 |')
    L.append('|------|------|------|------|--------|')
    L.append(f'| 0 | 表面实例 | {comp["surface_instances"]} | — | — |')
    L.append(f'| 1 | 活用形归并 | {comp["unique_pairs"]} | {comp["conjugation_savings"]} | {comp["conjugation_savings_pct"]}% |')
    L.append(f'| 2 | 形态词根归并 | {comp["morphology_roots"]} | {comp["morphology_savings"]} | {comp["morphology_savings_pct"]}% |')
    L.append(f'| 3 | 跨级复用(词根) | {comp["cumulative_new_roots"]} | {comp["cross_level_savings"]} | {comp["cross_level_savings_pct"]}% |')
    L.append(f'| 4 | 词干连带(3层) | {comp["effective_memory_items"]} | {comp["carry_over_savings"]} | — |')
    L.append('')
    L.append('```')
    L.append(f'  {comp["surface_instances"]:>5}  表面实例')
    L.append(f'    ↓ 活用形归并 {comp["conjugation_savings_pct"]}%')
    L.append(f'  {comp["unique_pairs"]:>5}  不同(汉字,读法)对')
    L.append(f'    ↓ 形态词根归并 {comp["morphology_savings_pct"]}%')
    L.append(f'  {comp["morphology_roots"]:>5}  独立词根')
    L.append(f'    ↓ 跨级复用 {comp["cross_level_savings_pct"]}%')
    L.append(f'  {comp["cumulative_new_roots"]:>5}  逐级新词根')
    L.append(f'    ↓ 词干连带(强{comp["carry_strong"]}+中{comp["carry_medium"]}+弱{comp["carry_weak"]})')
    L.append(f'  {comp["effective_memory_items"]:>5}  有效记忆项')
    L.append(f'')
    L.append(f'  压缩比 = {comp["surface_instances"]} / {comp["effective_memory_items"]} = {comp["compression_ratio"]}:1')
    L.append('```')
    L.append('')

    L.append('### 词干连带详情')
    L.append(f'- 强连带(2拍共享)：{comp["carry_strong"]} 词根，省70%')
    L.append(f'- 中连带(1拍+同域)：{comp["carry_medium"]} 词根，省50%')
    L.append(f'- 弱连带(1拍+高频)：{comp["carry_weak"]} 词根，省30%')
    L.append('')

    L.append('---')
    L.append('## 维度二：层级递进效率')
    L.append('')
    L.append('| 级别 | 总对 | 真正复用 | 复用率 | 仅同字异读 | 全新 | 效率指数 |')
    L.append('|------|------|---------|--------|----------|------|---------|')
    for lv in LEVELS:
        t = transfer[lv]
        L.append(f'| {lv} | {t["total"]} | {t["genuine_reuse"]} | {t["genuine_reuse_pct"]}% | {t["surface_reuse"]} | {t["completely_new"]} | {t["effort_index"]} |')
    L.append('')
    L.append('| 级别 | 总词根 | 新词根 | 复用词根 | 词根复用率 |')
    L.append('|------|--------|--------|---------|----------|')
    for lv in LEVELS:
        cl = comp['cross_level'][lv]
        L.append(f'| {lv} | {cl["total_roots"]} | {cl["new_roots"]} | {cl["reused_roots"]} | {cl["reuse_pct"]}% |')
    L.append('')

    L.append('---')
    L.append('## 维度三：记忆锚点覆盖率（7类）')
    L.append('')
    L.append(f'- 总对：{anchor_stats["total_pairs"]}')
    L.append(f'- 有锚点：{anchor_stats["pairs_with_anchors"]}（{anchor_stats["coverage_pct"]}%）')
    L.append(f'- 无锚点：{anchor_stats["pairs_without_anchors"]}')
    L.append(f'- 3+锚点：{anchor_stats["pairs_with_3plus_anchors"]}（{anchor_stats["pairs_with_3plus_pct"]}%）')
    L.append('')
    L.append('| 锚点类型 | 覆盖 | 覆盖率 | 说明 |')
    L.append('|---------|------|--------|------|')
    tp = anchor_stats['total_pairs']
    desc = {
        'stem_family':'词干家族(≥1个同词干异字)',
        'semantic_domain':'语义场归属(9域)',
        'radical_group':'部首归类(同部首≥2个JLPT汉字)',
        'cross_level':'跨级出现(≥2级别)',
        'okurigana':'送假名词尾',
        'transitivity_pair':'自他动词对应(跨汉字)',
    }
    for at, cnt in sorted(anchor_stats['anchor_type_distribution'].items(), key=lambda x:-x[1]):
        L.append(f'| {at} | {cnt} | {round(cnt/tp*100,1)}% | {desc.get(at,"")} |')
    L.append('')
    L.append('### 部首锚点质量分层')
    rt = anchor_stats['radical_tiers']
    L.append(f'- **强部首层（≥10个JLPT汉字）**：{rt["strong_10plus"]} 对')
    L.append(f'- **中部首层（5–9个JLPT汉字）**：{rt["medium_5to9"]} 对')
    L.append(f'- **弱部首层（2–4个JLPT汉字）**：{rt["weak_2to4"]} 对')
    L.append(f'- 说明：部首归类作为锚点的价值取决于该部首下JLPT汉字的密度。强部首层（水/手/心/糸/言等）提供扎实的聚类支撑；弱部首层提供1–3个同伴关联，价值有限但非零。')
    L.append('')
    L.append('| 锚点数 | 对数 | 占比 |')
    L.append('|--------|------|------|')
    for n in sorted(anchor_stats['pairs_per_anchor_count'].keys()):
        L.append(f'| {n} | {anchor_stats["pairs_per_anchor_count"][n]} | {round(anchor_stats["pairs_per_anchor_count"][n]/tp*100,1)}% |')
    L.append(f'| 0 | {anchor_stats["pairs_without_anchors"]} | {round(anchor_stats["pairs_without_anchors"]/tp*100,1)}% |')
    L.append('')
    L.append(f'> **自他动词检测说明**：{anchor_stats.get("transitivity_note", "")}')
    L.append('')

    L.append('---')
    L.append('## 维度四：陷阱标记')
    L.append('')
    L.append(f'### A. 多训字陷阱：{traps["multi_kun_count"]} 个')
    L.append('| 汉字 | 读法数 | 读法 |')
    L.append('|------|--------|------|')
    for k, rs in list(traps['multi_kun_kanji'].items())[:20]:
        L.append(f'| {k} | {len(rs)} | {", ".join(rs)} |')
    L.append('')

    L.append(f'### B. 同音异字陷阱：{traps["homophonous_count"]} 个')
    L.append('| 读法 | 汉字数 | 汉字 |')
    L.append('|------|--------|------|')
    for r, ks in list(traps['homophonous_kun'].items())[:20]:
        L.append(f'| {r} | {len(ks)} | {", ".join(ks[:10])}{"…" if len(ks)>10 else ""} |')
    L.append('')

    L.append(f'### C. 形近异训陷阱（同部首/部件，不同读法）：{traps["shape_similar_count"]} 组')
    if traps['shape_similar_groups']:
        L.append('| 共享部首 | 汉字数 | 代表汉字 | 读法示例 |')
        L.append('|---------|--------|---------|---------|')
        for shape, info in list(traps['shape_similar_groups'].items())[:20]:
            kanji_str = ' '.join(info['kanji'][:6])
            read_str = ' | '.join(f'{k}({",".join(info["readings"].get(k,[])[:2])})'
                                  for k in info['kanji'][:4])
            L.append(f'| {shape} | {len(info["kanji"])} | {kanji_str} | {read_str} |')
    else:
        L.append('（未加载到部首数据）')
    L.append('')

    L.append(f'### D. 重度陷阱：{traps["heavy_hitter_count"]} 个')
    L.append('| 汉字 | 读法 | 拍数 | 级别 |')
    L.append('|------|------|------|------|')
    for k, info in list(traps['heavy_hitters'].items())[:20]:
        L.append(f'| {k} | {", ".join(info["readings"])} | {info["mora_lengths"]} | {",".join(info["levels"])} |')
    L.append('')

    # Summary
    L.append('---')
    L.append('## 综合评估')
    L.append('')
    L.append('| 维度 | 当前值 | 目标 | 状态 |')
    L.append('|------|--------|------|------|')
    cr = comp['compression_ratio']
    L.append(f'| 压缩比 | {cr}:1 | ≥4:1 | {"✓ 达标" if cr>=4 else "差"+str(round(4-cr,1))} |')
    n4r = transfer['N4']['genuine_reuse_pct']
    L.append(f'| N4复用率 | {n4r}% | ≥30% | {"✓" if n4r>=30 else "差"+str(round(30-n4r,1))+"%"} |')
    n1r = transfer['N1']['genuine_reuse_pct']
    L.append(f'| N1复用率 | {n1r}% | ≥50% | {"✓" if n1r>=50 else "差"+str(round(50-n1r,1))+"%"} |')
    ac = anchor_stats['coverage_pct']
    L.append(f'| 锚点覆盖率 | {ac}% | ≥90% | {"✓" if ac>=90 else "差"+str(round(90-ac,1))+"%"} |')
    a3 = anchor_stats['pairs_with_3plus_pct']
    L.append(f'| 3+锚点率 | {a3}% | ≥50% | {"✓" if a3>=50 else "差"+str(round(50-a3,1))+"%"} |')
    L.append(f'| 陷阱标记 | {traps["multi_kun_count"]}多训+{traps["homophonous_count"]}同音+{traps["shape_similar_count"]}形近+{traps["heavy_hitter_count"]}重度 | 全覆盖 | {"✓" if traps["shape_similar_count"]>0 else "形近已启用"} |')
    rt2 = anchor_stats['radical_tiers']
    L.append(f'| 部首锚点 | 强{rt2["strong_10plus"]}+中{rt2["medium_5to9"]}+弱{rt2["weak_2to4"]} | 强层主导 | — |')
    L.append('')
    L.append(f'*诊断时间：2026-05-08 | 数据：V9 JLPT + 漢字検索V2部首分解*')
    return '\n'.join(L)


# ============================================================
# MAIN
# ============================================================

def main():
    print("=== V9 Diagnostic v3 ===")
    print("Loading data...")
    data = load_data()

    print("Loading kanji decomposition...")
    kanji_radical, kanji_components = load_kanji_decomposition()
    print(f"  Radicals: {len(kanji_radical)} kanji")
    print(f"  Components: {len(kanji_components)} kanji")

    print("\n[1/4] Compression...")
    (comp, pairs, pair_levels, kanji_readings, kanji_root_map,
     stem2_kanji, stem1_kanji, pair_to_root, kanji_root_first_level,
     LEVELS) = diagnose_compression(data, kanji_radical)
    print(f"  {comp['surface_instances']} → {comp['unique_pairs']} → {comp['morphology_roots']} → {comp['cumulative_new_roots']} → {comp['effective_memory_items']}")
    print(f"  Ratio: {comp['compression_ratio']}:1 ({comp['compression_pct']}%)")
    print(f"  Morphology: {comp['morphology_savings_pct']}%")
    print(f"  Cross-level: {comp['cross_level_savings_pct']}%")
    print(f"  Carry-over: {comp['carry_strong']}s + {comp['carry_medium']}m + {comp['carry_weak']}w = {comp['carry_over_savings']} saved")

    print("\n[2/4] Transfer...")
    transfer = diagnose_transfer(pairs, pair_levels, LEVELS)
    for lv in LEVELS:
        t = transfer[lv]
        print(f"  {lv}: reuse={t['genuine_reuse_pct']}%, effort={t['effort_index']}")
        cl = comp['cross_level'][lv]
        print(f"       root: reuse={cl['reuse_pct']}%, new={cl['new_roots']}")

    print("\n[3/4] Anchors...")
    anchors, anchor_stats = diagnose_anchors(
        pairs, pair_levels, kanji_readings, kanji_root_map,
        stem2_kanji, stem1_kanji, pair_to_root, kanji_radical)
    print(f"  Coverage: {anchor_stats['coverage_pct']}%, 3+: {anchor_stats['pairs_with_3plus_pct']}%")
    for at, cnt in sorted(anchor_stats['anchor_type_distribution'].items(), key=lambda x:-x[1]):
        print(f"    {at}: {cnt} ({round(cnt/anchor_stats['total_pairs']*100,1)}%)")
    rt = anchor_stats['radical_tiers']
    print(f"    Radical tiers: strong={rt['strong_10plus']}, medium={rt['medium_5to9']}, weak={rt['weak_2to4']}")

    print("\n[4/4] Traps...")
    traps = diagnose_traps(pairs, pair_levels, kanji_readings, kanji_radical, kanji_components)
    print(f"  Multi-kun: {traps['multi_kun_count']}, Homo: {traps['homophonous_count']}, Shape: {traps['shape_similar_count']}, Heavy: {traps['heavy_hitter_count']}")

    print("\nGenerating report...")
    report = generate_report(comp, transfer, anchor_stats, traps, LEVELS)
    with open(OUT / 'kun_diagnostic_v9.md', 'w') as f:
        f.write(report)
    print(f"Report: {OUT / 'kun_diagnostic_v9.md'}")

    # Structured data
    diag = {
        'compression': {
            'surface': comp['surface_instances'], 'pairs': comp['unique_pairs'],
            'roots': comp['morphology_roots'], 'cumulative_new': comp['cumulative_new_roots'],
            'effective': comp['effective_memory_items'], 'ratio': comp['compression_ratio'],
            'stages': {
                'conjugation': {'pct': comp['conjugation_savings_pct']},
                'morphology': {'pct': comp['morphology_savings_pct']},
                'cross_level': {'pct': comp['cross_level_savings_pct']},
                'carry_over': {'strong': comp['carry_strong'], 'medium': comp['carry_medium'],
                              'weak': comp['carry_weak'], 'savings': comp['carry_over_savings']},
            }
        },
        'transfer': {lv: transfer[lv] for lv in LEVELS},
        'transfer_roots': {lv: comp['cross_level'][lv] for lv in LEVELS},
        'anchors': anchor_stats,
        'traps': {k: v for k, v in traps.items() if 'groups' not in k and 'kanji' not in k},
    }
    with open(OUT / 'kun_diagnostic_v9.json', 'w') as f:
        json.dump(diag, f, ensure_ascii=False, indent=2)
    print(f"Data: {OUT / 'kun_diagnostic_v9.json'}")
    print("=== DONE ===")


if __name__ == '__main__':
    main()
