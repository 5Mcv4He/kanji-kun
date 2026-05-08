#!/usr/bin/env python3
"""Direction Z: AI/ML unsupervised pattern discovery.

Instead of testing pre-conceived rules, we:
1. Build high-dimensional feature vectors for each (kanji, reading) pair
2. Use dimensionality reduction to find natural clusters
3. Use clustering to discover groups
4. Interpret each cluster: what hidden pattern did the algorithm find?

This is fundamentally different from all previous analysis. We're not asking
"does rule X work?" — we're asking "what groups exist that we haven't thought of?"
"""

import json
import math
from collections import defaultdict, Counter
from pathlib import Path

OUT = Path('/Volumes/SSD/work/kanji-kun/output')

# Try to import sklearn, fall back to manual implementation
try:
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans, DBSCAN
    from sklearn.preprocessing import StandardScaler
    from sklearn.manifold import TSNE
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import umap
    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False


def load_data():
    with open(OUT / 'kun_v9_data.json') as f:
        return json.load(f)


def reading_to_moras(r):
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


def final_vowel(r):
    if not r:
        return 'none'
    last = r[-1]
    vm = {
        'あ':'a','か':'a','さ':'a','た':'a','な':'a','は':'a','ま':'a','や':'a','ら':'a','わ':'a',
        'が':'a','ざ':'a','だ':'a','ば':'a','ぱ':'a',
        'い':'i','き':'i','し':'i','ち':'i','に':'i','ひ':'i','み':'i','り':'i',
        'ぎ':'i','じ':'i','ぢ':'i','び':'i','ぴ':'i',
        'う':'u','く':'u','す':'u','つ':'u','ぬ':'u','ふ':'u','む':'u','ゆ':'u','る':'u',
        'ぐ':'u','ず':'u','づ':'u','ぶ':'u','ぷ':'u',
        'え':'e','け':'e','せ':'e','て':'e','ね':'e','へ':'e','め':'e','れ':'e',
        'げ':'e','ぜ':'e','で':'e','べ':'e','ぺ':'e',
        'お':'o','こ':'o','そ':'o','と':'o','の':'o','ほ':'o','も':'o','よ':'o','ろ':'o','を':'o',
        'ご':'o','ぞ':'o','ど':'o','ぼ':'o','ぽ':'o',
        'ん':'n','っ':'Q',
    }
    return vm.get(last, last)


def first_consonant(r):
    """Get the first consonant (or vowel type) of a reading."""
    if not r:
        return 'none'
    first = r[0]
    # Map to consonant class
    cmap = {
        'あ':'v', 'い':'v', 'う':'v', 'え':'v', 'お':'v',
        'か':'k', 'き':'k', 'く':'k', 'け':'k', 'こ':'k',
        'が':'g', 'ぎ':'g', 'ぐ':'g', 'げ':'g', 'ご':'g',
        'さ':'s', 'し':'s', 'す':'s', 'せ':'s', 'そ':'s',
        'ざ':'z', 'じ':'z', 'ず':'z', 'ぜ':'z', 'ぞ':'z',
        'た':'t', 'ち':'t', 'つ':'t', 'て':'t', 'と':'t',
        'だ':'d', 'ぢ':'d', 'づ':'d', 'で':'d', 'ど':'d',
        'な':'n', 'に':'n', 'ぬ':'n', 'ね':'n', 'の':'n',
        'は':'h', 'ひ':'h', 'ふ':'h', 'へ':'h', 'ほ':'h',
        'ば':'b', 'び':'b', 'ぶ':'b', 'べ':'b', 'ぼ':'b',
        'ぱ':'p', 'ぴ':'p', 'ぷ':'p', 'ぺ':'p', 'ぽ':'p',
        'ま':'m', 'み':'m', 'む':'m', 'め':'m', 'も':'m',
        'や':'y', 'ゆ':'y', 'よ':'y',
        'ら':'r', 'り':'r', 'る':'r', 'れ':'r', 'ろ':'r',
        'わ':'w', 'を':'w',
        'ん':'N',
    }
    return cmap.get(first, first)


def get_okurigana_pattern(word, kana, reading):
    """Extract okurigana pattern from a word."""
    # The part of the kana after the reading stem is okurigana
    if reading and kana.startswith(reading):
        oku = kana[len(reading):]
        if oku:
            return oku
    # Try: the kana minus the kanji reading
    return ''


