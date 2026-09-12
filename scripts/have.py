"""Quick lookup: which of these words are in the known set?"""
import sys, vocab
lemmas, forms = vocab.known_forms()
weak = vocab.weak_forms()
for w in sys.argv[1:]:
    mark = "✓" if w in forms else "✗"
    if w in weak:
        mark += " (weak)"
    print(f"{mark} {w}")
