# V8 Word-Level Prediction Engine Report

**Overall Accuracy:** 50.1% (4791/9572 words)


## Ground Truth Distribution

| Pattern | Count |
|---------|-------|
| on+on | 3410 |
| kun | 2175 |
| no_kanji | 1197 |
| kun+kun~ | 620 |
| mixed+mixed~ | 473 |
| on+on+on | 278 |
| on | 253 |
| unknown | 218 |
| kun+kun | 209 |
| kun+on~ | 126 |
| on+kun~ | 96 |
| on~ | 69 |
| on+on~ | 66 |
| mixed+mixed+mixed~ | 60 |
| on+mixed~ | 45 |
| on+kun | 33 |
| mixed+on~ | 32 |
| on+on+on+on | 27 |
| kun+kun+kun~ | 24 |
| on+on+on+on~ | 21 |
| mixed+on+mixed~ | 19 |
| on+on+kun~ | 19 |
| kun+on+on~ | 15 |
| mixed+mixed+mixed+mixed~ | 12 |
| mixed+mixed+on~ | 10 |
| kun+on+kun~ | 10 |
| kun+kun+kun+kun~ | 9 |
| on+on+on~ | 8 |
| on+mixed+mixed~ | 7 |
| on+kun+kun~ | 4 |
| mixed+on+on~ | 3 |
| on+mixed+on+mixed~ | 2 |
| on+on+on+on+on+on~ | 2 |
| mixed+mixed+mixed+on~ | 2 |
| mixed+kun~ | 2 |
| kun+kun+on~ | 2 |
| mixed+mixed+mixed+mixed+mixed+mixed+mixed~ | 1 |
| mixed+mixed+mixed+mixed+mixed+mixed~ | 1 |
| kun+on+on+on~ | 1 |
| on+kun+on~ | 1 |
| on+on+on+on+on | 1 |
| mixed+on+mixed+on~ | 1 |
| on+mixed+mixed+mixed~ | 1 |
| on+on+on+kun~ | 1 |
| kun+kun+on+on~ | 1 |
| kun+kun+kun+on~ | 1 |
| on+kun+on+kun~ | 1 |
| kun+on+kun+kun~ | 1 |
| mixed+mixed+on+mixed~ | 1 |
| on+on+kun+on~ | 1 |

## Per-Level Accuracy

| Level | Total | Correct | Accuracy |
|-------|-------|---------|----------|
| N5 | 999 | 721 | 72.2% |
| N4 | 1121 | 689 | 61.5% |
| N3 | 2071 | 1030 | 49.7% |
| N2 | 2328 | 979 | 42.1% |
| N1 | 3053 | 1372 | 44.9% |

## Per-Pattern Accuracy

