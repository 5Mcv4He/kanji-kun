# 训读分级规则系统 v5 · Kun-Yomi Tiered Rules

> 对标 kanji-on 方法论 | 生成: 2026-05-07 08:35
> 数据: 漢字検索V2 46,849字 + 红宝书 9,573词
> 7 Bridge × 4 Rule Type × 5 JLPT Level

---

## 七大铁律 · Seven Iron Laws

> kun-yomi 版 "Iron Laws"。对标 kanji-on 的五大铁律，
> 这7条规则提供最高的性价比——最小记忆量，最大命中率。

| # | 规则 | 类型 | 准确率 | 说明 |
|---|------|------|--------|------|
| 1 | **魚部→名词** | B·radical | 100.0% | 部首=魚 → 名词（100%, 212训读数） |
| 2 | **浊音不重复铁律** | D·phonological | 99.5% | 训读词干内g/z/d/b行音不会重复出现 → 验证器/排除器 |
| 3 | **送假名→训读用言** | A·okurigana | 96.1% | 单汉字词有送假名(〜く/む/る/い等) → 训读 |
| 4 | **自然物部首无动词** | D·radical | 95.0% | 魚/米/牛/竹/虫/雨等自然物部首 → 几乎不产生动词训读 |
| 5 | **单汉字词→训读** | A·compound | 82.7% | 单独一个汉字出现的词 → 训读 |
| 6 | **手部→动词** | B·radical | 74.9% | 部首=手 → 动词（65%, 440训读数） |
| 7 | **2拍复合词→音+音** | A·compound | 71.2% | 2字复合词且2拍 → 音读+音读 |

---

## 验证层 · Verification Layer

> Type D: 不直接预测读音，但提供验证/排除机制

- **浊音不重复铁律**: 训读词干内g/z/d/b行音不会重复出现 → 验证器/排除器 (置信度: very_high)
- **自然物部首无动词**: 魚/米/牛/竹/虫/雨等自然物部首 → 几乎不产生动词训读 (置信度: very_high)
- **入声字→动词倾向**: 中古汉语入声字(-ク/-ツ音读) → 训读倾向动词 (置信度: high)
- **简笔字→警惕多训读**: 笔画≤9的简单汉字 → 平均有更多训读（1.62 vs 1.28） (置信度: medium)
- **工具部首→自他对搜索**: 手/馬/言/力/足/刀/貝部 → 优先检查自他动词对 (置信度: high)

---

## N5 级 · 653字 · 1000词

### 核心规律 (15条)

| # | 规则 | 桥 | 层级 | 置信度 | 准确率 | 记忆成本 |
|---|------|-----|------|--------|--------|---------|
| 1 | 送假名无→名词 | okurigana | 2 | high | 72.2% | 1 |
| 2 | 送假名→训读用言 | okurigana | 1 | very_high | 96.1% | 1 |
| 3 | 送假名る→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 4 | 送假名う→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 5 | 送假名く→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 6 | 送假名つ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 7 | 送假名い→形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 8 | 送假名す→五段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 9 | 送假名ぶ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 10 | 送假名える→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 11 | 送假名しい→シク形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 12 | 送假名む→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 13 | 送假名ける→一段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 14 | 单汉字词→训读 | compound | 1 | very_high | 82.7% | 1 |
| 15 | 5拍+复合词→含训读 | compound | 1 | very_high | 90.4% | 1 |

> 共 44 条规则被集合覆盖算法选中

---

## N4 级 · 781字 · 1121词

### 核心规律 (15条)

| # | 规则 | 桥 | 层级 | 置信度 | 准确率 | 记忆成本 |
|---|------|-----|------|--------|--------|---------|
| 1 | 送假名→训读用言 | okurigana | 1 | very_high | 96.1% | 1 |
| 2 | 送假名无→名词 | okurigana | 2 | high | 72.2% | 1 |
| 3 | 送假名る→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 4 | 送假名う→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 5 | 送假名く→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 6 | 送假名い→形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 7 | 送假名える→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 8 | 送假名す→五段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 9 | 送假名む→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 10 | 送假名ぶ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 11 | 送假名しい→シク形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 12 | 送假名つ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 13 | 送假名ける→一段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 14 | 送假名いる→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 15 | 八部→名词 | radical | 1 | very_high | 100.0% | 1 |

> 共 47 条规则被集合覆盖算法选中

---

## N3 级 · 1113字 · 2071词

### 核心规律 (15条)

| # | 规则 | 桥 | 层级 | 置信度 | 准确率 | 记忆成本 |
|---|------|-----|------|--------|--------|---------|
| 1 | 送假名る→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 2 | 送假名无→名词 | okurigana | 2 | high | 72.2% | 1 |
| 3 | 送假名→训读用言 | okurigana | 1 | very_high | 96.1% | 1 |
| 4 | 送假名う→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 5 | 送假名す→五段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 6 | 送假名い→形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 7 | 送假名く→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 8 | 送假名える→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 9 | 送假名つ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 10 | 送假名む→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 11 | 送假名ぶ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 12 | 送假名ける→一段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 13 | 送假名しい→シク形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 14 | 送假名ぐ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 15 | 送假名いる→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |

> 共 64 条规则被集合覆盖算法选中

---

## N2 级 · 1330字 · 2328词

### 核心规律 (15条)

| # | 规则 | 桥 | 层级 | 置信度 | 准确率 | 记忆成本 |
|---|------|-----|------|--------|--------|---------|
| 1 | 送假名る→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 2 | 送假名无→名词 | okurigana | 2 | high | 72.2% | 1 |
| 3 | 送假名う→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 4 | 送假名→训读用言 | okurigana | 1 | very_high | 96.1% | 1 |
| 5 | 送假名く→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 6 | 送假名い→形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 7 | 送假名す→五段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 8 | 送假名える→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 9 | 送假名ける→一段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 10 | 送假名む→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 11 | 送假名つ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 12 | 送假名ぶ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 13 | 送假名しい→シク形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 14 | 送假名ぐ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 15 | 送假名いる→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |

> 共 72 条规则被集合覆盖算法选中

---

## N1 级 · 1473字 · 3053词

### 核心规律 (15条)

| # | 规则 | 桥 | 层级 | 置信度 | 准确率 | 记忆成本 |
|---|------|-----|------|--------|--------|---------|
| 1 | 送假名る→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 2 | 送假名无→名词 | okurigana | 2 | high | 72.2% | 1 |
| 3 | 送假名う→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 4 | 送假名→训读用言 | okurigana | 1 | very_high | 96.1% | 1 |
| 5 | 送假名い→形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 6 | 送假名く→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 7 | 送假名す→五段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 8 | 送假名える→一段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 9 | 送假名む→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 10 | 送假名つ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 11 | 送假名ける→一段他动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 12 | 送假名しい→シク形容词 | okurigana | 1 | very_high | 100.0% | 1 |
| 13 | 送假名ぐ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 14 | 送假名ぶ→五段动词 | okurigana | 1 | very_high | 100.0% | 1 |
| 15 | 5拍+复合词→含训读 | compound | 1 | very_high | 90.4% | 1 |

> 共 89 条规则被集合覆盖算法选中

---
