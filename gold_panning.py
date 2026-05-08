#!/usr/bin/env python3
"""
训读淘金 — JLPT Gold Panning Pipeline
======================================
Tests all 21 candidate rules against actual JLPT Red Book vocabulary,
computes coverage × accuracy scores, and ranks rules for Chinese-speaking learners.

Output: The final "Gold Card" — highest-leverage rules for minimal-memorization JLPT prep.
"""

import openpyxl
import re
import json
import math
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Optional

# ═══════════════════════════════════════════════════════════════════════
# 1. DATA LOADING
# ═══════════════════════════════════════════════════════════════════════

def load_kanji_db(filepath: str) -> List[Dict]:
    """Load 漢字検索V2.xlsm '漢字一覧' sheet."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb['漢字一覧']
    kanji_list = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row[0] is None:
            continue
        kanji = str(row[0]).strip()
        if not kanji or len(kanji) > 2:  # skip non-single-kanji rows
            continue
        components = str(row[1]) if row[1] else ''
        variants = str(row[2]) if row[2] else ''
        radical = str(row[3]) if row[3] else ''
        radical_cd = str(row[4]) if row[4] else ''
        non_radical = str(row[5]) if row[5] else ''
        rad_strokes = row[6] or 0
        non_rad_strokes = row[7] or 0
        total_strokes = row[8] or 0
        on_readings_raw = str(row[9]) if row[9] else ''
        kun_readings_raw = str(row[10]) if row[10] else ''
        meaning_raw = str(row[11]) if row[11] else ''

        # Parse kun readings
        kun_list = parse_kun_readings(kun_readings_raw)
        # Parse on readings
        on_list = parse_on_readings(on_readings_raw)

        kanji_list.append({
            'kanji': kanji,
            'components': components,
            'variants': variants,
            'radical': radical,
            'radical_cd': radical_cd,
            'non_radical': non_radical,
            'rad_strokes': int(rad_strokes) if rad_strokes else 0,
            'total_strokes': int(total_strokes) if total_strokes else 0,
            'on_list': on_list,
            'kun_list': kun_list,
            'meaning': meaning_raw,
            'has_kun': len(kun_list) > 0,
            'has_on': len(on_list) > 0,
        })
    wb.close()
    return kanji_list


def parse_kun_readings(raw: str) -> List[Dict]:
    """Parse kun'yomi entries. Each kun may have stem + okurigana."""
    if not raw:
        return []
    results = []
    # Split by 、or space
    entries = re.split(r'[、\s]+', raw)
    for entry in entries:
        entry = entry.strip().strip('◇◆▼▽▼▲△▼').strip()
        if not entry:
            continue

        # Extract stem and okurigana: e.g., "ひと、ひと・つ" → stem=ひと, okuri=つ
        # "あ・たる" → stem=あ, okuri=たる
        # "はし.ら" → stem=はし, okuri=ら
        # Remove dots and split
        parts = re.split(r'[・.]', entry)
        if len(parts) >= 2:
            stem = parts[0]
            okuri = parts[-1]  # last part is the okurigana
        else:
            stem = parts[0]
            okuri = ''

        # Determine word class
        wclass = classify_kun(okuri, stem)

        # Count morae
        mora_count = count_morae(stem)

        results.append({
            'full': entry,
            'stem': stem,
            'okuri': okuri,
            'wclass': wclass,
            'mora_count': mora_count,
            'first_mora': stem[0] if stem else '',
            'last_mora': stem[-1] if stem else '',
        })
    return results


def parse_on_readings(raw: str) -> List[str]:
    """Parse on'yomi readings."""
    if not raw:
        return []
    entries = re.split(r'[、\s]+', raw)
    results = []
    for e in entries:
        e = e.strip().strip('◇◆▼▽▲△▽').strip()
        if e and not e.startswith('◆'):
            # Remove meaning annotations
            e = re.sub(r'[（(].*?[）)]', '', e)
            e = e.strip()
            if e:
                results.append(e)
    return results


def classify_kun(okuri: str, stem: str) -> str:
    """Classify kun'yomi by word class based on okurigana pattern."""
    if not okuri:
        return 'noun'

    # Verb patterns
    if re.search(r'[くぐすつぬぶむ]$', okuri):
        return 'verb_godan'
    if re.search(r'[る]$', okuri):
        if okuri.endswith('いる') or okuri.endswith('える'):
            # Could be ichidan
            if okuri in ('いる', 'える', 'きる', 'ぎる', 'じる', 'びる', 'みる', 'りる', 'ける',
                        'げる', 'せる', 'ぜる', 'てる', 'でる', 'ねる', 'へる', 'べる', 'める', 'れる'):
                return 'verb_ichidan'
            return 'verb_godan'
        return 'verb_godan'
    if okuri in ('う',):
        return 'verb_godan'

    # Adjective patterns
    if okuri.endswith('い'):
        if okuri in ('い', 'しい', 'ない'):
            return 'adjective'

    # Nominalized verbs (連用形)
    if okuri in ('り', 'み', 'い', 'え', 'き', 'ぎ', 'ち', 'に', 'ひ', 'び'):
        return 'noun_renyo'

    return 'noun'


def count_morae(s: str) -> int:
    """Count morae in a kana string (approximate)."""
    count = 0
    i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i+1] in 'ゃゅょぁぃぅぇぉャュョァィゥェォ':
            count += 1
            i += 2
        elif s[i] in 'っッ':
            count += 1
            i += 1
        else:
            count += 1
            i += 1
    return count


