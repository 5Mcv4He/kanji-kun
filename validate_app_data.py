#!/usr/bin/env python3
"""
Validate kanji_app_data.json — internal consistency + cross-reference with network data.
"""
import json, sys, os
from collections import defaultdict, Counter

BASE = os.path.dirname(os.path.abspath(__file__))

# Load app data
with open(os.path.join(BASE, 'app/output/kanji_app_data.json')) as f:
    app = json.load(f)

# Load network data
with open(os.path.join(BASE, 'output/kun_network_data.json')) as f:
    net = json.load(f)

nodes = {n['id']: n for n in net['nodes']}
kanji = app['kanji']
ERR = 0

def err(msg):
    global ERR
    ERR += 1
    print(f"  ❌ {msg}")

def ok(msg):
    print(f"  ✅ {msg}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ═══════════════════════════════════════════════
# 1. Basic integrity
# ═══════════════════════════════════════════════
section("1. Basic Integrity")

total = app['total']
print(f"  Declared total: {total}, Actual kanji: {len(kanji)}")
if total != len(kanji):
    err(f"Total mismatch: {total} != {len(kanji)}")
else:
    ok(f"Total consistent: {total}")

# Every kanji in hubs exists in kanji
missing_hubs = [k for k in app['hubs'] if k not in kanji]
if missing_hubs:
    err(f"Hub kanji missing from data: {missing_hubs[:10]}")
else:
    ok(f"All {len(app['hubs'])} hub kanji exist in data")

# Every kanji has required fields
required = ['ku', 'on', 'lv', 'hub']
missing_fields = defaultdict(list)
for ik, d in kanji.items():
    for f in required:
        if f not in d:
            missing_fields[f].append(ik)
if missing_fields:
    for f, iks in missing_fields.items():
        err(f"Missing field '{f}' in {len(iks)} kanji: {iks[:10]}")
else:
    ok("All kanji have required fields (ku, on, lv, hub)")

# ═══════════════════════════════════════════════
# 2. On-yomi rules (on_rules)
# ═══════════════════════════════════════════════
section("2. On-yomi Rules (on_rules)")

rule_count = sum(len(d.get('on_rules', [])) for d in kanji.values())
kanji_with_rules = sum(1 for d in kanji.values() if d.get('on_rules'))
print(f"  Total rules: {rule_count}, Kanji with rules: {kanji_with_rules}")

# Check each rule
bad_on = 0
bad_conf = 0
bad_tier = 0
rule_types = Counter()

for ik, d in kanji.items():
    on_all = set(d.get('on_all', []))
    if d.get('on'):
        on_all.add(d['on'])

    for r in d.get('on_rules', []):
        # Confidence
        if r.get('c') not in ('确定', '可能'):
            bad_conf += 1
            if bad_conf <= 3:
                err(f"{ik}: bad confidence '{r.get('c')}' in rule '{r.get('t','')}'")

        # Tier
        if r.get('r', 99) > 2:
            bad_tier += 1

        # On-yomi match
        if r.get('o') and on_all and r['o'] not in on_all:
            bad_on += 1
            if bad_on <= 5:
                err(f"{ik}: rule on='{r['o']}' not in kanji on_all={sorted(on_all)}")

        # Rule type
        if '拼音' in r.get('t', ''):
            rule_types['拼音'] += 1
        elif '声符' in r.get('t', ''):
            rule_types['声符'] += 1
        else:
            rule_types['其他'] += 1

if bad_on == 0: ok(f"All rules' on-yomi match the kanji's on_all (0 mismatches)")
else: err(f"{bad_on} rules have on-yomi NOT in kanji's on_all")

if bad_conf == 0: ok("All rules have valid confidence (确定/可能)")
else: err(f"{bad_conf} rules have invalid confidence")

if bad_tier == 0: ok("All rules are tier 1-2")
else: err(f"{bad_tier} rules exceed tier 2")

print(f"  Rule types: {dict(rule_types)}")

# ═══════════════════════════════════════════════
# 3. Stem Families (sf)
# ═══════════════════════════════════════════════
section("3. Stem Families (sf)")

sf_kanji = sum(1 for d in kanji.values() if d.get('sf'))
sf_families = sum(len(d.get('sf', [])) for d in kanji.values())
print(f"  Kanji with sf: {sf_kanji}, Total families: {sf_families}")

bad_sf_refs = 0
bad_sf_stem = 0
sf_size_dist = Counter()

for ik, d in kanji.items():
    for f in d.get('sf', []):
        stem = f.get('st', '')
        sf_size_dist[min(len(f.get('ks', [])), 30)] += 1

        for mk in f.get('ks', []):
            if mk not in kanji:
                bad_sf_refs += 1
                if bad_sf_refs <= 5:
                    err(f"{ik} sf[{stem}] references unknown kanji '{mk}'")

            # Check the referenced kanji actually has this stem in its readings
            if mk in kanji and stem:
                mk_ku = kanji[mk].get('ku', '')
                mk_sf_stems = {sf.get('st', '') for sf in kanji[mk].get('sf', [])}
                # The stem should either match ku or be in the sf stems
                if stem != mk_ku and stem not in mk_sf_stems:
                    # Check if mk appears with this stem in any of its sf families
                    found = any(
                        ik in fam.get('ks', [])
                        for fam in kanji[mk].get('sf', [])
                        if fam.get('st') == stem
                    )
                    if not found:
                        bad_sf_stem += 1
                        if bad_sf_stem <= 5:
                            err(f"{ik} sf[{stem}]→{mk}: {mk} doesn't have stem '{stem}' (ku={mk_ku})")

if bad_sf_refs == 0: ok("All sf kanji references exist")
else: err(f"{bad_sf_refs} sf references to non-existent kanji")

if bad_sf_stem == 0: ok("All sf cross-references are consistent")
else: err(f"{bad_sf_stem} sf cross-reference inconsistencies")

print(f"  Family size distribution (top): {sf_size_dist.most_common(10)}")

# ═══════════════════════════════════════════════
# 4. Same On-yomi (so)
# ═══════════════════════════════════════════════
section("4. Same On-yomi (so)")

so_kanji = sum(1 for d in kanji.values() if d.get('so'))
print(f"  Kanji with so: {so_kanji}")

bad_so = 0
for ik, d in kanji.items():
    on_all = set(d.get('on_all', []))
    if d.get('on'):
        on_all.add(d['on'])

    for g in d.get('so', []):
        r = g.get('r', '')
        for mk in g.get('ks', []):
            if mk not in kanji:
                bad_so += 1
                if bad_so <= 3:
                    err(f"{ik} so[{r}] references unknown '{mk}'")
                continue
            mk_on = set(kanji[mk].get('on_all', []))
            if kanji[mk].get('on'):
                mk_on.add(kanji[mk]['on'])
            if r not in mk_on:
                bad_so += 1
                if bad_so <= 10:
                    err(f"{ik} so[{r}]→{mk}: {mk} does NOT have on-yomi '{r}' (has {sorted(mk_on)})")

if bad_so == 0: ok("All so kanji actually share the claimed on-yomi")
else: err(f"{bad_so} so mismatches (kanji don't share the claimed on-yomi)")

# ═══════════════════════════════════════════════
# 5. Same Component (sc) & Same Radical (rb)
# ═══════════════════════════════════════════════
section("5. Same Component (sc) & Same Radical (rb)")

sc_count = sum(len(d.get('sc', [])) for d in kanji.values())
rb_count = sum(len(d.get('rb', [])) for d in kanji.values())
print(f"  Total sc edges: {sc_count}, Total rb edges: {rb_count}")

bad_sc = 0
bad_rb = 0
for ik, d in kanji.items():
    for mk in d.get('sc', []):
        if mk not in kanji:
            bad_sc += 1
    for mk in d.get('rb', []):
        if mk not in kanji:
            bad_rb += 1

if bad_sc == 0: ok(f"All {sc_count} sc references valid")
else: err(f"{bad_sc} sc references to non-existent kanji")

if bad_rb == 0: ok(f"All {rb_count} rb references valid")
else: err(f"{bad_rb} rb references to non-existent kanji")

# Cross-check: if A has B in sc, B should have A in sc (symmetry from network)
sc_asym = 0
for ik, d in kanji.items():
    for mk in d.get('sc', []):
        if mk in kanji and ik not in kanji[mk].get('sc', []):
            sc_asym += 1
if sc_asym == 0:
    ok("sc is symmetric (A→B implies B→A)")
else:
    print(f"  ⚠️  {sc_asym} asymmetric sc pairs (expected from network build, may be fine)")

# ═══════════════════════════════════════════════
# 6. Transitivity (tr)
# ═══════════════════════════════════════════════
section("6. Transitivity (tr)")

tr_count = sum(len(d.get('tr', [])) for d in kanji.values())
tr_kanji = sum(1 for d in kanji.values() if d.get('tr'))
print(f"  Kanji with tr: {tr_kanji}, Total tr entries: {tr_count}")

patterns = Counter()
bad_tr = 0
for ik, d in kanji.items():
    for t in d.get('tr', []):
        patterns[t.get('p', '?')] += 1
        if not t.get('p'): bad_tr += 1
        if not t.get('a') or not t.get('t'): bad_tr += 1

print(f"  TR patterns: {dict(patterns)}")
if bad_tr == 0: ok("All tr entries have pattern + auto/trans forms")
else: err(f"{bad_tr} tr entries missing pattern or forms")

# ═══════════════════════════════════════════════
# 7. Compounds (cp)
# ═══════════════════════════════════════════════
section("7. Compounds (cp)")

cp_kanji = sum(1 for d in kanji.values() if d.get('cp'))
cp_total = sum(len(d.get('cp', [])) for d in kanji.values())
print(f"  Kanji with cp: {cp_kanji}, Total cp edges: {cp_total}")

bad_cp = 0
for ik, d in kanji.items():
    for mk in d.get('cp', []):
        if mk not in kanji:
            bad_cp += 1

if bad_cp == 0: ok(f"All {cp_total} cp references valid")
else: err(f"{bad_cp} cp references to non-existent kanji")

# ═══════════════════════════════════════════════
# 8. Network data cross-reference
# ═══════════════════════════════════════════════
section("8. Network Data Cross-Reference")

# Check hub ordering matches network degrees
net_degrees = {}
for e in net['edges']:
    s, t = e['source'], e['target']
    net_degrees[s] = net_degrees.get(s, 0) + 1
    net_degrees[t] = net_degrees.get(t, 0) + 1

# Top 10 hubs in app vs network
app_top10 = app['hubs'][:10]
net_ranked = sorted(net_degrees.keys(), key=lambda k: net_degrees.get(k, 0), reverse=True)
print(f"  App top 10 hubs: {', '.join(app_top10)}")
print(f"  Net top 10 hubs: {', '.join(net_ranked[:10])}")

overlap = set(app_top10) & set(net_ranked[:10])
print(f"  Overlap in top 10: {len(overlap)}/10")
if len(overlap) >= 7:
    ok("Hub ranking broadly consistent with network data")
else:
    err(f"Hub ranking diverges significantly from network (only {len(overlap)}/10 overlap)")

# Check stem families against network shared_stem edges
ss_edges = [e for e in net['edges'] if e['type'] == 'shared_stem']
ss_pairs = defaultdict(set)
for e in ss_edges:
    ss_pairs[e['source']].add(e['target'])
    ss_pairs[e['target']].add(e['source'])

sf_in_net = 0
sf_not_in_net = 0
for ik, d in kanji.items():
    for f in d.get('sf', []):
        for mk in f.get('ks', []):
            if mk in ss_pairs.get(ik, set()):
                sf_in_net += 1
            else:
                sf_not_in_net += 1

print(f"  SF pairs found in network: {sf_in_net}, NOT in network: {sf_not_in_net}")
if sf_not_in_net == 0:
    ok("All sf connections verified in network shared_stem edges")
else:
    print(f"  ⚠️  {sf_not_in_net} sf pairs not in network (may be from reading_index derivation, OK)")

# ═══════════════════════════════════════════════
# 9. Spot-check key kanji
# ═══════════════════════════════════════════════
section("9. Spot-Check Key Kanji")

for ik in ['高', '生', '健', '変', '水', '行', '一', '無']:
    d = kanji.get(ik)
    if not d:
        err(f"{ik}: NOT IN DATA")
        continue

    issues = []
    on_all = set(d.get('on_all', []))
    if d.get('on'): on_all.add(d['on'])

    # Check on_rules against on_all
    for r in d.get('on_rules', []):
        if r.get('o') and r['o'] not in on_all:
            issues.append(f"rule '{r['t']}' on='{r['o']}' not in on_all={sorted(on_all)}")

    # Check so consistency
    for g in d.get('so', []):
        for mk in g.get('ks', []):
            if mk in kanji:
                mk_on = set(kanji[mk].get('on_all', []))
                if kanji[mk].get('on'): mk_on.add(kanji[mk]['on'])
                if g['r'] not in mk_on:
                    issues.append(f"so[{g['r']}]→{mk} doesn't have {g['r']}")

    status = "✅" if not issues else f"❌ {len(issues)} issues"
    print(f"  {ik}: ku={d['ku']} on={d['on']} lv={d['lv']} hub={d['hub']} {status}")
    print(f"    sf={len(d.get('sf',[]))} tr={len(d.get('tr',[]))} cp={len(d.get('cp',[]))} sc={len(d.get('sc',[]))} rb={len(d.get('rb',[]))}")
    print(f"    on_rules={len(d.get('on_rules',[]))} so={sum(len(g['ks']) for g in d.get('so',[]))}")
    for issue in issues:
        print(f"    ⚠️  {issue}")

# ═══════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════
section("SUMMARY")

print(f"  Total errors: {ERR}")
if ERR == 0:
    print("  ✅ ALL CHECKS PASSED")
else:
    print(f"  ❌ {ERR} errors found")

# Distribution stats
print(f"\n  On-yomi rules coverage: {kanji_with_rules}/{total} kanji ({kanji_with_rules/total*100:.1f}%)")
print(f"  SF coverage: {sf_kanji}/{total} ({sf_kanji/total*100:.1f}%)")
print(f"  SO coverage: {so_kanji}/{total} ({so_kanji/total*100:.1f}%)")
print(f"  TR coverage: {tr_kanji}/{total} ({tr_kanji/total*100:.1f}%)")
print(f"  CP coverage: {cp_kanji}/{total} ({cp_kanji/total*100:.1f}%)")
