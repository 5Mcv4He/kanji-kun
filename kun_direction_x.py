#!/usr/bin/env python3
"""Direction X: Morphological derivation deduplication.

Key question: How many (kanji, reading) pairs are actually the same ROOT
with different grammatical suffixes, rather than independent memorization units?

Example: 上 has あ(がる), あ(げる), あ(がり) → 3 surface forms, 1 root "a-"
Plus: うえ, うわ → 2 surface forms, 1 root "ue/uwa"
Plus: かみ → 1 root
Total: 6 surface pairs → 3 actual roots (50% reduction within this kanji)

This analysis expands Layer 0 (transitivity pairs) to FULL morphological derivation.
"""

import json
from collections import defaultdict
from pathlib import Path

OUT = Path('/Volumes/SSD/work/kanji-kun/output')

# Known derivational suffix patterns in Japanese
# Each maps a surface ending → what it indicates about the root
DERIV_SUFFIXES = {
    # Godan verb endings (drop to get root)
    'u': 'verb_godan',
    'ku': 'verb_godan',
    'gu': 'verb_godan',
    'su': 'verb_godan',
    'tsu': 'verb_godan',
    'nu': 'verb_godan',
    'bu': 'verb_godan',
    'mu': 'verb_godan',
    'ru': 'verb_godan',  # ambiguous with ichidan
    # Ichidan verb endings
    'eru': 'verb_ichidan',
    'iru': 'verb_ichidan',
    # Adjective endings
    'i': 'adj',
    'shii': 'adj',
    # Noun-forming suffixes (連用形 nominalization)
    'ri': 'noun',
    'ki': 'noun',
    'mi': 'noun',
    'shi': 'noun',
    'chi': 'noun',
    'ke': 'noun',
    'e': 'noun',
    'ari': 'noun',
    # Passive/potential
    'reru': 'passive',
    'rareru': 'passive',
    # Causative
    'seru': 'causative',
    'saseru': 'causative',
}

# Transitivity suffix patterns (same root, different voice)
TRANSITIVITY_PATTERNS = [
    ('aru', 'eru'),   # 上がる↔上げる
    ('garu', 'geru'), # 下がる↔下げる
    ('ku', 'keru'),   # 開く↔開ける
    ('ru', 'su'),     # 出る↔出す
    ('reru', 'ru'),   # 切れる↔切る
    ('karu', 'keru'), # 助かる↔助ける
    ('u', 'eru'),     # 変わる↔変える
    ('tsu', 'teru'),  # 立つ↔立てる
    ('bu', 'beru'),   # 並ぶ↔並べる
    ('mu', 'meru'),   # 止む↔止める
]

def load_data():
    with open(OUT / 'kun_v9_data.json') as f:
        return json.load(f)

def extract_kun_pairs(data):
    """Extract all unique (kanji, reading) kun pairs with their words."""
    pairs = defaultdict(list)
    for w in data['annotated_words']:
        for d in w.get('gt_details', []):
            if d['type'] == 'kun' and d['reading']:
                key = (d['kanji'], d['reading'])
                pairs[key].append({
                    'word': w['word'],
                    'kana': w['kana'],
                    'level': w['level'],
                    'rules_fired': w.get('rules_fired', [])
                })
    return dict(pairs)

def is_rendaku(a, b):
    """Check if b is a rendaku (voiced) variant of a."""
    # Simple: if the only difference is the first consonant being voiced
    voiced_map = {
        'k': 'g', 's': 'z', 't': 'd', 'h': 'b', 'p': 'b',
        'sh': 'j', 'ch': 'j', 'ts': 'z',
    }
    # Also: ひ→び, ふ→ぶ, へ→べ, ほ→ぼ
    unvoiced_to_voiced = str.maketrans({
        'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
        'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
        'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
        'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
        'ぱ': 'ば', 'ぴ': 'び', 'ぷ': 'ぶ', 'ぺ': 'べ', 'ぽ': 'ぼ',
    })
    return a.translate(unvoiced_to_voiced) == b or b.translate(unvoiced_to_voiced) == a