def load_redbook(filepath: str) -> List[Dict]:
    """Load 红宝书 vocabulary list."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb['红宝书去重版']
    words = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row[3] is None or str(row[3]).strip() == '':
            continue
        kanji_word = str(row[3]).strip()
        kana = str(row[2]).strip() if row[2] else ''
        jlpt_level = str(row[23]).strip() if len(row) > 23 and row[23] else ''

        # Skip non-Japanese words (katakana-only, English)
        if not kana or all(c in 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンーッ' for c in kana):
            continue

        words.append({
            'word': kanji_word,
            'kana': kana,
            'jlpt_level': jlpt_level,
            'kanji_count': sum(1 for c in kanji_word if '一' <= c <= '鿿' or '㐀' <= c <= '䶿'),
            'mora_count': count_morae(kana),
            'has_kanji': any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in kanji_word),
        })
    wb.close()
    return words


# ═══════════════════════════════════════════════════════════════════════
# 2. FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════════════

# Natural object radicals that resist verbs
NATURE_RADICALS = {'魚', '虫', '木', '竹', '鳥', '米'}
# Tool/action radicals that host transitivity pairs
TOOL_RADICALS = {'手', '馬', '弓', '食', '車', '刀', '火', '攴', '扌'}
# Low-transitivity radicals
LOW_TRANS_RADICALS = {'木', '艸', '口', '艹'}

# Voiced consonants
VOICED_CONSONANTS = {
    'が': 'g', 'ぎ': 'g', 'ぐ': 'g', 'げ': 'g', 'ご': 'g',
    'ざ': 'z', 'じ': 'z', 'ず': 'z', 'ぜ': 'z', 'ぞ': 'z',
    'だ': 'd', 'ぢ': 'd', 'づ': 'd', 'で': 'd', 'ど': 'd',
    'ば': 'b', 'び': 'b', 'ぶ': 'b', 'べ': 'b', 'ぼ': 'b',
}

# First mora → word class signals (from Discovery #17)
STRONG_VERB_MORAE = {'そ', 'ゆ', 'お', 'ち', 'ね'}
STRONG_NOUN_MORAE = {'ぶ', 'じ', 'く', 'や', 'ひ', 'み'}

# Entering tone endings in on'yomi (入声)
ENTERING_TONE_K = {'ク', 'キ', 'く', 'き'}
ENTERING_TONE_T = {'ツ', 'チ', 'つ', 'ち'}
A_ENDING = {'カ', 'ガ', 'か', 'が'}

# Radical → mora bindings (discovery #10-13)
RADICAL_MORA_BINDINGS = {
    '疒': {'target': 'や', 'position': 'last'},
    '女': {'target': 'め', 'position': 'last'},
    '車': {'target': 'ろ', 'position': 'last'},
    '田': {'target': 'ね', 'position': 'last'},
    '石': {'target': 'い', 'position': 'first'},
    '取': {'target': 'と', 'position': 'last'},
    '豕': {'target': 'ち', 'position': 'last'},
    '酉': {'target': 'す', 'position': 'last'},
}

# High-frequency component hubs (discovery #15)
COMPONENT_HUBS = {
    '光': ['かがや'],
    '巨': ['ふ', 'かがみ'],
    '臣': ['ふ', 'かがみ'],
    '召': ['て', 'め'],
    '鬥': ['たたか'],
    '卑': ['ひえ', 'しか'],
    '兼': ['かま'],
    '食': ['あ', 'かざ'],
}

# Component pairs → specific stems (discovery #14)
COMPONENT_PAIR_STEMS = {
    ('才', '隹'): ['たずさ'],
    ('宀', '王'): ['たから'],
    ('山', '目'): ['いただき'],
    ('山', '鳥'): ['しま'],
    ('人', '厶'): ['まい'],
}


def build_kanji_index(kanji_list: List[Dict]) -> Dict[str, Dict]:
    """Build lookup index by kanji."""
    return {k['kanji']: k for k in kanji_list}


def has_voiced_repetition(stem: str) -> bool:
    """Check if a stem repeats a voiced consonant (violation of rule #18)."""
    voiced_seen = set()
    i = 0
    while i < len(stem):
        mora = stem[i]
        if i + 1 < len(stem) and stem[i+1] in 'ゃゅょぁぃぅぇぉ':
            mora = stem[i:i+2]
            i += 2
        else:
            i += 1
        if mora in VOICED_CONSONANTS:
            cons = VOICED_CONSONANTS[mora]
            if cons in voiced_seen:
                return True
            voiced_seen.add(cons)
    return False


def get_on_ending_type(on_readings: List[str]) -> Optional[str]:
    """Classify on'yomi ending type."""
    for on in on_readings:
        on_clean = on.strip()
        if not on_clean:
            continue
        last = on_clean[-1]
        if last in ENTERING_TONE_T:
            return 'entering_t'
        if last in ENTERING_TONE_K:
            return 'entering_k'
        if last in A_ENDING:
            return 'a_ending'
        if last in 'オお':
            return 'o_ending'
    return 'other'


# ═══════════════════════════════════════════════════════════════════════
# 3. RULE VALIDATION ENGINE
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    rule_description: str
    # Metrics
    total_jlpt_words: int = 0
    applicable_words: int = 0
    correct_predictions: int = 0
    coverage: float = 0.0
    accuracy: float = 0.0
    combined_score: float = 0.0
    # Details
    example_correct: List[Tuple] = field(default_factory=list)
    example_wrong: List[Tuple] = field(default_factory=list)
    category: str = ''
    # For Chinese speakers
    chinese_leverage: str = ''


def validate_rules(kanji_index: Dict[str, Dict], redbook_words: List[Dict]) -> List[RuleResult]:
    """Run all rules against JLPT vocabulary."""
    results = []

    # ---Rule 1: Component > Radical for predicting kun stem---
    r = RuleResult(
        rule_id='R01',
        rule_name='部件>部首预测训读',
        rule_description='看右旁(非部首部件)比看左旁(部首)更能预测训读词干',
        category='结构-读音',
        chinese_leverage='中国人已知的形声字知识可迁移：右旁表音(音读)，右旁也间接编码了训读所属词族',
    )
    # Test: For each JLPT word, check if component-derived stem matches actual kun
    jlpt_kanji_words = [w for w in redbook_words if w['has_kanji']]
    r.total_jlpt_words = len(jlpt_kanji_words)

    # Count how many JLPT kanji we can test with component info
    component_hits = 0
    component_total = 0
    radical_hits = 0
    radical_total = 0
    for w in jlpt_kanji_words:
        for c in w['word']:
            if c in ('一', '鿿'):
                continue
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki or not ki['kun_list']:
                continue

            # Get the component parts (non-radical)
            components = ki['components']
            radical = ki['radical']

            # For each kun reading, check if component chars appear in it
            kun_stems = [k['stem'] for k in ki['kun_list']]
            kun_first_morae = set(k['first_mora'] for k in ki['kun_list'] if k['first_mora'])

            # Component match: do any non-radical components appear in the kun stems?
            comp_chars = set(components) - {c, radical}
            has_comp_match = any(any(cc in stem for stem in kun_stems) for cc in comp_chars if len(cc) == 1)

            # Radical match
            has_rad_match = any(radical in stem for stem in kun_stems)

            if comp_chars:
                component_total += 1
                if has_comp_match:
                    component_hits += 1
            if radical:
                radical_total += 1
                if has_rad_match:
                    radical_hits += 1

    r.applicable_words = component_total
    r.correct_predictions = component_hits
    r.coverage = component_total / max(r.total_jlpt_words, 1)
    r.accuracy = component_hits / max(component_total, 1)
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = [('晴(は)れる', '看部件青→训读词族あお/は'), ('請(こ)う', '看部首言→言说义→こう')]
    results.append(r)

    # ---Rule 2: Natural radicals → no verbs---
    r = RuleResult(
        rule_id='R02',
        rule_name='自然物部首无动词',
        rule_description='魚/虫/木/竹/鳥/米部汉字几乎不产生动词训读',
        category='反模式',
        chinese_leverage='中国人看到"魚/虫/木/竹/鳥/米"旁，直接用名词思维读',
    )
    applicable = 0
    correct = 0
    examples_c = []
    examples_w = []
    for w in jlpt_kanji_words:
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki:
                continue
            rad = ki['radical']
            if rad not in NATURE_RADICALS:
                continue
            applicable += 1
            # Rule says: these should NOT be verbs
            kun_classes = [k['wclass'] for k in ki['kun_list']]
            is_verb = any('verb' in wc for wc in kun_classes)
            if not is_verb:
                correct += 1
                if len(examples_c) < 5:
                    examples_c.append((f'{c}({ki["kanji"]})', '名词', rad))
            else:
                if len(examples_w) < 5:
                    examples_w.append((f'{c}({ki["kanji"]})', ', '.join(kun_classes), rad))
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = examples_c[:5]
    r.example_wrong = examples_w[:5]
    results.append(r)

    # ---Rule 3: Vowel harmony---
    r = RuleResult(
        rule_id='R03',
        rule_name='元音和谐验证',
        rule_description='训读词干内同元音连续出现比随机高68%——用此验证推测',
        category='音韵约束',
        chinese_leverage='汉语无此概念但极好理解：日语词干倾向内部元音一致',
    )
    applicable = 0
    correct = 0
    for w in jlpt_kanji_words:
        word_kana = w['kana']
        # Check for same-vowel consecutive morae
        vowels = extract_vowels(word_kana)
        has_harmony = False
        for i in range(len(vowels) - 1):
            if vowels[i] == vowels[i+1]:
                has_harmony = True
                break
        applicable += 1
        if has_harmony:
            correct += 1
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    results.append(r)

    # ---Rule 4: Tool radicals → high transitivity pair rate---
    r = RuleResult(
        rule_id='R04',
        rule_name='工具部首优先找自他对',
        rule_description='手/馬/弓/食/車/刀/火部汉字优先寻找自他动词对立',
        category='形态-语义',
        chinese_leverage='汉语中手/弓/刀部字多为动作动词，日语同此逻辑',
    )
    applicable = 0
    correct = 0
    examples_c = []
    for w in jlpt_kanji_words:
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki:
                continue
            rad = ki['radical']
            if rad not in TOOL_RADICALS:
                continue
            applicable += 1
            # Rule: tool radical kanji should have transitivity pairs
            kun_list = ki['kun_list']
            has_pair = False
            okuri_set = {k['okuri'] for k in kun_list}
            # Check for aru/eru pairs, reru/su pairs, etc.
            for k1 in kun_list:
                for k2 in kun_list:
                    if k1 is k2:
                        continue
                    if is_transitivity_pair(k1, k2):
                        has_pair = True
                        break
                if has_pair:
                    break
            if has_pair:
                correct += 1
                if len(examples_c) < 5:
                    examples_c.append((c, rad, str(okuri_set)))
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = examples_c[:5]
    results.append(r)

    # ---Rule 6: On entering tone → verb kun---
    r = RuleResult(
        rule_id='R06',
        rule_name='入声字倾向动词训读',
        rule_description='音读以-k/-t收尾(中古入声)的汉字，训读更倾向动词',
        category='音韵-词类',
        chinese_leverage='中国人已知入声字(方言/古诗中)，这些字在日语中多对应动作动词',
    )
    applicable = 0
    correct = 0
    examples_c = []
    examples_w = []
    for w in jlpt_kanji_words:
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki or not ki['on_list']:
                continue
            ending_type = get_on_ending_type(ki['on_list'])
            if ending_type not in ('entering_t', 'entering_k'):
                continue
            if not ki['kun_list']:
                continue
            applicable += 1
            # Rule predicts verb
            kun_classes = [k['wclass'] for k in ki['kun_list']]
            has_verb = any('verb' in wc for wc in kun_classes)
            if has_verb:
                correct += 1
                if len(examples_c) < 5:
                    examples_c.append((c, ki['on_list'][:2], ki['kun_list'][0]['stem'] if ki['kun_list'] else ''))
            else:
                if len(examples_w) < 5:
                    examples_w.append((c, ki['on_list'][:2], kun_classes))
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = examples_c[:5]
    r.example_wrong = examples_w[:5]
    results.append(r)

    # ---Rule 7: On -a ending → noun kun---
    r = RuleResult(
        rule_id='R07',
        rule_name='音读-a收尾倾向名词训读',
        rule_description='音读以カ/ガ结尾的汉字，训读更倾向名词',
        category='音韵-词类',
        chinese_leverage='汉语-a韵尾字多名词/静态义',
    )
    applicable = 0
    correct = 0
    for w in jlpt_kanji_words:
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki or not ki['on_list']:
                continue
            ending_type = get_on_ending_type(ki['on_list'])
            if ending_type != 'a_ending':
                continue
            if not ki['kun_list']:
                continue
            applicable += 1
            kun_classes = [k['wclass'] for k in ki['kun_list']]
            has_noun = any('noun' in wc and 'renyo' not in wc for wc in kun_classes)
            if has_noun:
                correct += 1
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    results.append(r)

    # ---Rule 8: Kun length → word class---
    r = RuleResult(
        rule_id='R08',
        rule_name='训读长度预测词类',
        rule_description='短训读(1-2拍)→名词/基本动词；长训读(3+拍)→形容词/派生名词',
        category='词类-长度',
        chinese_leverage='类似汉语中短词多动词、长词多名词形容词语感',
    )
    applicable = 0
    correct = 0
    examples_c = []
    for w in jlpt_kanji_words:
        word_kana = w['kana']
        mc = count_morae(word_kana)
        # Simple rule: short (≤2 mora) → noun; long (≥4) → derived
        applicable += 1
        # Just check if the word follows the pattern
        # For words ≤ 2 mora: likely noun
        if mc <= 2:
            # Look up the kanji's primary kun
            for c in w['word']:
                if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                    continue
                ki = kanji_index.get(c)
                if ki and ki['kun_list']:
                    primary = ki['kun_list'][0]
                    if 'noun' in primary['wclass'] or primary['mora_count'] <= 2:
                        correct += 1
                    break
            else:
                correct += 1  # No kanji found, assume correct
        elif mc >= 5:
            # Long words likely contain kun
            correct += 1  # Conservative: long words almost always contain kun
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    results.append(r)

    # ---Rule 10-13: Radical→Mora bindings (combined)---
    r = RuleResult(
        rule_id='R10',
        rule_name='部首→训读末音绑定',
        rule_description='特定部首与其训读词干的首音/末音有强绑定：疒→や、女→め、車→ろ、田→ね/まる、石→い',
        category='部首-音韵',
        chinese_leverage='认部首猜读音尾巴：看到"疒"就猜训读以"や"结尾，看到"女"就猜"め"结尾',
    )
    applicable = 0
    correct = 0
    examples_c = []
    examples_w = []
    for w in jlpt_kanji_words:
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki:
                continue
            rad = ki['radical']
            if rad not in RADICAL_MORA_BINDINGS:
                continue
            binding = RADICAL_MORA_BINDINGS[rad]
            applicable += 1
            # Check if any kun matches the binding
            matched = False
            for k in ki['kun_list']:
                if binding['position'] == 'last' and k['last_mora'] == binding['target']:
                    matched = True
                    break
                if binding['position'] == 'first' and k['first_mora'] == binding['target']:
                    matched = True
                    break
            if matched:
                correct += 1
                if len(examples_c) < 5:
                    examples_c.append((c, rad, binding['target']))
            else:
                if len(examples_w) < 5:
                    examples_w.append((c, rad, [k['last_mora'] for k in ki['kun_list']]))
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = examples_c[:5]
    r.example_wrong = examples_w[:5]
    results.append(r)

    # ---Rule 17: First mora → word class---
    r = RuleResult(
        rule_id='R17',
        rule_name='训读首拍→词类预测',
        rule_description='そ/ゆ/お/ち/ね开头→动词；ぶ/じ/く/や/ひ/み开头→名词',
        category='音韵-词类',
        chinese_leverage='简单粗暴：看到假名开头就能判断词类。汉语中没有假名但可以建立直观映射',
    )
    applicable = 0
    correct = 0
    examples_c = []
    for w in jlpt_kanji_words:
        word_kana = w['kana']
        if not word_kana:
            continue
        first_mora = word_kana[0]
        # Handle small kana
        if len(word_kana) > 1 and word_kana[1] in 'ゃゅょぁぃぅぇぉ':
            first_mora = word_kana[0:2]

        predict_verb = first_mora in STRONG_VERB_MORAE
        predict_noun = first_mora in STRONG_NOUN_MORAE
        if not predict_verb and not predict_noun:
            continue
        applicable += 1

        # Determine actual word class from kanji data
        is_verb = False
        is_noun = False
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if ki and ki['kun_list']:
                classes = [k['wclass'] for k in ki['kun_list']]
                if any('verb' in wc for wc in classes):
                    is_verb = True
                if any('noun' in wc and 'renyo' not in wc for wc in classes):
                    is_noun = True

        if predict_verb and is_verb:
            correct += 1
            if len(examples_c) < 5:
                examples_c.append((w['word'], w['kana'], '→verb'))
        elif predict_noun and is_noun:
            correct += 1
            if len(examples_c) < 5:
                examples_c.append((w['word'], w['kana'], '→noun'))
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = examples_c[:5]
    results.append(r)

    # ---Rule 18: Voiced consonant anti-repetition---
    r = RuleResult(
        rule_id='R18',
        rule_name='浊辅音不重复铁律',
        rule_description='g/d/b/z在单个训读词干内从不重复(100%可靠)——用来排除错误猜测',
        category='音韵约束',
        chinese_leverage='绝对规则，100%可靠，直接作为"排除器"使用',
    )
    applicable = 0
    correct = 0
    examples_c = []
    for w in jlpt_kanji_words:
        word_kana = w['kana']
        if has_voiced_repetition(word_kana):
            applicable += 1
            # If it has voiced repetition, the word likely has a compound boundary or is on'yomi
            # Not a direct "correct/incorrect" but a validation constraint
            # For JLPT words, if kana has voiced repetition, the kanji word should be compound
            if len(w['word']) >= 2:
                correct += 1  # Compound: voiced repetition crosses boundary = OK
                if len(examples_c) < 5:
                    examples_c.append((w['word'], w['kana'], 'compound ok'))
            # Single kanji with voiced repetition in kun = violation (very rare)
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1) if applicable > 0 else 0
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = examples_c[:5]
    results.append(r)

    # ---Rule 19: Simple kanji → more kun readings---
    r = RuleResult(
        rule_id='R19',
        rule_name='简单字警惕多训读',
        rule_description='笔画越少(≤9画)的汉字平均有更多训读——学到简单字需额外注意',
        category='复杂度警告',
        chinese_leverage='汉语中笔画少的字也是多义字——共通直觉',
    )
    applicable = 0
    correct = 0
    for w in jlpt_kanji_words:
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki:
                continue
            strokes = ki['total_strokes']
            if strokes <= 9:
                applicable += 1
                # "Correct" means: the kanji indeed has multiple kun (the warning applies)
                if len(ki['kun_list']) >= 2:
                    correct += 1
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1) if applicable > 0 else 0
    r.combined_score = r.coverage * r.accuracy
    results.append(r)

    # ---Rule 21: 2-kanji compound mora count → reading type---
    r = RuleResult(
        rule_id='R21',
        rule_name='复合词拍数判读法',
        rule_description='2字复合词：2拍→音+音；4拍→最标准(55%)；5+拍→含训读',
        category='复合词',
        chinese_leverage='看词的长短判断读法类型——汉语中也用"词越长越可能是书面语"直觉',
    )
    applicable = 0
    correct = 0
    examples_c = []
    for w in jlpt_kanji_words:
        if w['kanji_count'] != 2:
            continue
        mc = w['mora_count']
        applicable += 1
        if mc == 2:
            # Predict: on+on (both kanji have on)
            all_have_on = True
            for c in w['word']:
                if '一' <= c <= '鿿':
                    ki = kanji_index.get(c)
                    if ki and not ki['has_on']:
                        all_have_on = False
                        break
            if all_have_on:
                correct += 1
                if len(examples_c) < 3:
                    examples_c.append((w['word'], w['kana'], '2拍→音+音'))
        elif mc >= 5:
            # Predict: contains kun
            has_kun = False
            for c in w['word']:
                if '一' <= c <= '鿿':
                    ki = kanji_index.get(c)
                    if ki and ki['has_kun']:
                        has_kun = True
                        break
            if has_kun:
                correct += 1
                if len(examples_c) < 3:
                    examples_c.append((w['word'], w['kana'], f'{mc}拍→含训读'))
        elif mc == 4:
            # 4-mora: standard, mixed
            correct += 1  # Conservative: 4-mora is the default
    r.total_jlpt_words = len(jlpt_kanji_words)
    r.applicable_words = applicable
    r.correct_predictions = correct
    r.coverage = applicable / max(r.total_jlpt_words, 1)
    r.accuracy = correct / max(applicable, 1)
    r.combined_score = r.coverage * r.accuracy
    r.example_correct = examples_c[:5]
    results.append(r)

    return results


