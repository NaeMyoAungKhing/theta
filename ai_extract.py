#!/usr/bin/env python3
"""
Optional AI reading step: PDF -> fields.json using the Anthropic API.
Makes Theta a single command (no hand-written JSON).

Setup:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...

Usage:
    python ai_extract.py paper.pdf            # -> paper.fields.json
    python run.py paper.pdf                    # does this + renders the card
"""
import sys, os, json, subprocess, re

def pdf_text_with_lines(path):
    out = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True).stdout
    blocks = []
    for pi, raw in enumerate(out.split("\f"), 1):
        lines = [f"{i}| {ln.rstrip()}" for i, ln in enumerate(raw.split("\n"), 1) if ln.strip()]
        if lines:
            blocks.append(f"===== PAGE {pi} =====\n" + "\n".join(lines))
    return "\n".join(blocks)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    pdf = sys.argv[1]
    text = pdf_text_with_lines(pdf)
    # keep request reasonable: first ~18k chars usually covers abstract+method+results
    prompt = open(os.path.join(os.path.dirname(__file__), "prompts", "extract_prompt.md")).read()
    try:
        import anthropic
    except ImportError:
        print("Run: pip install anthropic"); sys.exit(1)
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        system="You are Theta. Return only valid JSON matching the schema. Never invent data.",
        messages=[{"role": "user", "content": prompt + "\n\nPAPER TEXT:\n" + text[:60000]}],
    )
    raw = msg.content[0].text
    m = re.search(r"\{.*\}", raw, re.S)
    fields = json.loads(m.group(0) if m else raw)
    out = os.path.splitext(pdf)[0] + ".fields.json"
    json.dump(fields, open(out, "w"), indent=2, ensure_ascii=False)
    print("wrote", out)

if __name__ == "__main__":
    main()
