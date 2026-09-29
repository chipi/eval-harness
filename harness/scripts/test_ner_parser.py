"""The JSON repairs must fix the observed failures and must NOT invent answers.

Every case here is one an arm actually produced on the Few-NERD dev slice, plus the
negative cases that stop the repairs going too far. The asymmetry is the point: widening
a parser to accept a readable answer is legitimate, widening it to mine entities out of
an explanation would be scoring answers the model never gave.
"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]
                        / "examples" / "ner-few-nerd"))
from adapter import _parse_entities
ok = []
def check(label, cond, got=None):
    ok.append(cond); print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"  -> {got!r}" if not cond else ""))

# observed on the dev slice
r1 = _parse_entities('{"text": "p", "type": "other"}')
check("deepseek_s bare object -> one-element set", r1 == [{"text":"p","type":"other"}], r1)
r2 = _parse_entities('[\n  {\n    "text": "Palm Beach County",type: "location"\n  }\n]')
check("llama_m unquoted key repaired", r2 == [{"text":"Palm Beach County","type":"location"}], r2)

# must still work
check("plain array", _parse_entities('[{"text":"X","type":"person"}]') == [{"text":"X","type":"person"}])
check("fenced", _parse_entities('```json\n[{"text":"X","type":"person"}]\n```') == [{"text":"X","type":"person"}])
check("empty array stays empty (NOT None)", _parse_entities("[]") == [])
check("trailing comma", _parse_entities('[{"text":"X","type":"person"},]') == [{"text":"X","type":"person"}])

# must NOT invent
check("prose -> None", _parse_entities("Let me analyze this sentence. The entity is X, a person.") is None)
check("empty string -> None", _parse_entities("") is None)
check("refusal text -> None", _parse_entities("You didn't provide the sentence.") is None)
# the repair must not corrupt a value containing a colon
r3 = _parse_entities('[{"text": "Trip: The Movie", "type": "art"}]')
check("colon inside a value survives", r3 == [{"text":"Trip: The Movie","type":"art"}], r3)
# A VALID LIST FOLLOWED BY PROSE. The array search used to be skipped whenever the body
# already started with "[", so `[{...}]\n\nI hope this helps!` went to json.loads whole
# and failed -- a correct answer with a courtesy sentence scored zero, and that may be
# part of what the NER report counted as "unreadable". Found by external review.
r4 = _parse_entities('[{"text": "Paris", "type": "location"}]\n\nI hope this helps!')
check("trailing prose after a valid array", r4 == [{"text":"Paris","type":"location"}], r4)
r5 = _parse_entities('Here you go:\n[{"text": "Paris", "type": "location"}]')
check("leading prose before a valid array", r5 == [{"text":"Paris","type":"location"}], r5)
check("prose with no array at all is still unreadable",
      _parse_entities("I could not find any entities.") is None)

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