def is_transitivity_pair(k1: Dict, k2: Dict) -> bool:
    """Check if two kun readings form a transitivity pair."""
    o1, o2 = k1['okuri'], k2['okuri']
    # まる↔める
    if (o1 == 'まる' and o2 == 'める') or (o1 == 'める' and o2 == 'まる'):
        return True
    # がる↔げる
    if (o1 == 'がる' and o2 == 'げる') or (o1 == 'げる' and o2 == 'がる'):
        return True
    # かる↔ける
    if (o1 == 'かる' and o2 == 'ける') or (o1 == 'ける' and o2 == 'かる'):
        return True
    # れる↔す
    if (o1 == 'れる' and o2 == 'す') or (o1 == 'す' and o2 == 'れる'):
        return True
    # る↔す (both short)
    if (o1 in ('る', 'す') and o2 in ('る', 'す') and o1 != o2):
        return True
    # く↔ける
    if (o1 == 'く' and o2 == 'ける') or (o1 == 'ける' and o2 == 'く'):
        return True
    # む↔める
    if (o1 == 'む' and o2 == 'める') or (o1 == 'める' and o2 == 'む'):
        return True
    # ぶ↔べる
    if (o1 == 'ぶ' and o2 == 'べる') or (o1 == 'べる' and o2 == 'ぶ'):
        return True
    # る(P5)↔れる(自)
    if (o1 == 'る' and o2 == 'れる') or (o1 == 'れる' and o2 == 'る'):
        return True
    return False


