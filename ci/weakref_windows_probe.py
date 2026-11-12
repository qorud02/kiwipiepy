"""Isolate Kiwi weakref lifetime checks so native crashes are observable."""
import argparse
import json
import platform
from pathlib import Path
import subprocess
import sys

CHILD = r'''
import ctypes, gc, sys, weakref
if sys.platform == "win32":
    ctypes.windll.kernel32.SetErrorMode(0x8003)
from kiwipiepy import Kiwi, TypoTransformer
kind, with_weakref = sys.argv[1], sys.argv[2] == "1"
called = []
if kind == "kiwi":
    obj = Kiwi(num_workers=1)
    obj.tokenize("안녕하세요")
elif kind == "token":
    kiwi = Kiwi(num_workers=1)
    obj = kiwi.tokenize("안녕하세요")[0]
else:
    obj = TypoTransformer([])
if with_weakref:
    ref = weakref.ref(obj, lambda r: called.append("called"))
del obj
gc.collect()
print("released", flush=True)
if with_weakref:
    assert ref() is None
    assert called == ["called"]
print("ok", flush=True)
'''
parser = argparse.ArgumentParser()
parser.add_argument("--expect", choices=["baseline", "patched"], required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
import kiwipiepy
report = {"python": sys.version, "platform": platform.platform(),
          "module": kiwipiepy.__file__, "version": kiwipiepy.__version__,
          "expect": args.expect, "results": []}
ok = True
for kind in ("kiwi", "token", "typo"):
    for mode in (False, True):
        result = subprocess.run([sys.executable, "-c", CHILD, kind, str(int(mode))],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=120)
        expected = 0xc0000005 if args.expect == "baseline" and mode else 0
        entry = {"kind": kind, "weakref": mode, "returncode": result.returncode,
                 "code_hex": hex(result.returncode & 0xffffffff),
                 "expected": hex(expected), "stdout": result.stdout,
                 "stderr": result.stderr}
        entry["pass"] = (result.returncode & 0xffffffff) == expected
        ok &= entry["pass"]
        report["results"].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
assert ok, report
