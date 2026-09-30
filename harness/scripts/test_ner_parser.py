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

# THE GREEDY ARRAY BUG. `\[.*\]` with DOTALL spanned the first "[" to the LAST "]",
# so a valid answer followed by any later bracket became one unparseable blob.
check("a valid array followed by a bracketed citation",
      _parse_entities('[{"text":"X","type":"person"}] See [1]')
      == [{"text": "X", "type": "person"}])
check("a valid array between two brackets",
      _parse_entities('Refs [2]: [{"text":"X","type":"person"}]')
      == [{"text": "X", "type": "person"}])

# SELF-CORRECTION. llama_l emitted a malformed array, then "the correct output:", then
# a valid one. The first candidate must fall through to the second, not swallow both.
check("a broken array followed by a good one",
      _parse_entities('[\n {"text":"A","type":"person"},\n "text":"B"\n} ] '
                      'is wrong. Correct:\n[{"text":"A","type":"person"}]')
      == [{"text": "A", "type": "person"}])

# THE SHAPE TEST. "See [1]" is valid JSON and yields [1]; the item loop drops non-dicts,
# so without a shape test it would arrive as an EMPTY set -- scored as "correctly found
# nothing", a free 1.0 on the 15% of items whose gold is empty. That is the bug this
# example already shipped once, arriving by a different road.
check("a bracketed citation alone is NOT an empty answer",
      _parse_entities("I could not find entities. See [1].") is None)
check("a list of non-objects is not an entity set",
      _parse_entities('[1, 2, 3]') is None)
check("an explicit empty array is still an empty answer, not None",
      _parse_entities("[]") == [])

# TRUNCATION STAYS UNREADABLE. glm_l ran out of tokens mid-object; there is no answer
# there, and a repair that invented one would be mining prose for entities.
# AN UNCLOSED BRACKET IS NOT THE END OF THE SCAN. glm_l opened a fragment, restarted,
# and emitted a complete array -- finish_reason=stop, 89 tokens, not a truncation. The
# scan stopped at the stray "[" and reported nothing. One real item of 48.
check("a stray unclosed bracket does not hide a later complete array",
      _parse_entities('Output: [{"text": "Hagar", "type": "[{"text": "Hagar", "type": "person"}]')
      == [{"text": "Hagar", "type": "person"}])
check("but a reply genuinely cut off mid-array is still unreadable",
      _parse_entities('Here goes:\n[\n  {"text": "Corfu International') is None)

check("an array cut off mid-object -> None",
      _parse_entities('Here goes:\n[\n  {"text": "Corfu International') is None)
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