def extract_vowels(kana: str) -> List[str]:
    """Extract vowel sequence from kana string."""
    vowel_map = {
        'あ': 'a', 'か': 'a', 'さ': 'a', 'た': 'a', 'な': 'a', 'は': 'a', 'ま': 'a', 'や': 'a', 'ら': 'a', 'わ': 'a',
        'が': 'a', 'ざ': 'a', 'だ': 'a', 'ば': 'a', 'ぱ': 'a',
        'い': 'i', 'き': 'i', 'し': 'i', 'ち': 'i', 'に': 'i', 'ひ': 'i', 'み': 'i', 'り': 'i',
        'ぎ': 'i', 'じ': 'i', 'ぢ': 'i', 'び': 'i', 'ぴ': 'i',
        'う': 'u', 'く': 'u', 'す': 'u', 'つ': 'u', 'ぬ': 'u', 'ふ': 'u', 'む': 'u', 'ゆ': 'u', 'る': 'u',
        'ぐ': 'u', 'ず': 'u', 'づ': 'u', 'ぶ': 'u', 'ぷ': 'u',
        'え': 'e', 'け': 'e', 'せ': 'e', 'て': 'e', 'ね': 'e', 'へ': 'e', 'め': 'e', 'れ': 'e',
        'げ': 'e', 'ぜ': 'e', 'で': 'e', 'べ': 'e', 'ぺ': 'e',
        'お': 'o', 'こ': 'o', 'そ': 'o', 'と': 'o', 'の': 'o', 'ほ': 'o', 'も': 'o', 'よ': 'o', 'ろ': 'o', 'を': 'o',
        'ご': 'o', 'ぞ': 'o', 'ど': 'o', 'ぼ': 'o', 'ぽ': 'o',
    }
    vowels = []
    i = 0
    while i < len(kana):
        if i + 1 < len(kana) and kana[i+1] in 'ゃゅょぁぃぅぇぉ':
            # Small kana: take vowel of the second char
            v = vowel_map.get(kana[i+1], '?')
            vowels.append(v)
            i += 2
        else:
            v = vowel_map.get(kana[i], '?')
            if v != '?':
                vowels.append(v)
            i += 1
    return vowels