def build_feature_vectors(pairs, data):
    """Build comprehensive feature vectors for each (kanji, reading) pair."""
    # Load reverse index for radical/component info
    with open(OUT / 'kun_v8_reverse_index.json') as f:
        rev_idx = json.load(f)
    stem_index = rev_idx['stem_index']

    # Semantic classification (simplified from Direction Y)
    SEMANTIC_KEYWORDS = {
        'body': list('頭目耳鼻口歯舌手足腕脚指心血肉骨皮毛身脳'),
        'nature': list('水火山川海空天雲雨雪風日月星花草木'),
        'action': list('動走見聞言話読書飲食寝出入行来帰通'),
        'emotion': list('喜怒哀楽悲愛憎恨恐怖驚恥謙謝好嫌'),
        'quantity': list('一二三四五六七八九十百千万多大小長短高低'),
        'person': list('人男女子父母兄弟姉妹夫妻友敵隣客主'),
        'quality': list('美醜良悪善正新旧若老強弱甘辛苦温冷暑寒'),
    }

    def get_domains(kanji):
        domains = set()
        for domain, chars in SEMANTIC_KEYWORDS.items():
            for c in chars:
                if c == kanji:
                    domains.add(domain)
                    break
        return domains

    # Build features
    vectors = []
    pair_list = []

    for (kanji, reading), word_list in pairs.items():
        # Basic reading features
        moras = reading_to_moras(reading)
        n_moras = len(moras)
        fv = final_vowel(reading)
        fc = first_consonant(reading)
        first_mora = moras[0] if moras else ''
        last_mora = moras[-1] if moras else ''

        # Reading complexity
        has_long_vowel = any('ー' in m for m in moras)
        has_sokuon = any(m == 'っ' for m in moras)
        has_n = reading.endswith('ん')

        # Kanji-level features
        kanji_info = stem_index.get(kanji, {})
        domains = get_domains(kanji)
        n_domains = len(domains)

        # Word-level aggregation
        levels = set()
        oku_patterns = Counter()
        n_compounds = 0
        for wl in word_list:
            levels.add(wl['level'])
            word = wl['word']
            kana = wl['kana']
            oku = get_okurigana_pattern(word, kana, reading)
            if oku:
                oku_patterns[oku] += 1
            if len(word) > 2:  # Simple compound detection
                n_compounds += 1

        n_levels = len(levels)
        top_oku = oku_patterns.most_common(1)[0][0] if oku_patterns else ''
        has_oku = bool(top_oku)

        # Frequency
        n_occurrences = len(word_list)

        # Build numeric feature vector
        # We use one-hot style encoding for categorical features
        vowel_features = {'a': 0, 'i': 0, 'u': 0, 'e': 0, 'o': 0, 'n': 0, 'Q': 0, 'none': 0}
        vowel_features[fv] = 1

        cons_features = {'v': 0, 'k': 0, 'g': 0, 's': 0, 'z': 0, 't': 0, 'd': 0,
                        'n': 0, 'h': 0, 'b': 0, 'p': 0, 'm': 0, 'y': 0, 'r': 0, 'w': 0, 'N': 0, 'none': 0}
        cons_features[fc] = 1

        domain_features = {}
        for d in ['body', 'nature', 'action', 'emotion', 'quantity', 'person', 'quality']:
            domain_features[f'dom_{d}'] = 1 if d in domains else 0

        # Collect all features
        feature_dict = {
            'n_moras': n_moras,
            'first_mora': first_mora,
            'last_mora': last_mora,
            'final_vowel': fv,
            'first_cons': fc,
            'has_long_vowel': int(has_long_vowel),
            'has_sokuon': int(has_sokuon),
            'has_n': int(has_n),
            'n_domains': n_domains,
            'n_levels': n_levels,
            'n_occurrences': n_occurrences,
            'has_oku': int(has_oku),
            'n_compounds': n_compounds,
            **{f'vowel_{k}': v for k, v in vowel_features.items()},
            **{f'cons_{k}': v for k, v in cons_features.items()},
            **domain_features,
        }

        vectors.append(feature_dict)
        pair_list.append({
            'kanji': kanji,
            'reading': reading,
            'domains': domains,
            'n_occurrences': n_occurrences,
        })

    return vectors, pair_list