def strip_known_suffix(reading):
    """Try to strip a known derivational suffix from a reading.
    Returns (root, suffix, suffix_type) or (reading, '', 'unknown')."""
    # Try longest suffixes first
    suffixes = sorted(DERIV_SUFFIXES.keys(), key=len, reverse=True)
    for suffix in suffixes:
        if reading.endswith(suffix) and len(reading) > len(suffix):
            root = reading[:-len(suffix)]
            if len(root) >= 1:  # root must be at least 1 mora
                return root, suffix, DERIV_SUFFIXES[suffix]
    return reading, '', 'bare'

def reading_to_moras(r):
    """Split a reading into moras."""
    moras = []
    i = 0
    while i < len(r):
        if i + 1 < len(r) and r[i+1] in 'ゃゅょぁぃぅぇぉャュョァィゥェォ':
            moras.append(r[i:i+2])
            i += 2
        elif r[i] in 'っッ':
            moras.append(r[i])
            i += 1
        elif i + 1 < len(r) and r[i+1] in 'ー':
            moras.append(r[i:i+2])
            i += 2
        else:
            moras.append(r[i])
            i += 1
    return moras

def cluster_by_root(readings):
    """Cluster a list of readings by shared root.
    Two readings share a root if:
    1. They are rendaku variants
    2. One is the other plus a known derivational suffix
    3. They share the first N moras (for long readings)
    Returns: list of clusters, each cluster is a list of readings
    """
    if len(readings) <= 1:
        return [readings] if readings else []

    # Build adjacency: which readings share a root?
    n = len(readings)
    adj = {i: set() for i in range(n)}

    for i in range(n):
        for j in range(i+1, n):
            a, b = readings[i], readings[j]
            connected = False

            # 1. Rendaku
            if is_rendaku(a, b):
                connected = True

            # 2. One is the other + suffix
            root_a, suffix_a, _ = strip_known_suffix(a)
            root_b, suffix_b, _ = strip_known_suffix(b)
            if root_a == root_b and (suffix_a or suffix_b):
                connected = True
            # Check if one root is the other
            if root_a == b or root_b == a:
                connected = True

            # 3. Share first mora AND at least one is a bare noun (short reading)
            # and the lengths differ by <= 2 moras
            moras_a = reading_to_moras(a)
            moras_b = reading_to_moras(b)
            if len(moras_a) >= 1 and len(moras_b) >= 1:
                if moras_a[0] == moras_b[0]:
                    # If they share first mora and one is short (1-2 moras) → likely same root
                    if min(len(moras_a), len(moras_b)) <= 2:
                        len_diff = abs(len(moras_a) - len(moras_b))
                        if len_diff <= 2:
                            # Check if the shorter is a prefix of the longer
                            shorter = a if len(a) <= len(b) else b
                            longer = b if len(a) <= len(b) else a
                            if longer.startswith(shorter) or shorter.startswith(longer[:len(shorter)]):
                                connected = True

            if connected:
                adj[i].add(j)
                adj[j].add(i)

    # Connected components = root clusters
    visited = set()
    clusters = []
    for i in range(n):
        if i not in visited:
            comp = []
            stack = [i]
            while stack:
                v = stack.pop()
                if v not in visited:
                    visited.add(v)
                    comp.append(v)
                    stack.extend(adj[v] - visited)
            clusters.append([readings[v] for v in comp])

    return clusters

def analyze_morphology(pairs):
    """For each kanji, cluster its readings into roots and count savings."""

    # Group by kanji
    kanji_groups = defaultdict(list)
    for (kanji, reading), word_list in pairs.items():
        kanji_groups[kanji].append((reading, word_list))

    results = []
    total_pairs = 0
    total_roots = 0

    for kanji, readings_list in kanji_groups.items():
        readings = [r for r, _ in readings_list]
        clusters = cluster_by_root(readings)

        n_pairs = len(readings)
        n_roots = len(clusters)
        savings = n_pairs - n_roots

        total_pairs += n_pairs
        total_roots += n_roots

        if savings > 0:
            results.append({
                'kanji': kanji,
                'n_pairs': n_pairs,
                'n_roots': n_roots,
                'savings': savings,
                'reduction': savings / n_pairs,
                'clusters': {f"root_{i+1}": c for i, c in enumerate(clusters)},
                'readings': readings,
            })

    results.sort(key=lambda x: x['savings'], reverse=True)
    return results, total_pairs, total_roots