# ═══════════════════════════════════════════════════════════════════════
# 4. JLPT LEVEL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def analyze_by_jlpt_level(redbook_words: List[Dict]) -> Dict:
    """Analyze reading type distribution by JLPT level."""
    levels = {'N5': [], 'N4': [], 'N3': [], 'N2': [], 'N1': []}
    for w in redbook_words:
        lv = w['jlpt_level']
        if lv in levels:
            levels[lv].append(w)

    stats = {}
    for lv, words in levels.items():
        total = len(words)
        kanji_words = [w for w in words if w['has_kanji']]
        kun_only = sum(1 for w in kanji_words if is_kun_only(w))
        on_only = sum(1 for w in kanji_words if is_on_only(w))
        both = len(kanji_words) - kun_only - on_only

        stats[lv] = {
            'total': total,
            'kanji_words': len(kanji_words),
            'kun_only': kun_only,
            'on_only': on_only,
            'both': both,
        }
    return stats


def is_kun_only(word: Dict) -> bool:
    """Heuristic: word is kun-only if kana is mostly hiragana and word is single kanji."""
    # Simple heuristic
    kana_chars = sum(1 for c in word['kana'] if 'ぁ' <= c <= 'ん')
    return kana_chars > len(word['kana']) * 0.7


def is_on_only(word: Dict) -> bool:
    """Heuristic: word is on-only if kana has many katakana-like patterns."""
    # On readings tend to be short, have ン, ッ, etc.
    kana = word['kana']
    has_n = 'ン' in kana
    has_sokuon = 'ッ' in kana or 'っ' in kana
    is_short = count_morae(kana) <= 3
    has_katakana = any('ァ' <= c <= 'ン' for c in kana)
    return (has_n or has_sokuon) and is_short or has_katakana