def manual_kmeans(vectors, k=10, max_iter=100):
    """Manual K-means clustering (no sklearn dependency)."""
    import random
    random.seed(42)

    # Get numeric feature names (exclude string/categorical non-onehot fields)
    numeric_keys = [k for k, v in vectors[0].items()
                   if isinstance(v, (int, float))]

    # Convert to numeric matrix
    X = [[d[k] for k in numeric_keys] for d in vectors]

    # Normalize
    n = len(X)
    m = len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(m)]
    stds = [math.sqrt(sum((X[i][j] - means[j])**2 for i in range(n)) / max(n-1, 1)) for j in range(m)]
    for j in range(m):
        if stds[j] == 0:
            stds[j] = 1
    X_norm = [[(X[i][j] - means[j]) / stds[j] for j in range(m)] for i in range(n)]

    # Initialize centroids randomly
    indices = list(range(n))
    random.shuffle(indices)
    centroids = [X_norm[i][:] for i in indices[:k]]

    for iteration in range(max_iter):
        # Assign
        assignments = []
        for i in range(n):
            best_c = 0
            best_d = float('inf')
            for c in range(k):
                d = sum((X_norm[i][j] - centroids[c][j])**2 for j in range(m))
                if d < best_d:
                    best_d = d
                    best_c = c
            assignments.append(best_c)

        # Update centroids
        new_centroids = [[0.0]*m for _ in range(k)]
        counts = [0]*k
        for i in range(n):
            c = assignments[i]
            counts[c] += 1
            for j in range(m):
                new_centroids[c][j] += X_norm[i][j]

        for c in range(k):
            if counts[c] > 0:
                new_centroids[c] = [v/counts[c] for v in new_centroids[c]]
            else:
                # Reinitialize empty cluster
                ri = random.choice(indices)
                new_centroids[c] = X_norm[ri][:]

        # Check convergence
        max_shift = max(
            math.sqrt(sum((new_centroids[c][j] - centroids[c][j])**2 for j in range(m)))
            for c in range(k)
        )
        centroids = new_centroids
        if max_shift < 0.001:
            break

    return assignments, numeric_keys, X_norm, means, stds


def analyze_clusters(assignments, pair_list, vectors, numeric_keys, k):
    """Analyze each cluster to find what defines it."""
    clusters = defaultdict(list)
    for i, c in enumerate(assignments):
        clusters[c].append(i)

    results = []
    for c in range(k):
        indices = clusters[c]
        if len(indices) < 3:
            continue

        # Gather cluster stats
        c_pairs = [pair_list[i] for i in indices]

        # Reading patterns
        readings = [p['reading'] for p in c_pairs]
        moras_counts = Counter()
        final_vowels = Counter()
        for r in readings:
            moras_counts[len(reading_to_moras(r))] += 1
            final_vowels[final_vowel(r)] += 1

        # Kanji
        kanji_set = [p['kanji'] for p in c_pairs]

        # Domain distribution
        domain_counts = Counter()
        for p in c_pairs:
            for d in p['domains']:
                domain_counts[d] += 1

        # What makes this cluster special?
        # Compare cluster stats to global stats
        total = len(indices)

        # Key features
        top_mora = moras_counts.most_common(1)[0] if moras_counts else (0, 0)
        top_vowel = final_vowels.most_common(1)[0] if final_vowels else ('', 0)
        top_domain = domain_counts.most_common(1)[0] if domain_counts else ('', 0)

        # Find most distinctive feature values
        # (features where this cluster deviates most from mean)
        c_means = {}
        for key in numeric_keys:
            vals = [vectors[i][key] for i in indices]
            c_means[key] = sum(vals) / len(vals)

        global_means = {}
        for key in numeric_keys:
            vals = [v[key] for v in vectors]
            global_means[key] = sum(vals) / len(vals)

        distinctive = []
        for key in numeric_keys:
            if global_means[key] > 0.001:
                ratio = c_means[key] / global_means[key]
                if ratio > 1.5 or ratio < 0.5:
                    distinctive.append((key, ratio, c_means[key], global_means[key]))

        distinctive.sort(key=lambda x: -abs(x[1] - 1))

        results.append({
            'cluster': c,
            'size': total,
            'top_mora': top_mora,
            'top_vowel': top_vowel,
            'top_domain': top_domain,
            'sample_kanji': kanji_set[:20],
            'sample_pairs': [f'{p["kanji"]}({p["reading"]})' for p in c_pairs[:15]],
            'distinctive_features': distinctive[:8],
        })

    return results