| Pattern | Total | Correct | Accuracy |
|---------|-------|---------|----------|
| on+on | 3410 | 0 | 0.0% |
| kun | 2175 | 2175 | 100.0% |
| no_kanji | 1197 | 1197 | 100.0% |
| kun+kun~ | 620 | 186 | 30.0% |
| mixed+mixed~ | 473 | 473 | 100.0% |
| on+on+on | 278 | 277 | 99.6% |
| on | 253 | 33 | 13.0% |
| unknown | 218 | 0 | 0.0% |
| kun+kun | 209 | 0 | 0.0% |
| kun+on~ | 126 | 52 | 41.3% |
| on+kun~ | 96 | 41 | 42.7% |
| on~ | 69 | 48 | 69.6% |
| on+on~ | 66 | 0 | 0.0% |
| mixed+mixed+mixed~ | 60 | 60 | 100.0% |
| on+mixed~ | 45 | 45 | 100.0% |
| on+kun | 33 | 33 | 100.0% |
| mixed+on~ | 32 | 32 | 100.0% |
| on+on+on+on | 27 | 27 | 100.0% |
| kun+kun+kun~ | 24 | 16 | 66.7% |
| on+on+on+on~ | 21 | 21 | 100.0% |
| mixed+on+mixed~ | 19 | 19 | 100.0% |
| on+on+kun~ | 19 | 0 | 0.0% |
| kun+on+on~ | 15 | 0 | 0.0% |
| mixed+mixed+mixed+mixed~ | 12 | 12 | 100.0% |
| mixed+mixed+on~ | 10 | 10 | 100.0% |
| kun+on+kun~ | 10 | 0 | 0.0% |
| kun+kun+kun+kun~ | 9 | 6 | 66.7% |
| on+on+on~ | 8 | 4 | 50.0% |
| on+mixed+mixed~ | 7 | 7 | 100.0% |
| on+kun+kun~ | 4 | 0 | 0.0% |
| mixed+on+on~ | 3 | 3 | 100.0% |
| on+mixed+on+mixed~ | 2 | 2 | 100.0% |
| on+on+on+on+on+on~ | 2 | 2 | 100.0% |
| mixed+mixed+mixed+on~ | 2 | 2 | 100.0% |
| mixed+kun~ | 2 | 2 | 100.0% |
| kun+kun+on~ | 2 | 0 | 0.0% |
| mixed+mixed+mixed+mixed+mixed+mixed+mixed~ | 1 | 1 | 100.0% |
| mixed+mixed+mixed+mixed+mixed+mixed~ | 1 | 1 | 100.0% |
| kun+on+on+on~ | 1 | 0 | 0.0% |
| on+kun+on~ | 1 | 0 | 0.0% |
| on+on+on+on+on | 1 | 1 | 100.0% |
| mixed+on+mixed+on~ | 1 | 1 | 100.0% |
| on+mixed+mixed+mixed~ | 1 | 1 | 100.0% |
| on+on+on+kun~ | 1 | 0 | 0.0% |
| kun+kun+on+on~ | 1 | 0 | 0.0% |
| kun+kun+kun+on~ | 1 | 0 | 0.0% |
| on+kun+on+kun~ | 1 | 0 | 0.0% |
| kun+on+kun+kun~ | 1 | 0 | 0.0% |
| mixed+mixed+on+mixed~ | 1 | 1 | 100.0% |
| on+on+kun+on~ | 1 | 0 | 0.0% |

## Error Analysis (4781 total errors)

| Level | Errors |
|-------|--------|
| N5 | 278 |
| N4 | 432 |
| N3 | 1041 |
| N2 | 1349 |
| N1 | 1681 |

### Top 20 Misclassified Words

| Word | Kana | Level | Ground Truth | Predicted | Confidence |
|------|------|-------|--------------|-----------|------------|
| 温/暖かい | あたたかい | N5 | kun+kun~ | on+kun | 65.0% |
| あの様 | あのよう | N5 | unknown | kun | 96.1% |
| 愛 | あい | N4 | on | kun | 84.0% |
| 愛犬 | あいけん | N4 | on+on | kun+kun | 65.0% |
| 挨拶 | あいさつ | N4 | on+on | kun+kun | 65.0% |
| 赤字 | あかじ | N4 | kun+on~ | kun+kun | 65.0% |
| 温める/暖める | あたためる | N4 | kun+kun~ | on+kun | 65.0% |
| 編み物 | あみもの | N4 | kun+kun~ | on+kun | 65.0% |
| alcohol（荷） | アルコール | N4 | unknown | kun | 84.0% |
| 安心 | あんしん | N4 | on+on | kun+kun | 65.0% |
| 安全 | あんぜん | N4 | on+on | kun+kun | 65.0% |
| 安全belt | あんぜんベルト | N4 | on+on~ | kun+kun | 65.0% |
| 案内 | あんない | N4 | on+on | kun+kun | 65.0% |
| 愛情 | あいじょう | N3 | on+on | kun+kun | 65.0% |
| 曖昧 | あいまい | N3 | on+on | kun+kun | 65.0% |
| 愛用 | あいよう | N3 | on+on | kun+kun | 65.0% |
| 握手 | あくしゅ | N3 | on+on | kun+kun | 65.0% |
| 朝晩 | あさばん | N3 | kun+on~ | kun+kun | 65.0% |
| 味見 | あじみ | N3 | on+kun~ | kun+kun | 65.0% |
| 足元/足下 | あしもと | N3 | kun+kun+kun+kun~ | on+... | 55.0% |