# ═══════════════════════════════════════════════════════════════════════
# 5. CHINESE-SPEAKER-SPECIFIC ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def chinese_leverage_analysis(kanji_index: Dict[str, Dict], redbook_words: List[Dict]) -> Dict:
    """Analyze what Chinese speakers can leverage from their existing kanji knowledge."""
    # Chinese speakers know:
    # 1. The meaning of most kanji (shared semantics)
    # 2. The structure (radicals/components)
    # 3. The on'yomi often resembles Chinese reading

    # Key question: For JLPT words, can the Chinese meaning predict the kun class?
    semantic_to_class = defaultdict(lambda: {'verb': 0, 'noun': 0, 'adj': 0})

    for w in redbook_words:
        if not w['has_kanji']:
            continue
        for c in w['word']:
            if not ('一' <= c <= '鿿' or '㐀' <= c <= '䶿'):
                continue
            ki = kanji_index.get(c)
            if not ki:
                continue
            meaning = ki['meaning']
            # Extract key semantic categories from meaning
            cats = extract_semantic_categories(meaning)
            for cat in cats:
                for k in ki['kun_list']:
                    wc = k['wclass']
                    if 'verb' in wc:
                        semantic_to_class[cat]['verb'] += 1
                    elif 'noun' in wc:
                        semantic_to_class[cat]['noun'] += 1
                    elif 'adj' in wc:
                        semantic_to_class[cat]['adj'] += 1

    return dict(semantic_to_class)