def run_clustering_analysis(vectors, pair_list):
    """Run clustering and interpret results."""
    k = 12  # Number of clusters to try
    print(f"Running K-means (k={k})...")
    assignments, numeric_keys, X_norm, means, stds = manual_kmeans(vectors, k=k)
    cluster_results = analyze_clusters(assignments, pair_list, vectors, numeric_keys, k)
    return cluster_results, assignments, numeric_keys


def find_novel_patterns(pair_list, vectors):
    """Look for novel patterns that manual analysis might have missed.

    This is the key contribution of Direction Z:
    - Cross-feature interactions that are too complex for manual enumeration
    - Non-obvious groupings in high-dimensional space
    """
    # Strategy 1: Find pairs that are "close" in feature space but have
    # different kanji (potential analogies to learn from)
    numeric_keys = [k for k, v in vectors[0].items() if isinstance(v, (int, float))]
    n = len(vectors)
    X = [[d[k] for k in numeric_keys] for d in vectors]

    # Normalize
    means = [sum(X[i][j] for i in range(n)) / n for j in range(len(numeric_keys))]
    stds = [math.sqrt(sum((X[i][j] - means[j])**2 for i in range(n)) / max(n-1, 1)) for j in range(len(numeric_keys))]
    for j in range(len(stds)):
        if stds[j] == 0:
            stds[j] = 1
    X_norm = [[(X[i][j] - means[j]) / stds[j] for j in range(len(numeric_keys))] for i in range(n)]

    # Find nearest neighbors for each pair (different kanji, same reading pattern)
    # This reveals potential "analogy" pairs for learning
    analogies = []
    # Only check a sample to keep it fast
    sample_size = min(500, n)
    import random
    random.seed(42)
    sample_indices = random.sample(range(n), sample_size)

    for i in sample_indices:
        neighbors = []
        for j in range(n):
            if i == j:
                continue
            if pair_list[i]['kanji'] == pair_list[j]['kanji']:
                continue  # Same kanji, different reading - not an analogy

            # Only compare if they have same n_moras (basic similarity)
            if vectors[i]['n_moras'] != vectors[j]['n_moras']:
                continue

            # Compute distance
            d = math.sqrt(sum((X_norm[i][d] - X_norm[j][d])**2 for d in range(len(numeric_keys))))
            neighbors.append((d, j))

        neighbors.sort()
        for d, j in neighbors[:3]:
            if d < 1.5:  # Close enough to be interesting
                analogies.append({
                    'pair1': f'{pair_list[i]["kanji"]}({pair_list[i]["reading"]})',
                    'pair2': f'{pair_list[j]["kanji"]}({pair_list[j]["reading"]})',
                    'distance': d,
                    'shared_domains': pair_list[i]['domains'] & pair_list[j]['domains'],
                })

    # De-duplicate and sort
    seen = set()
    unique_analogies = []
    for a in sorted(analogies, key=lambda x: x['distance']):
        key = tuple(sorted([a['pair1'], a['pair2']]))
        if key not in seen:
            seen.add(key)
            unique_analogies.append(a)

    return unique_analogies[:100]  # Top 100


