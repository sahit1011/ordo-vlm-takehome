"""Scoring: normalized match (primary) + ANLS (secondary).

Primary metric: an answer is correct if, after normalization, the ground
truth (or any accept_also alias) appears in the model output. Short factual
answers make substring-after-normalization a reasonable and auditable rule;
every judgment is logged so a human can overrule in review.
"""

import re
import unicodedata


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("₹", " rs ").replace("$", " usd ")
    s = re.sub(r"[^\w\s.]", " ", s)               # drop punctuation
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)     # keep dots only inside numbers
    s = re.sub(r"\b(\d+)\.0+\b", r"\1", s)        # 180.00 -> 180
    return re.sub(r"\s+", " ", s).strip()


def is_correct(prediction: str, answer: str, accept_also: str = "") -> bool:
    pred = normalize(prediction)
    candidates = [answer] + [a for a in accept_also.split("|") if a.strip()]
    return any(normalize(c) in pred for c in candidates if c.strip())


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def anls(prediction: str, answer: str, accept_also: str = "", tau: float = 0.5) -> float:
    """ANLS (DocVQA-style), best over aliases.

    Models answer in full sentences while ground truth is a short fact, so we
    score the best-matching token span of the prediction, not the whole string.
    """
    pred_tokens = normalize(prediction).split()
    best = 0.0
    for c in [answer] + [a for a in accept_also.split("|") if a.strip()]:
        c = normalize(c)
        n = max(len(c.split()), 1)
        spans = [" ".join(pred_tokens[i:i + n])
                 for i in range(max(len(pred_tokens) - n + 1, 1))] or [""]
        for s in spans:
            nl = levenshtein(s, c) / max(len(s), len(c), 1)
            best = max(best, 1.0 - nl if nl < tau else 0.0)
    return best