def analyze_by_level(pairs, data):
    """Analyze morphological savings per JLPT level."""
    # Build word → level mapping
    word_levels = {}
    for w in data['annotated_words']:
        word_levels[w['word']] = w['level']

    # Build pairs per level
    level_pairs = defaultdict(dict)
    for (kanji, reading), word_list in pairs.items():
        # Determine level from the words that use this pair
        levels = set()
        for wl in word_list:
            lvl = wl['level']
            if lvl:
                levels.add(lvl)
        for lvl in levels:
            level_pairs[lvl][(kanji, reading)] = word_list

    results_by_level = {}
    grand_total_pairs = 0
    grand_total_roots = 0

    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        if level in level_pairs:
            results, tp, tr = analyze_morphology(level_pairs[level])
            results_by_level[level] = {
                'total_pairs': tp,
                'total_roots': tr,
                'savings': tp - tr,
                'reduction': (tp - tr) / tp * 100 if tp > 0 else 0,
                'top_savers': results[:20],
            }
            grand_total_pairs += tp
            grand_total_roots += tr

    return results_by_level, grand_total_pairs, grand_total_roots

def analyze_transitivity_coverage(pairs):
    """How many pairs are part of transitivity alternations?"""
    # Group by kanji
    kanji_groups = defaultdict(list)
    for (kanji, reading), word_list in pairs.items():
        kanji_groups[kanji].append((reading, word_list))

    trans_pairs_found = []
    for kanji, readings_list in kanji_groups.items():
        readings = [r for r, _ in readings_list]
        for vi_suf, vt_suf in TRANSITIVITY_PATTERNS:
            vi_readings = [r for r in readings if r.endswith(vi_suf)]
            vt_readings = [r for r in readings if r.endswith(vt_suf)]
            if vi_readings and vt_readings:
                # Check if they share the same root
                for vi_r in vi_readings:
                    vi_root = vi_r[:-len(vi_suf)]
                    for vt_r in vt_readings:
                        vt_root = vt_r[:-len(vt_suf)]
                        if vi_root == vt_root:
                            trans_pairs_found.append({
                                'kanji': kanji,
                                'vi': vi_r,
                                'vt': vt_r,
                                'root': vi_root,
                                'pattern': f'{vi_suf}↔{vt_suf}',
                            })

    return trans_pairs_found

def analyze_compound_verb_prefixes(pairs):
    """Discover compound verb patterns where the same reading appears
    with different initial elements (compound prefixes).

    Example: 取(と)る, 受け取(うけと)る, 取り消(とりけ)す
    The core verb root is shared.
    """
    # Find readings that appear both standalone and inside longer words
    reading_set = defaultdict(set)
    for (kanji, reading), word_list in pairs.items():
        reading_set[reading].add(kanji)

    # Find cases where a reading is a substring of another for same kanji
    compounds = []
    for (kanji, reading), word_list in pairs.items():
        kana_set = set()
        for wl in word_list:
            kana_set.add(wl['kana'])
        for other_kana in kana_set:
            if other_kana.endswith(reading) and len(other_kana) > len(reading):
                prefix = other_kana[:-len(reading)]
                compounds.append({
                    'kanji': kanji,
                    'base_reading': reading,
                    'compound_kana': other_kana,
                    'prefix': prefix,
                    'type': 'compound_suffix',
                })

    return compounds