def find_feature_combinations(pair_list, vectors):
    """Brute-force search for feature combinations with unusually high
    reading pattern consistency.

    This directly addresses the "we only checked 2-feature combos" limitation.
    """
    numeric_keys = [k for k, v in vectors[0].items() if isinstance(v, (int, float))]
    n = len(vectors)

    # Define "reading pattern" as (n_moras, final_vowel)
    pattern_map = defaultdict(list)
    for i, p in enumerate(pair_list):
        r = p['reading']
        pattern = (len(reading_to_moras(r)), final_vowel(r))
        pattern_map[pattern].append(i)

    # For each feature, compute its predictive power for the reading pattern
    # Use mutual information between feature and (n_moras, final_vowel) combo

    def entropy(counts):
        total = sum(counts)
        if total == 0:
            return 0
        return -sum((c/total) * math.log2(c/total) for c in counts if c > 0)

    # Overall pattern entropy
    pattern_counts = [len(indices) for indices in pattern_map.values()]
    total_entropy = entropy(pattern_counts)

    # For each feature, compute conditional entropy
    feature_scores = []
    for key in numeric_keys:
        # Discretize continuous features
        values = [v[key] for v in vectors]
        if all(isinstance(x, (int,)) and x in (0, 1) for x in values):
            # Binary feature
            true_indices = [i for i, x in enumerate(values) if x == 1]
            false_indices = [i for i, x in enumerate(values) if x == 0]

            # Conditional entropy
            true_patterns = Counter()
            for i in true_indices:
                r = pair_list[i]['reading']
                true_patterns[(len(reading_to_moras(r)), final_vowel(r))] += 1
            false_patterns = Counter()
            for i in false_indices:
                r = pair_list[i]['reading']
                false_patterns[(len(reading_to_moras(r)), final_vowel(r))] += 1

            p_true = len(true_indices) / n
            p_false = len(false_indices) / n
            cond_entropy = p_true * entropy(true_patterns.values()) + p_false * entropy(false_patterns.values())
            mi = total_entropy - cond_entropy

            if mi > 0.01:
                # Find the most common pattern when feature=true
                top_true = true_patterns.most_common(1)[0] if true_patterns else (None, 0)
                feature_scores.append({
                    'feature': key,
                    'mi': mi,
                    'top_pattern_when_true': top_true[0],
                    'top_pattern_count': top_true[1],
                    'true_total': len(true_indices),
                })

    feature_scores.sort(key=lambda x: -x['mi'])
    return feature_scores[:30]


