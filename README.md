<p align="center">
  <samp>訓</samp> <samp>読</samp> <samp>終</samp> <samp>結</samp>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/kanji-2,135-c5602e?style=flat-square" alt="2,135 JLPT kanji">
  <img src="https://img.shields.io/badge/ratio-4.0:1-b8472e?style=flat-square" alt="4.0:1 compression">
  <img src="https://img.shields.io/badge/level-N5%E2%80%93N1-d4954a?style=flat-square" alt="N5-N1">
  <img src="https://img.shields.io/badge/license-MIT-8a7a6a?style=flat-square" alt="MIT">
</p>

# 训读终结

<p align="center">
  <b>JLPT 的训读，四分之三不需要记。</b>
  <br>
  不是靠技巧绕过去——是日语本身的语法结构决定了它们不是独立的记忆项。
  <br>
  4,316 个表面实例，压缩到 ~1,100 个需要刻意记的词根。用三种走法串起来。
</p>

<br>

---

```
$ python3 kun_diagnostic_v9.py

=== V9 Diagnostic ===

[1/4] Compression...
  4,316 → 1,892 → 1,703 → 1,087
  Ratio: 4.0:1 (74.8% of surface instances eliminated)

[2/4] Transfer...
  N4: 25.2% already seen in N5
  N3: 39.9%            ← 将近一半不是新的
  N2: 46.9%
  N1: 44.9%

[3/4] Anchors...
  Coverage: 99.7% (3+ anchors: 54.8%)

[4/4] Traps...
  Multi-kun: 90  Homo: 123  Shape: 70  Heavy: 29

=== 训读不是背的，是逛的 ===
```

---

<br>

## 为什么不是"背"而是"逛"

| 传统做法 | 实际需要 |
|---------|---------|
| 4,316 个 (汉字, 读音) —— 逐个背 | 1,100 个词根 —— 逛着确认 |
| 每个读音独立记忆 | 260 个词干家族，同音汉字一次确认 |
| 自动词他动词分着记 | 10 个模式管几百对，学一个送一个 |
| 汉字散装排列 | 15 个部首文件夹，建好归类 |

**确认的成本，大约是全新记忆的三成。** 学「書＝か」之后，遇到「買＝か」「変＝か」——你不是在背新读音，你在确认同一个读音。

<br>

## 看一眼就能用

**音训判断，见到词第一秒决定方向：**

| 看到什么 | 判断 | 靠谱率 |
|---------|------|--------|
| 多汉字 + 无假名尾巴 | 音读 | 96% |
| 有假名尾巴 | 训读 | 90% |
| 身体/自然/亲属词汇 | 训读信号 | — |
| 入声尾(くつちき) + 无假名 | 音读 | 80% |

**自他对应，10 个模式学一次终身受用：**

```
まる↔める  がる↔げる  く↔ける  る↔す  れる↔る
かる↔ける  う↔える  つ↔てる  ぶ↔べる  む↔める
```

看到 〜める，自动词大概率 〜まる。**学模式，不学一对一对。**

**逛法速查：** 学到新字 → 问它是不是已知词干家族的成员 → 确认一次自他模式 → 部首文件夹归档。JLPT 任何一个汉字，三秒内知道往哪逛。

<br>

## 怎么做到的

三个方向穷举全死了，反而确认了边界：

- **规则推导**：if-then 规则覆盖率硬上限 21%。训读不存在全局推导规则。
- **特征交叉**：部首/语义/送假名两两交叉，最强信号 1 bit ≈ 抛硬币。
- **ML 聚类**：30+ 维特征跑 K-Means，只聚类出音韵相似性——不存在被隐藏的深层结构。

**这反而是好消息：** 75% 的东西本来就不该作为独立记忆项存在，剩下 25% 靠网络关系串起来。不需要找规律——你只需要学会逛。

<br>

## 快速开始

```bash
pip install openpyxl
python3 kun_diagnostic_v9.py
# → output/kun_diagnostic_v9.md + .json
```

**Web 工具：** [www.5mcv4he.cn/yomeru.html](https://www.5mcv4he.cn/yomeru.html) — 点任意汉字看它连着谁。

核心输出：

| 文件 | 说明 |
|------|------|
| `output/kun_final_system.md` | 学习者一站式文档（7 章 + 速查卡） |
| `output/kun_diagnostic_v9.md` | 四维量化诊断报告 |
| `output/kun_v8_anki_N5.csv` ~ `N1.csv` | 分级别 Anki 牌组 |
| `output/kanji_app_data.json` | Web 应用数据 |
| `app/index.html` | 训读网络探索器 |

<br>

## 已验证的发现

✓ 音训判断 6 条覆盖 91% · 自他对 10 模式 · 活用形归并 −56% · 跨级复用 25–47% · 词干连带确认成本 ~30% · 部首锚点覆盖 97.3% · 陷阱全标记

✗ "训读声旁"不存在（形近字共享读法 0.2–0.6%） · 部首不能预测读音 · ML 未发现隐藏结构

---

<p align="center">
  <a href="docs/2026-05-09-训读的终极答案-不是背-是逛.md">文章：训读的终极答案</a> ·
  <a href="output/kun_final_system.md">学习者文档</a> ·
  <a href="https://www.5mcv4he.cn/yomeru.html">Web 工具</a>
</p>

<p align="center">
  <sub>MIT · 所有数字可复现 · 基于 JLPT 词汇逐字标注</sub>
</p>
