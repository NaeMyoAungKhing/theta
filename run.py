#!/usr/bin/env python3
"""One command: PDF -> Theta card (AI reads it, then renders).

    python run.py paper.pdf

Requires ANTHROPIC_API_KEY (for the reading step). If you'd rather write the
JSON yourself, skip this and run:  python theta.py paper.pdf your.fields.json
"""
import sys, os, subprocess
if len(sys.argv) < 2:
    print(__doc__); sys.exit(1)
pdf = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "ai_extract.py"), pdf], check=True)
fields = os.path.splitext(pdf)[0] + ".fields.json"
subprocess.run([sys.executable, os.path.join(here, "theta.py"), pdf, fields], check=True)
print("done ->", os.path.splitext(pdf)[0] + ".theta.svg")