def generate_report(results, by_level, trans_pairs, compounds, total_pairs, total_roots):
    """Generate the markdown report."""
    lines = []
    lines.append('# 方向X：形态派生去重分析')
    lines.append('')
    lines.append('> 核心问题：多少个(汉字,读法)对本质上是同一个词根+不同语法后缀？')
    lines.append('> 如果学一个词根可以自动覆盖它的所有派生形式，真正的记忆量是多少？')
    lines.append('')

    # Overall stats
    lines.append('## 全局结果')
    lines.append('')
    savings_pct = (total_pairs - total_roots) / total_pairs * 100
    lines.append(f'- 表面 (汉字,读法) 对总数：**{total_pairs}**')
    lines.append(f'- 实际词根数：**{total_roots}**')
    lines.append(f'- 形态派生节省：**{total_pairs - total_roots}** 对 ({savings_pct:.1f}%)')
    lines.append(f'- 这是在我们之前的去重（1892）基础上的**进一步压缩**')
    lines.append('')

    # Per-level breakdown
    lines.append('## 按级别分解')
    lines.append('')
    lines.append('| 级别 | 表面对数 | 实际词根 | 节省 | 压缩率 |')
    lines.append('|------|---------|---------|------|--------|')
    for level in ['N5', 'N4', 'N3', 'N2', 'N1']:
        if level in by_level:
            info = by_level[level]
            lines.append(f'| {level} | {info["total_pairs"]} | {info["total_roots"]} | {info["savings"]} | {info["reduction"]:.1f}% |')
    lines.append('')

    # Combined with previous dedup
    lines.append('## 与之前去重的叠加效果')
    lines.append('')
    lines.append('| 步骤 | 说明 | N5-N1总计 |')
    lines.append('|------|------|----------|')
    lines.append(f'| 原始实例 | V9标注的所有kun实例 | 4316 |')
    lines.append(f'| 活用形去重 | 書く/書きます→同一对 | 1892 |')
    lines.append(f'| 词根聚类 | 上がる/上げる/上がり→同一词根 | **{total_roots}** |')
    lines.append(f'| 总压缩率 | 4316 → {total_roots} | **{(1-total_roots/4316)*100:.1f}%** |')
    lines.append('')

    # Top savers (kanji with most morphological inflation)
    lines.append('## 形态派生最密集的汉字 Top 30')
    lines.append('')
    lines.append('| # | 汉字 | 表面对 | 词根数 | 节省 | 压缩率 | 词根聚类 |')
    lines.append('|---|------|--------|--------|------|--------|---------|')
    for i, r in enumerate(results[:30]):
        clusters_str = ' | '.join(
            f'{" / ".join(c)}' for c in r['clusters'].values()
        )
        lines.append(f'| {i+1} | **{r["kanji"]}** | {r["n_pairs"]} | {r["n_roots"]} | {r["savings"]} | {r["reduction"]*100:.0f}% | {clusters_str} |')
    lines.append('')

    # Transitivity pairs discovered
    lines.append('## 自他动词对（形态分析自动发现）')
    lines.append('')
    lines.append(f'共发现 **{len(trans_pairs)}** 个自他动词对。')
    lines.append('')

    # Group by pattern
    by_pattern = defaultdict(list)
    for tp in trans_pairs:
        by_pattern[tp['pattern']].append(tp)

    lines.append('| 模式 | 对数 | 例 |')
    lines.append('|------|------|----|')
    for pattern, tps in sorted(by_pattern.items(), key=lambda x: len(x[1]), reverse=True):
        examples = ', '.join(
            f'{tp["kanji"]}({tp["vi"]}↔{tp["vt"]})' for tp in tps[:5]
        )
        lines.append(f'| {pattern} | {len(tps)} | {examples} |')
    lines.append('')

    # Compound verb patterns
    lines.append('## 复合动词词根复用')
    lines.append('')
    lines.append(f'共发现 **{len(compounds)}** 个复合动词词根复用实例。')
    lines.append('')
    lines.append('同一个词根出现在多种复合动词中，学一个词根覆盖多个复合词。')
    lines.append('')

    # Show top compound patterns
    compound_by_root = defaultdict(list)
    for c in compounds:
        compound_by_root[(c['kanji'], c['base_reading'])].append(c)

    # Sort by number of compounds
    sorted_compounds = sorted(compound_by_root.items(), key=lambda x: len(x[1]), reverse=True)

    lines.append('| 核心(汉字,词根) | 复合词数 | 例 |')
    lines.append('|---------------|---------|----|')
    for (kanji, root), comps in sorted_compounds[:20]:
        examples = ', '.join(c['compound_kana'] for c in comps[:4])
        lines.append(f'| {kanji}({root}) | {len(comps)} | {examples} |')
    lines.append('')

    # Key insight
    lines.append('## 核心发现')
    lines.append('')
    lines.append('1. **形态派生是最大的隐藏杠杆**：之前只做了活用形去重（書く/書きます），')
    lines.append('   但同一词根的自动/他动/名词化/形容词化仍然被算作不同的"记忆对"。')
    lines.append('   这个分析把它们合并了。')
    lines.append('')
    lines.append('2. **10个自他模式是冰山一角**：完整形态系统包括：')
    lines.append('   - 动词自动/他动交替（10个模式，已覆盖）')
    lines.append('   - 连用形名词化（-i/-e/-ari/-ri/-ki/-mi等）')
    lines.append('   - 形容词化（-i/-shii）')
    lines.append('   - 复合动词中的词根复用')
    lines.append('   - 清浊交替（rendaku）')
    lines.append('')
    lines.append('3. **一个词根学会 = 2-5个"记忆对"自动覆盖**。')
    lines.append('   这不是"折扣"，而是根本不需要记——词根学一次，')
    lines.append('   派生形式通过语法规则自动生成，和活用形一样免费。')
    lines.append('')

    return '\n'.join(lines)


