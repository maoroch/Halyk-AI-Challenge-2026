import json

with open("submission.json") as f:
    sub = json.load(f)["answers"]
with open("docs/agentic-bank-public/ground_truth.json") as f:
    gt = json.load(f)["scenarios"]

print(f"{'SCEN':<5} | {'CLAUSE':<6} | {'SUBMISSION':<42} | {'GROUND TRUTH':<42} | {'STATUS':<7} | {'ACTUAL':<7} | {'EVID':<7}")
print("-" * 125)

total = 0
status_matches = 0
actual_matches = 0
evidence_matches = 0
exact_cell_matches = 0

for scen in sorted(gt.keys()):
    scen_gt = gt[scen].get("covenants", {})
    scen_sub = sub.get(scen, {})

    for clause in ["6.1", "6.2", "6.3"]:
        total += 1
        s_cell = scen_sub.get(clause, {})
        g_cell = scen_gt.get(clause, {})

        s_st = s_cell.get("status")
        s_act = s_cell.get("actual")
        s_ev = s_cell.get("evidence_txn_id")

        g_st = g_cell.get("status")
        g_act = g_cell.get("actual")
        g_ev = g_cell.get("evidence_txn_id")

        s_str = f"st={s_st} act={s_act} ev={s_ev}"
        g_str = f"st={g_st} act={g_act} ev={g_ev}"

        st_match = (s_st == g_st)
        act_match = (abs((s_act or 0) - (g_act or 0)) < 0.05) if (s_act is not None and g_act is not None) else False
        ev_match = (s_ev == g_ev)

        if st_match:
            status_matches += 1
        if act_match:
            actual_matches += 1
        if ev_match:
            evidence_matches += 1

        if st_match and act_match and ev_match:
            exact_cell_matches += 1

        st_flag = "OK" if st_match else "FAIL"
        act_flag = "OK" if act_match else "FAIL"
        ev_flag = "OK" if ev_match else "FAIL"

        print(f"{scen:<5} | {clause:<6} | {s_str:<42} | {g_str:<42} | {st_flag:<7} | {act_flag:<7} | {ev_flag:<7}")

print("=" * 125)
print(f"Total covenant cells evaluated : {total}")
print(f"Status Matches                 : {status_matches} / {total} ({status_matches/total*100:.1f}%)")
print(f"Actual Metric Matches          : {actual_matches} / {total} ({actual_matches/total*100:.1f}%)")
print(f"Evidence Txn ID Matches        : {evidence_matches} / {total} ({evidence_matches/total*100:.1f}%)")
print(f"100% Exact Cell Matches        : {exact_cell_matches} / {total} ({exact_cell_matches/total*100:.1f}%)")