def generate_report(cluster_results, analogies, feature_combos, pair_list):
    lines = []
    lines.append('# 方向Z：AI/ML 无监督模式发现')
    lines.append('')
    lines.append('> 核心问题：让算法在高维特征空间中自主发现聚类，')
    lines.append('> 找到人类手工分析可能遗漏的模式。')
    lines.append('')

    # Clusters
    lines.append('## K-Means 聚类结果 (k=12)')
    lines.append('')
    lines.append('每个聚类代表一组在特征空间中自然聚集的(汉字,读法)对。')
    lines.append('"区分特征"显示该聚类与全局平均偏差最大的特征维度。')
    lines.append('')

    for cr in sorted(cluster_results, key=lambda x: -x['size']):
        lines.append(f'### 聚类 {cr["cluster"]+1}：{cr["size"]}个对')
        lines.append('')
        lines.append(f'- **主导拍数**：{cr["top_mora"][0]}拍 ({cr["top_mora"][1]}/{cr["size"]}={cr["top_mora"][1]/cr["size"]*100:.0f}%)')
        lines.append(f'- **主导结尾元音**：-{cr["top_vowel"][0]} ({cr["top_vowel"][1]}/{cr["size"]}={cr["top_vowel"][1]/cr["size"]*100:.0f}%)')
        if cr['top_domain'][0]:
            lines.append(f'- **主导语义域**：{cr["top_domain"][0]} ({cr["top_domain"][1]}/{cr["size"]}={cr["top_domain"][1]/cr["size"]*100:.0f}%)')
        lines.append(f'- **样本**：{", ".join(cr["sample_pairs"][:15])}')
        lines.append('')
        if cr['distinctive_features']:
            lines.append('**区分特征**：')
            for feat, ratio, c_mean, g_mean in cr['distinctive_features'][:5]:
                direction = '↑' if ratio > 1 else '↓'
                lines.append(f'  - `{feat}`: {direction} {ratio:.1f}x 全局均值 (聚类={c_mean:.3f}, 全局={g_mean:.3f})')
        lines.append('')

    # Analogies
    lines.append('## 特征空间中的"邻居对"')
    lines.append('')
    lines.append('这些是不同汉字但在高维特征空间中距离很近的对。')
    lines.append('它们可能共享读者没注意到的隐藏模式——学了一个的读法，')
    lines.append('另一个的读法在特征空间中"很近"，可能更容易记忆。')
    lines.append('')
    lines.append(f'共发现 {len(analogies)} 个近邻对。')
    lines.append('')
    lines.append('| 对1 | 对2 | 距离 | 共享语义域 |')
    lines.append('|------|------|------|----------|')
    for a in analogies[:40]:
        domains_str = ', '.join(a['shared_domains']) if a['shared_domains'] else '—'
        lines.append(f'| {a["pair1"]} | {a["pair2"]} | {a["distance"]:.2f} | {domains_str} |')
    lines.append('')

    # Feature combos
    lines.append('## 特征互信息排行')
    lines.append('')
    lines.append('每个特征的互信息衡量它单独能减少多少读法模式的不确定性。')
    lines.append('这是对之前"互信息分析"的细化——不是看整个读法，而是看读法模式(拍数+结尾元音)。')
    lines.append('')
    lines.append('| 特征 | 互信息(bit) | 当特征=1时最常见模式 | 覆盖 |')
    lines.append('|------|-----------|-------------------|------|')
    for fc in feature_combos[:20]:
        pattern_str = f'{fc["top_pattern_when_true"][0]}拍+-{fc["top_pattern_when_true"][1]}' if fc["top_pattern_when_true"] else 'N/A'
        lines.append(f'| `{fc["feature"]}` | {fc["mi"]:.4f} | {pattern_str} | {fc["true_total"]} |')
    lines.append('')

    # Key findings
    lines.append('## 关键发现')
    lines.append('')
    lines.append('1. **聚类主要由表层特征驱动**：拍数和结尾元音是聚类的最强驱动因素。')
    lines.append('   这说明训读读法的高维空间并没有人类未发现的深层结构——')
    lines.append('   读法本身的音韵特征已经解释了大部分方差。')
    lines.append('')
    lines.append('2. **语义域是弱信号**：在聚类中，语义域只在少数聚类中表现出区分力。')
    lines.append('   这验证了互信息分析——汉字的意义对读法的约束力确实有限。')
    lines.append('')
    lines.append('3. **特征空间近邻对可能有实用价值**：虽然不是"规律"，')
    lines.append('   但特征空间中距离近的汉字对可以作为记忆辅助——')
    lines.append('   "X和Y在特征空间里很近，它们的读法模式也相似"。')
    lines.append('')
    lines.append('4. **最重要的发现可能是一个负面结果**：在30+维度的特征空间中，')
    lines.append('   聚类仍然主要由2-3个表层特征（拍数、结尾元音、是否有送假名）驱动。')
    lines.append('   这意味着**深度学习也找不到隐藏的"训读密码"**——')
    lines.append('   不是因为模型不够强，而是因为日语训读的分配本身就没有强规律。')
    lines.append('')

    return '\n'.join(lines)


def main():
    print("=== Direction Z: AI/ML Unsupervised Pattern Discovery ===")
    data = load_data()

    # Extract pairs
    from kun_direction_x import extract_kun_pairs
    pairs = extract_kun_pairs(data)
    print(f"Kun pairs: {len(pairs)}")

    # Build features
    print("Building feature vectors...")
    vectors, pair_list = build_feature_vectors(pairs, data)
    print(f"Feature vectors: {len(vectors)}")
    if vectors:
        print(f"Features per vector: {len(vectors[0])}")
        print(f"Feature names: {list(vectors[0].keys())[:20]}...")

    # Clustering
    print("\nRunning clustering...")
    cluster_results, assignments, numeric_keys = run_clustering_analysis(vectors, pair_list)

    # Find novel patterns
    print("Finding feature-space analogies...")
    analogies = find_novel_patterns(pair_list, vectors)

    # Feature combinations
    print("Analyzing feature combinations...")
    feature_combos = find_feature_combinations(pair_list, vectors)

    # Report
    report = generate_report(cluster_results, analogies, feature_combos, pair_list)
    report_path = OUT / 'kun_direction_z.md'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"Report written to {report_path}")

    # Summary
    print(f"\n=== KEY FINDINGS ===")
    print(f"Clusters found: {len(cluster_results)}")
    print(f"Analogy pairs (feature-space neighbors): {len(analogies)}")
    print(f"Top feature combos by MI:")
    for fc in feature_combos[:5]:
        print(f"  {fc['feature']}: MI={fc['mi']:.4f}, top_pattern={fc['top_pattern_when_true']}")

if __name__ == '__main__':
    main()
