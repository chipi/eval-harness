"""Does the set scorer do what the docstring claims? Checked before any arm uses it."""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "examples" / "_shared"))
from extraction import score_sets, normalize, prf, as_members

G = json.dumps([{"text": "Grill Room", "type": "building"},
                {"text": "New York", "type": "location"}])
def f1(pred, gold=G): return score_sets(pred, gold)["f1"]
ok = []
def check(label, cond): ok.append((label, cond)); print(f"  {'ok  ' if cond else 'FAIL'} {label}")

check("perfect match -> 1.0", f1([{"text":"Grill Room","type":"building"},
                                  {"text":"New York","type":"location"}]) == 1.0)
check("case/punct insensitive", f1([{"text":"grill room.","type":"Building"},
                                    {"text":"new york","type":"LOCATION"}]) == 1.0)
check("leading article dropped", f1([{"text":"the Grill Room","type":"building"},
                                     {"text":"New York","type":"location"}]) == 1.0)
check("half found -> 0.667", abs(f1([{"text":"New York","type":"location"}]) - 2/3) < 1e-9)
check("wrong type is a miss", f1([{"text":"Grill Room","type":"location"},
                                  {"text":"New York","type":"location"}]) == 0.5)
r = score_sets([{"text":"Grill Room","type":"location"},
                {"text":"New York","type":"location"}], G)
check("untyped_f1 sees both spans", r["untyped_f1"] == 1.0)
check("type_penalty = untyped - typed", abs(r["type_penalty"] - 0.5) < 1e-9)
check("empty gold + empty pred -> 1.0", score_sets([], json.dumps([]))["f1"] == 1.0)
check("empty gold + prediction -> 0.0",
      score_sets([{"text":"X","type":"person"}], json.dumps([]))["f1"] == 0.0)
check("gold + empty pred -> 0.0", f1([]) == 0.0)
# one-to-one: two identical predictions must not both match one gold
r2 = prf(as_members([{"text":"New York","type":"location"}]*2, True),
         as_members([{"text":"New York","type":"location"}], True))
check("one-to-one: duplicate pred scores tp=1", r2["tp"] == 1.0 and r2["fp"] == 1.0)
check("unparseable gold -> treated as empty", score_sets([], "not json")["f1"] == 1.0)
print(f"\n{sum(1 for _, c in ok if c)}/{len(ok)} passed")
sys.exit(0 if all(c for _, c in ok) else 1)