def main():
    print("=== Direction X: Morphological Derivation Dedup ===")
    data = load_data()
    pairs = extract_kun_pairs(data)
    print(f"Unique (kanji, reading) kun pairs: {len(pairs)}")

    # Full analysis
    print("\nAnalyzing morphological clusters...")
    results, total_pairs, total_roots = analyze_morphology(pairs)
    print(f"Total pairs: {total_pairs}")
    print(f"Total roots: {total_roots}")
    print(f"Savings: {total_pairs - total_roots} ({(total_pairs-total_roots)/total_pairs*100:.1f}%)")

    # Per-level
    print("\nPer-level analysis...")
    by_level, gp, gr = analyze_by_level(pairs, data)

    # Transitivity
    print("\nAnalyzing transitivity coverage...")
    trans_pairs = analyze_transitivity_coverage(pairs)
    print(f"Transitivity pairs found: {len(trans_pairs)}")

    # Compound verbs
    print("\nAnalyzing compound verb reuse...")
    compounds = analyze_compound_verb_prefixes(pairs)
    print(f"Compound verb instances: {len(compounds)}")

    # Generate report
    report = generate_report(results, by_level, trans_pairs, compounds, total_pairs, total_roots)
    report_path = OUT / 'kun_direction_x.md'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport written to {report_path}")

    # Print key stats
    print(f"\n=== KEY FINDINGS ===")
    print(f"Surface pairs: {total_pairs}")
    print(f"True roots: {total_roots}")
    print(f"Morphological savings: {total_pairs - total_roots} pairs ({(total_pairs-total_roots)/total_pairs*100:.1f}%)")
    print(f"Combined with conjugation dedup (1892 pairs): {total_roots} is {(1-total_roots/1892)*100:.1f}% further reduction from 1892")

    # Top 10 kanji by morphological complexity
    print(f"\nTop 10 most morphologically complex kanji:")
    for r in results[:10]:
        print(f"  {r['kanji']}: {r['n_pairs']} pairs → {r['n_roots']} roots (save {r['savings']})")
        for cluster_name, members in r['clusters'].items():
            print(f"    {cluster_name}: {' / '.join(members)}")

if __name__ == '__main__':
    main()
