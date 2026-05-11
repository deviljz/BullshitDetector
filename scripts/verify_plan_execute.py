# -*- coding: utf-8 -*-
"""Verify plan_execute structured output refactor"""
import io, sys, pathlib
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_SRC = pathlib.Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC))

from ai.analyzer import analyze_text_staged as analyze_text

CASES = [
    {
        "id": "hype_title",
        "label": "hype + fake data (GPT-4 IQ 180)",
        "text": (
            "GPT-4 scored 180 on the Wechsler IQ scale, surpassing Einstein's estimated 160. "
            "Dr. James Holler of Stanford's Cognitive Science Lab says this is the first time "
            "any entity has crossed this threshold. Leading academic institutions jointly announced "
            "the AGI era has officially arrived. Investment institutions are piling into AI stocks."
        ),
    },
    {
        "id": "out_of_context",
        "label": "out-of-context quote (mismatched caption)",
        "text": (
            "A famous professor was caught on video claiming China's economy has completely "
            "collapsed and the RMB will reach zero in three months. The clip went viral. "
            "Note: the original video was the professor discussing a dystopian novel's plot; "
            "someone clipped it and added a false caption to spread panic."
        ),
    },
    {
        "id": "basically_true",
        "label": "basically true (normal news)",
        "text": (
            "China's National Bureau of Statistics released data showing 2024 full-year GDP growth "
            "was 5.0%, meeting the government's target of around 5%. "
            "Total retail sales of consumer goods rose 3.5% year-on-year. "
            "Per capita disposable income grew 5.1% in real terms."
        ),
    },
]

VALID_NATURE = {
    "\u4e8b\u5b9e\u9519\u8bef", "\u5c40\u90e8\u5931\u5b9e", "\u57fa\u672c\u5c5e\u5b9e",
    "\u5938\u5927\u6e32\u67d3", "\u771f\u5b9e\u4f46\u79bb\u8c31", "\u6807\u9898\u515a",
    "\u65ad\u7ae0\u53d6\u4e49", "\u9006\u8f91\u6df7\u4e71",
}
VALID_TITLE_VERDICT = {"\u6709\u95ee\u9898", "\u65e0\u95ee\u9898", "\u65e0\u6cd5\u5224\u65ad", "\u65e0\u6807\u9898", "\u4e0d\u9002\u7528"}
VALID_HYPE_VERDICT = {"\u6709\u5938\u5927", "\u65e0\u5938\u5927", "\u65e0\u6cd5\u5224\u65ad"}

all_pass = True

for c in CASES:
    print(f"\n{'='*60}")
    print(f"[{c['id']}] {c['label']}")
    try:
        result = analyze_text(c["text"])
        h = result.get("header", {})
        ir = result.get("investigation_report", {})
        tlc = ir.get("title_logic_check", {})
        hc = ir.get("hype_check", {})

        nature = h.get("bullshit_nature", "")
        bi = h.get("bullshit_index", "?")
        title_v = tlc.get("verdict", "")
        hype_v = hc.get("verdict", "")
        flaw_list = result.get("flaw_list", [])
        path = result.get("_path", "?")

        # verdict fields only present when AI actually called the tool — empty dict is valid
        ok_nature = nature in VALID_NATURE
        ok_title = (title_v == "") or (title_v in VALID_TITLE_VERDICT)
        ok_hype = (hype_v == "") or (hype_v in VALID_HYPE_VERDICT)

        print(f"  path           : {path}")
        print(f"  bullshit_index : {bi}")
        print(f"  bullshit_nature: {nature}  {'OK' if ok_nature else 'FAIL - invalid!'}")
        print(f"  title_verdict  : {title_v or '(not called)'}  {'OK' if ok_title else 'FAIL - invalid!'}")
        print(f"  hype_verdict   : {hype_v or '(not called)'}  {'OK' if ok_hype else 'FAIL - invalid!'}")
        print(f"  flaw_list      : {flaw_list}")

        if not (ok_nature and ok_title and ok_hype):
            all_pass = False
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        all_pass = False

print(f"\n{'='*60}")
print("Result:", "ALL PASS" if all_pass else "SOME FAILED")
