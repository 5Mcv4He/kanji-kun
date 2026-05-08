#!/usr/bin/env python3
"""
Word Derivation Inspector — 逐词推导器
For any JLPT word, show step-by-step derivation of its reading.
Loads the derivation database from chinese_bridge_v1.py output.

Usage:
  python3 derive.py 消火器          # Derive one word
  python3 derive.py --level N5      # List all N5 words with derivation status
  python3 derive.py --mem N3        # Show N3 words that MUST be memorized
  python3 derive.py --free N4       # Show N4 words that are fully derivable
  python3 derive.py --interactive   # Enter REPL mode
"""

import json, os, sys

OUT = '/Volumes/SSD/work/kanji-kun/output'
DB_PATH = f'{OUT}/derive_db.json'


def load_db():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        print("Run chinese_bridge_v1.py first to generate the derivation database.")
        sys.exit(1)
    with open(DB_PATH) as f:
        return json.load(f)


def print_derivation(info):
    print(f"\n  {'='*60}")
    status_str = {'free': '◎ FREE (完全可推导)', 'must_memorize': '✗ MUST MEMORIZE (需要记忆)',
                  'unknown': '? UNKNOWN'}
    print(f"  {info['word']}  【{info['kana']}】  {info['level']}")
    print(f"  Status: {status_str.get(info['status'], info['status'])}")
    print(f"  Type: GT={info['gt_pattern']} Pred={info['pred_pattern']} "
          f"{'✓' if info['type_correct'] else '✗'}")

    print(f"\n  ┌─ 逐字推导 " + "─" * 45)
    for i, e in enumerate(info['kanji_entries']):
        ch = e['kanji']
        print(f"  │")
        print(f"  │ [{i+1}] {ch}  (部首: {e['radical']})")
        if e.get('pinyin'):
            print(f"  │     Pinyin: {', '.join(e['pinyin'][:3])}")
        if e.get('all_on'):
            print(f"  │     可能音读: {', '.join(e['all_on'][:5])}")
        if e.get('all_kun'):
            print(f"  │     可能训读: {', '.join(e['all_kun'][:5])}")

        print(f"  │     GT类型: {e['gt_type']}  GT读音: {e['gt_seg']}")

        if e['gt_type'] == 'on':
            print(f"  │     --- 音读推导 ---")
            jlpt_d = e.get('jlpt_default', '')
            jlpt_c = e.get('jlpt_confidence', 0)
            print(f"  │     ① JLPT词频默认: {jlpt_d} (置信度{jlpt_c:.0%})")
            if e.get('pin_pred'):
                print(f"  │     ② Pinyin推导: {e['pin_pred']} (置信度{e.get('pin_confidence',0):.0%})")
            if e.get('comp_pred'):
                print(f"  │     ③ 部件推导: {e.get('comp_pred')} (声旁「{e.get('comp_used','')}」)")
            if e.get('is_entering'):
                print(f"  │     ④ 入声约束: ✓ (→短音, 结尾く/つ/ち/き/う/い)")
            if e.get('context_pred') and e.get('context_pred') != e.get('jlpt_default', ''):
                ctx_src = e.get('context_source', '')
                print(f"  │     ⑤ 语境消歧: {e['context_pred']} ({ctx_src})")
            if e.get('multi_on'):
                print(f"  │     ⚠ 多音字 (此字有多个音读)")

        elif e['gt_type'] == 'kun':
            print(f"  │     --- 训读推导 ---")
            print(f"  │     ① JLPT词频默认: {e.get('freq_pred','')}")
            if e.get('multi_kun'):
                print(f"  │     ⚠ 多训字 ({e.get('context_key','')})")
                if e.get('context_pred'):
                    print(f"  │     ② 送假名消歧: {e.get('context_pred')} ← 匹配模式「{e['kanji']}+{e.get('context_key','').replace('oku_','')}」")
                else:
                    print(f"  │     ② 送假名消歧: 无匹配语境")

        result = '✓ 正确' if e['correct'] else '✗ 错误'
        print(f"  │     → 预测: {e['predicted']} {result}")

        if not e['correct'] and e.get('predicted') and e['gt_seg']:
            pred = e['predicted']
            gt = e['gt_seg']
            rendaku_map = str.maketrans(
                'かきくけこさしすせそたちつてとはひふへほ',
                'がぎぐげござじずぜぞだぢづでどばびぶべぼ')
            if len(pred) == len(gt):
                for a, b in zip(pred, gt):
                    if a != b and a.translate(rendaku_map) == b:
                        print(f"  │     ⚡ 原因: 连浊 ({pred}→{gt})，词干正确")
                        break
                else:
                    print(f"  │     ⚡ 原因: 多音/多训选错 → 需单独记忆")
            else:
                print(f"  │     ⚡ 原因: 读音不匹配 → 需单独记忆")

    print(f"  └" + "─" * 57)

    can_predict = all(e.get('predicted') and e['predicted'] != '?' for e in info['kanji_entries'])
    all_correct = all(e.get('correct', False) for e in info['kanji_entries'])
    if can_predict and all_correct:
        print(f"  ◎ 全部读音可推导，记忆成本 = 0")
    elif can_predict:
        wrong_kanji = [e['kanji'] for e in info['kanji_entries'] if not e.get('correct', False)]
        print(f"  ✗ 需记忆: {'、'.join(wrong_kanji)} 的读音")
    print()


