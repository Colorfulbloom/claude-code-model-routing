"""Run every case in a case file through runcase.py. Usage: runbatch.py <cases.json> <first-port>"""
import json, os, subprocess, sys, tempfile
cases = json.load(open(sys.argv[1])); port = int(sys.argv[2])
here = os.path.dirname(os.path.abspath(__file__))
for i, c in enumerate(cases):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump(c, f); f.close()
        out = subprocess.run([sys.executable, os.path.join(here, "runcase.py"), f.name, str(port + i)],
                             capture_output=True, text=True)
    finally:
        os.unlink(f.name)
    print(out.stdout.strip() or out.stderr[-300:], flush=True)