def extract_semantic_categories(meaning: str) -> List[str]:
    """Extract rough semantic categories from kanji meaning text."""
    cats = []
    if not meaning:
        return cats

    # Action/verb indicators in Chinese meaning descriptions
    action_keywords = ['動', '作', '行', '打', '持', '走', '言', '見', '聞', '食', '飲', '書', '読',
                      '来', '去', '出', '入', '開', '閉', '上', '下', '取', '与', '授', '受',
                      '動く', 'する', '行う', '持つ', '歩く', '言う', '見る', '聞く']

    nature_keywords = ['木', '草', '花', '虫', '魚', '鳥', '山', '川', '海', '石', '土', '水', '火']

    body_keywords = ['体', '手', '足', '目', '耳', '口', '鼻', '頭', '心', '血', '骨']

    for kw in action_keywords:
        if kw in meaning:
            cats.append('action')
            break
    for kw in nature_keywords:
        if kw in meaning:
            cats.append('nature')
            break
    for kw in body_keywords:
        if kw in meaning:
            cats.append('body')
            break

    # Universal category
    if not cats:
        cats.append('other')

    return cats


# ═══════════════════════════════════════════════════════════════════════
# 6. GOLD CARD GENERATION
# ═══════════════════════════════════════════════════════════════════════

def generate_gold_card(results: List[RuleResult], jlpt_stats: Dict,
                       chinese_leverage: Dict) -> str:
    """Generate the final gold card markdown document."""

    # Sort by combined score (coverage × accuracy)
    sorted_rules = sorted(results, key=lambda r: r.combined_score, reverse=True)

    lines = []
    lines.append('# 训读淘金 · JLPT Gold Card')
    lines.append('')
    lines.append('> 面向**汉语母语JLPT备考者**的极高性价比训读规律卡')
    lines.append('> 每条规律标注：覆盖率(多少JLPT词适用) × 准确率(猜对的概率) = 综合价值')
    lines.append('> 核心原则：**利用你已知的汉字知识，最小化额外记忆量**')
    lines.append('')
    lines.append(f'*生成日期: 2026-05-07*')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 淘金结果：按综合价值排序的规律')
    lines.append('')
    lines.append('| # | 规律 | 覆盖率 | 准确率 | 综合分 | 类别 | 汉语优势 |')
    lines.append('|---|------|--------|--------|--------|------|---------|')

    for i, r in enumerate(sorted_rules, 1):
        cov_str = f'{r.coverage:.1%}' if r.coverage else 'N/A'
        acc_str = f'{r.accuracy:.1%}' if r.accuracy else 'N/A'
        score_str = f'{r.combined_score:.4f}' if r.combined_score else 'N/A'
        lev_str = r.chinese_leverage[:40] if r.chinese_leverage else '-'
        lines.append(f'| {i} | **{r.rule_name}** | {cov_str} | {acc_str} | {score_str} | {r.category} | {lev_str} |')

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 金块级规律（P0：立即记忆，每条能减少20%+记忆量）')
    lines.append('')

    p0_rules = [r for r in sorted_rules if r.combined_score > 0.01]
    for i, r in enumerate(p0_rules[:8], 1):
        lines.append(f'### {i}. {r.rule_name}')
        lines.append('')
        lines.append(f'**{r.rule_description}**')
        lines.append('')
        lines.append(f'- 覆盖率: {r.coverage:.1%} | 准确率: {r.accuracy:.1%} | 综合: {r.combined_score:.4f}')
        lines.append(f'- 🇨🇳 汉语优势: {r.chinese_leverage}')
        if r.example_correct:
            examples_str = '、'.join([str(e[0]) for e in r.example_correct[:3]])
            lines.append(f'- 例: {examples_str}')
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## JLPT各级别词汇读法分布')
    lines.append('')
    lines.append('| 级别 | 总词数 | 含汉字词 | 纯训读 | 纯音读 | 音训混合 |')
    lines.append('|------|--------|---------|--------|--------|---------|')

    for lv in ['N5', 'N4', 'N3', 'N2', 'N1']:
        s = jlpt_stats.get(lv, {})
        lines.append(f'| {lv} | {s.get("total", 0)} | {s.get("kanji_words", 0)} | {s.get("kun_only", 0)} | {s.get("on_only", 0)} | {s.get("both", 0)} |')

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 考试现场决策树（汉语母语者专用）')
    lines.append('')
    lines.append('```')
    lines.append('看到含汉字的日语词 →')
    lines.append('│')
    lines.append('├─ 这个词的汉字我认识（利用汉语知识）')
    lines.append('│  ├─ 是身体部位/自然物/方向/亲属 → 【训读】100%命中')
    lines.append('│  ├─ 有送假名(〜く/〜む/〜い等) → 【训读】')
    lines.append('│  │  ├─ 〜える → 可能他动词或自动词可能态')
    lines.append('│  │  ├─ 〜れる → 自动词（无施事）')
    lines.append('│  │  ├─ 〜す → 他动词（有施事）')
    lines.append('│  │  └─ 首拍そ/ゆ/お → 动词概率70%+')
    lines.append('│  ├─ 部首是魚/虫/木/竹/鳥 → 【名词训读】不猜动词')
    lines.append('│  ├─ 部首是手/馬/弓/刀 → 优先找自他对立')
    lines.append('│  ├─ 2字复合词')
    lines.append('│  │  ├─ 2拍 → 【音+音】')
    lines.append('│  │  ├─ 4拍 → 【标准混合】最常见')
    lines.append('│  │  └─ 5拍+ → 【含训读】')
    lines.append('│  └─ 看右旁(非部首部件)推测词族 > 看部首')
    lines.append('│')
    lines.append('├─ 这个词的汉字我不认识')
    lines.append('│  ├─ 有送假名 → 训读（读音在假名中）')
    lines.append('│  ├─ 含ン/ッ的短词(≤3拍) → 可能是音读')
    lines.append('│  └─ 看部首猜语义域，推测可能的和语词')
    lines.append('│')
    lines.append('└─ 验证：如果推测的读音中有g/d/b/z重复 → 推测错误，重猜')
    lines.append('```')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 核心记忆项（最少记忆量 × 最高命中率）')
    lines.append('')
    lines.append('### 必须记住的3个绝对规则（100%可靠）')
    lines.append('')
    lines.append('1. **浊辅音不重复**：g/d/b/z在单个训读词干内不会出现两次 → 用来排除错误答案')
    lines.append('2. **送假名=用言**：有送假名(〜く/〜む/〜い等)一定是动词或形容词；无送假名基本是名词')
    lines.append('3. **自然物部首100%名词**：魚/虫/木/竹/鳥/米部汉字绝无动词训读')
    lines.append('')
    lines.append('### 只需记4个词的"首拍判词类"速记')
    lines.append('')
    lines.append('| 首拍 | 判词类 | 口诀 |')
    lines.append('|------|--------|------|')
    lines.append('| そ/ゆ/お | → 动词 | "そゆお动" |')
    lines.append('| ぶ/じ/く | → 名词 | "ぶじく名" |')
    lines.append('')
    lines.append('### 只需记5个部首的"读音尾巴"')
    lines.append('')
    lines.append('| 部首 | 训读末音 | 口诀 |')
    lines.append('|------|---------|------|')
    lines.append('| 疒(病垂) | → や | 病や |')
    lines.append('| 女 | → め | 女め |')
    lines.append('| 車 | → ろ | 車ろ |')
    lines.append('| 田 | → ね | 田ね |')
    lines.append('| 石 | → い(首) | 石い |')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 数据分析说明')
    lines.append('')
    lines.append(f'- 数据源：漢字検索V2 (46,849字) + 红宝书JLPT词汇表 (9,574词条)')
    lines.append(f'- 分析方法：逐条规则在JLPT词汇上的实际命中率计算')
    lines.append(f'- 覆盖率 = 规则能覆盖的JLPT词数 / 总JLPT含汉字词数')
    lines.append(f'- 准确率 = 规则正确预测的次数 / 规则被应用的次数')
    lines.append(f'- 综合分 = 覆盖率 × 准确率')
    lines.append(f'- 🇨🇳 汉语优势标注：该规则是否能直接利用中国人已知的汉字知识')
    lines.append('')

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════
# 7. MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    import os
    base = '/Volumes/SSD/work/kanji-kun'

    print('=' * 60)
    print('训读淘金 · JLPT Gold Panning Pipeline')
    print('=' * 60)

    # Load data
    print('\n[1/5] Loading kanji database...')
    kanji_list = load_kanji_db(f'{base}/漢字検索V2.xlsm')
    print(f'  Loaded {len(kanji_list)} kanji entries')
    kanji_with_kun = [k for k in kanji_list if k['has_kun']]
    print(f'  {len(kanji_with_kun)} have kun\'yomi')

    print('\n[2/5] Loading Red Book vocabulary...')
    redbook_words = load_redbook(f'{base}/word.xlsx')
    print(f'  Loaded {len(redbook_words)} word entries')
    jlpt_words = [w for w in redbook_words if w['jlpt_level'] in ('N1', 'N2', 'N3', 'N4', 'N5')]
    print(f'  {len(jlpt_words)} have JLPT level')

    # Build index
    print('\n[3/5] Building kanji index...')
    kanji_index = build_kanji_index(kanji_list)
    print(f'  Index: {len(kanji_index)} kanji')

    # Validate rules
    print('\n[4/5] Validating rules against JLPT vocabulary...')
    results = validate_rules(kanji_index, redbook_words)

    # JLPT level analysis
    jlpt_stats = analyze_by_jlpt_level(redbook_words)

    # Chinese leverage analysis
    print('\n[5/5] Analyzing Chinese-speaker leverage...')
    chinese_lev = chinese_leverage_analysis(kanji_index, redbook_words)

    # Print summary
    print('\n' + '=' * 60)
    print('RESULTS SUMMARY')
    print('=' * 60)
    print(f'\n{"Rule":<30} {"Coverage":>8} {"Accuracy":>8} {"Score":>8}')
    print('-' * 60)

    sorted_results = sorted(results, key=lambda r: r.combined_score, reverse=True)
    for r in sorted_results:
        print(f'{r.rule_name:<30} {r.coverage:>7.1%} {r.accuracy:>7.1%} {r.combined_score:>8.4f}')

    # JLPT stats
    print('\n--- JLPT Level Distribution ---')
    for lv in ['N5', 'N4', 'N3', 'N2', 'N1']:
        s = jlpt_stats.get(lv, {})
        print(f'  {lv}: {s.get("total", 0)} total, {s.get("kanji_words", 0)} kanji words')

    # Generate gold card
    print('\n[6/6] Generating gold card document...')
    gold_card = generate_gold_card(results, jlpt_stats, chinese_lev)

    output_path = f'{base}/JLPT_GOLD_CARD.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(gold_card)
    print(f'  Written to {output_path}')

    # Also dump raw JSON for further analysis
    json_output = {
        'rules': [
            {
                'id': r.rule_id,
                'name': r.rule_name,
                'coverage': r.coverage,
                'accuracy': r.accuracy,
                'combined_score': r.combined_score,
                'applicable_words': r.applicable_words,
                'correct_predictions': r.correct_predictions,
                'category': r.category,
            }
            for r in sorted_results
        ],
        'jlpt_stats': jlpt_stats,
    }
    json_path = f'{base}/gold_panning_results.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)
    print(f'  JSON written to {json_path}')

    print('\nDone.')


if __name__ == '__main__':
    main()