def list_by_level(db, level, status_filter=None):
    """List words for a JLPT level, optionally filtered by status."""
    words = [(k, v) for k, v in db['word_index'].items()
             if v['level'] == level]
    if status_filter:
        words = [(k, v) for k, v in words if v['status'] == status_filter]

    words.sort(key=lambda x: x[0])
    return words


def main():
    db = load_db()
    word_index = db['word_index']

    if len(sys.argv) < 2 or sys.argv[1] in ('-i', '--interactive'):
        # Interactive REPL
        print(f"\n  Word Derivation Inspector")
        print(f"  {db['total_free']} words fully derivable, {db['total_memorize']} must memorize")
        print(f"\n  Enter a JLPT word (e.g. 安心, 生け花, 食べる)")
        print(f"  Commands: !free N5  !mem N3  !all N1  q=quit\n")
        while True:
            try:
                cmd = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not cmd:
                continue
            if cmd == 'q':
                break
            if cmd.startswith('!'):
                parts = cmd.split()
                action = parts[0][1:]
                level = parts[1] if len(parts) > 1 else None
                if action == 'free' and level:
                    words = list_by_level(db, level, 'free')
                    print(f"\n  {level} Fully Derivable ({len(words)} words):")
                    for w, info in words[:20]:
                        print(f"    {info['word']} 【{info['kana']}】")
                    if len(words) > 20:
                        print(f"    ... and {len(words)-20} more")
                elif action == 'mem' and level:
                    words = list_by_level(db, level, 'must_memorize')
                    print(f"\n  {level} Must Memorize ({len(words)} words):")
                    for w, info in words[:20]:
                        print(f"    {info['word']} 【{info['kana']}】 → {info['gt_pattern']}")
                    if len(words) > 20:
                        print(f"    ... and {len(words)-20} more")
                elif action == 'all' and level:
                    free = list_by_level(db, level, 'free')
                    mem = list_by_level(db, level, 'must_memorize')
                    unk = list_by_level(db, level, 'unknown')
                    total = len(free) + len(mem) + len(unk)
                    print(f"\n  {level} Summary: {total} words")
                    print(f"    ◎ FREE: {len(free)} ({len(free)/max(total,1):.0%})")
                    print(f"    ✗ MEM:  {len(mem)} ({len(mem)/max(total,1):.0%})")
                    print(f"    ? UNK:  {len(unk)}")
                else:
                    print(f"  Usage: !free <level>  !mem <level>  !all <level>")
                print()
                continue

            if cmd in word_index:
                print_derivation(word_index[cmd])
            else:
                matches = [k for k in word_index if cmd in k]
                if not matches:
                    print(f"  '{cmd}' not found. Try a JLPT word.\n")
                elif len(matches) == 1:
                    print_derivation(word_index[matches[0]])
                else:
                    print(f"  Multiple matches ({len(matches)}):")
                    for m in sorted(matches)[:15]:
                        info = word_index[m]
                        status_icon = '◎' if info['status'] == 'free' else '✗'
                        print(f"    {status_icon} {m} 【{info['kana']}】 {info['level']}")
                    print()
        return

    # Command-line mode: python3 derive.py <word>
    query = sys.argv[1]

    if query.startswith('--'):
        # --level N5, --mem N3, --free N4
        if query == '--level' and len(sys.argv) > 2:
            level = sys.argv[2]
            words = list_by_level(db, level)
            free = [w for w in words if w[1]['status'] == 'free']
            mem = [w for w in words if w[1]['status'] == 'must_memorize']
            print(f"\n  {level} ({len(words)} words)")
            print(f"    ◎ FREE: {len(free)} ({len(free)/max(len(words),1):.0%})")
            print(f"    ✗ MEM:  {len(mem)} ({len(mem)/max(len(words),1):.0%})")
            if mem:
                print(f"\n  Must Memorize List:")
                for w, info in mem:
                    print(f"    ✗ {info['word']:20s} 【{info['kana']:20s}】 {info['gt_pattern']}")
        elif query == '--mem' and len(sys.argv) > 2:
            level = sys.argv[2]
            words = list_by_level(db, level, 'must_memorize')
            print(f"\n  {level} Must Memorize ({len(words)} words):")
            for w, info in words:
                # Show which kanji need memorization
                bad = [e['kanji'] for e in info['kanji_entries'] if not e.get('correct', False)]
                print(f"    ✗ {info['word']:20s} 【{info['kana']:20s}】 {'、'.join(bad)}")
        elif query == '--free' and len(sys.argv) > 2:
            level = sys.argv[2]
            words = list_by_level(db, level, 'free')
            print(f"\n  {level} Fully Derivable ({len(words)} words):")
            for w, info in words:
                print(f"    ◎ {info['word']:20s} 【{info['kana']:20s}】")
        else:
            print("Usage: derive.py <word> | --level N5 | --mem N3 | --free N4 | --interactive")
    else:
        if query in word_index:
            print_derivation(word_index[query])
        else:
            matches = [k for k in word_index if query in k]
            if len(matches) == 1:
                print_derivation(word_index[matches[0]])
            elif matches:
                print(f"Multiple matches for '{query}':")
                for m in sorted(matches)[:15]:
                    info = word_index[m]
                    status_icon = '◎' if info['status'] == 'free' else '✗'
                    print(f"  {status_icon} {m} 【{info['kana']}】 {info['level']}")
            else:
                print(f"'{query}' not found.")


if __name__ == '__main__':
    main()