## Per-Word Annotations (first 100 words)

| # | Word | Kana | Level | GT | Pred | Correct | Rules |
|---|------|------|-------|----|------|---------|-------|
| 1 | ice-cream | アイスクリーム | N5 | no_kanji | no_kanji | ✓ |  |
| 2 | 会う | あう | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 3 | 青 | あお | N5 | kun | kun | ✓ | IL2_single_default |
| 4 | 青い | あおい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 5 | 赤 | あか | N5 | kun | kun | ✓ | IL2_single_default |
| 6 | 赤い | あかい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 7 | 明るい | あかるい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 8 | 秋 | あき | N5 | kun | kun | ✓ | IL2_single_default |
| 9 | 開く | あく | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 10 | 開ける | あける | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 11 | 上げる | あげる | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 12 | 朝 | あさ | N5 | kun | kun | ✓ | IL2_single_default |
| 13 | 朝ご飯 | あさごはん | N5 | kun+on~ | on+kun | ✓ | IL1_okurigana, A1_compound_oku, A1_on_kun_mix |
| 14 | 明後日 | あさって | N5 | mixed+mixed+mixed~ | on+... | ✓ | A4_multi_on |
| 15 | 足 | あし | N5 | kun | kun | ✓ | IL2_single_default, B_verb_rad_足 |
| 16 | 明日 | あした | N5 | mixed+mixed~ | kun+kun | ✓ | A3_short_compound |
| 17 |  | あそこ | N5 | no_kanji | no_kanji | ✓ |  |
| 18 | 遊ぶ | あそぶ | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 19 |  | あたし | N5 | no_kanji | no_kanji | ✓ |  |
| 20 | 温/暖かい | あたたかい | N5 | kun+kun~ | on+kun | ✗ | IL1_okurigana, A1_compound_oku, A1_on_kun_mix |
| 21 | 頭 | あたま | N5 | kun | kun | ✓ | IL2_single_default |
| 22 | 新しい | あたらしい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 23 |  | あちら | N5 | no_kanji | no_kanji | ✓ |  |
| 24 |  | あっ | N5 | no_kanji | no_kanji | ✓ |  |
| 25 | 暑い | あつい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 26 | 熱い | あつい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 27 | 厚い | あつい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 28 |  | あっち | N5 | no_kanji | no_kanji | ✓ |  |
| 29 | 後 | あと | N5 | kun | kun | ✓ | IL2_single_default |
| 30 |  | あなた | N5 | no_kanji | no_kanji | ✓ |  |
| 31 | 兄 | あに | N5 | kun | kun | ✓ | IL2_single_default |
| 32 | 姉 | あね | N5 | kun | kun | ✓ | IL2_single_default |
| 33 |  | あの | N5 | no_kanji | no_kanji | ✓ |  |
| 34 |  | あの/あのう | N5 | no_kanji | no_kanji | ✓ |  |
| 35 | あの様 | あのよう | N5 | unknown | kun | ✗ | IL1_okurigana, IL2_single_okuri, B_noun_rad_木 |
| 36 | apartment | アパート | N5 | no_kanji | no_kanji | ✓ |  |
| 37 | 浴びる | あびる | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 38 | 危ない | あぶない | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 39 | 甘い | あまい | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 40 | 余り | あまり | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 41 | 雨 | あめ | N5 | kun | kun | ✓ | IL2_single_default, B_noun_rad_雨 |
| 42 | 飴 | あめ | N5 | kun | kun | ✓ | IL2_single_default |
| 43 | 洗う | あらう | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 44 | 有る | ある | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 45 | 歩く | あるく | N5 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 46 | album | アルバム | N5 | no_kanji | no_kanji | ✓ |  |
| 47 |  | あれ | N5 | no_kanji | no_kanji | ✓ |  |
| 48 |  | あ | N4 | no_kanji | no_kanji | ✓ |  |
| 49 |  | ああ | N4 | no_kanji | no_kanji | ✓ |  |
| 50 | 愛 | あい | N4 | on | kun | ✗ | IL2_single_default |
| 51 | 愛犬 | あいけん | N4 | on+on | kun+kun | ✗ |  |
| 52 | 挨拶 | あいさつ | N4 | on+on | kun+kun | ✗ | B_verb_rad_手, B_verb_rad_手 |
| 53 | 間 | あいだ | N4 | kun | kun | ✓ | IL2_single_default |
| 54 | 合う | あう | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 55 | ～合う | あう | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 56 | 遭う | あう | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 57 | 青空 | あおぞら | N4 | kun+kun~ | kun+kun | ✓ |  |
| 58 | 赤字 | あかじ | N4 | kun+on~ | kun+kun | ✗ | A3_short_compound |
| 59 | 赤ちゃん | あかちゃん | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 60 | 上る | あがる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 61 | 赤ん坊 | あかんぼう | N4 | kun+on~ | on+kun | ✓ | IL1_okurigana, A1_compound_oku, A1_on_kun_mix |
| 62 | 空く | あく | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 63 | accessory | アクセサリー | N4 | no_kanji | no_kanji | ✓ |  |
| 64 | 挙げる | あげる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri, B_verb_rad_手 |
| 65 | 憧れ | あこがれ | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 66 | 浅い | あさい | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 67 | 味 | あじ | N4 | kun | kun | ✓ | IL2_single_default |
| 68 | Asia | アジア | N4 | no_kanji | no_kanji | ✓ |  |
| 69 | 遊び | あそび | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 70 | 与える | あたえる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 71 | 温める/暖める | あたためる | N4 | kun+kun~ | on+kun | ✗ | IL1_okurigana, A1_compound_oku, A1_on_kun_mix |
| 72 | 辺り | あたり | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 73 | 当たる | あたる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 74 |  | あちこち | N4 | no_kanji | no_kanji | ✓ |  |
| 75 |  | あちらこちら | N4 | no_kanji | no_kanji | ✓ |  |
| 76 |  | あっちこっち | N4 | no_kanji | no_kanji | ✓ |  |
| 77 | 集まる | あつまる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 78 | 集める | あつめる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 79 | 当てる | あてる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 80 | address | アドレス | N4 | no_kanji | no_kanji | ✓ |  |
| 81 | announcer | アナウンサー | N4 | no_kanji | no_kanji | ✓ |  |
| 82 | animation | アニメ | N4 | no_kanji | no_kanji | ✓ |  |
| 83 |  | あのね | N4 | no_kanji | no_kanji | ✓ |  |
| 84 | 油 | あぶら | N4 | kun | kun | ✓ | IL2_single_default |
| 85 | Africa | アフリカ | N4 | no_kanji | no_kanji | ✓ |  |
| 86 | 編み物 | あみもの | N4 | kun+kun~ | on+kun | ✗ | IL1_okurigana, A1_compound_oku, A1_on_kun_mix |
| 87 | 編む | あむ | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 88 | America | アメリカ | N4 | no_kanji | no_kanji | ✓ |  |
| 89 | 謝る | あやまる | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri, B_verb_rad_言 |
| 90 |  | あら | N4 | no_kanji | no_kanji | ✓ |  |
| 91 | alarm | アラーム | N4 | no_kanji | no_kanji | ✓ |  |
| 92 | 表す | あらわす | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 93 |  | ある | N4 | no_kanji | no_kanji | ✓ |  |
| 94 | alcohol（荷） | アルコール | N4 | unknown | kun | ✗ | IL2_single_default |
| 95 | Arbeit（德） | アルバイト | N4 | on~ | on | ✓ | IL2_on_only |
| 96 |  | あれ | N4 | no_kanji | no_kanji | ✓ |  |
| 97 |  | あれえ | N4 | no_kanji | no_kanji | ✓ |  |
| 98 |  | あれっ | N4 | no_kanji | no_kanji | ✓ |  |
| 99 | 淡い | あわい | N4 | kun | kun | ✓ | IL1_okurigana, IL2_single_okuri |
| 100 | 安心 | あんしん | N4 | on+on | kun+kun | ✗ | B_noun_rad_宀 |