#!/usr/bin/env python3
"""
Compute VCBench metrics (GPA, MoC, UDA) from unified format results.
Based on taxonomy_and_metrics.md specification.
"""

import json
import math
from collections import defaultdict

def sign(x):
    """Sign function: +1 if x > 0, -1 if x < 0, 0 if x == 0"""
    return 1 if x > 0 else (-1 if x < 0 else 0)

# Subtype applicability
MOC_SUBTYPES = {'O2-Unique', 'E1-Action', 'E1-Transit', 'E2-Periodic', 'E2-Episode'}
UDA_SUBTYPES = {'O1-Snap', 'O2-Unique', 'E1-Action', 'E1-Transit', 'E2-Periodic', 'E2-Episode'}

def compute_gpa(predictions, gts):
    """
    Gaussian Precision Accuracy
    GPA = (1/n) * Σ exp(-(p_i - g_i)^2 / (2*σ_i^2))
    where σ_i = 0.05 * max(g_i, 1)
    """
    n = len(predictions)
    if n == 0:
        return None

    total = 0.0
    for p, g in zip(predictions, gts):
        sigma = 0.05 * max(g, 1)
        error_sq = (p - g) ** 2
        total += math.exp(-error_sq / (2 * sigma ** 2))

    return total / n

def compute_moc(predictions):
    """
    Monotonicity Consistency
    MoC = v / (n-1), where v is the first violation position
    Returns 1.0 if fully monotonic, 0.0 if first pair violates
    """
    n = len(predictions)
    if n < 2:
        return None

    # Find first violation
    for i in range(n - 1):
        if predictions[i + 1] < predictions[i]:
            # Violation at position i
            return i / (n - 1)

    # No violation, fully monotonic
    return 1.0

def compute_uda(predictions, gts):
    """
    Update Direction Accuracy
    UDA = (1/(n-1)) * Σ 1[dir(p_i, p_{i+1}) == dir(g_i, g_{i+1})]
    """
    n = len(predictions)
    if n < 2:
        return None

    matches = 0
    for i in range(n - 1):
        pred_dir = sign(predictions[i + 1] - predictions[i])
        gt_dir = sign(gts[i + 1] - gts[i])
        if pred_dir == gt_dir:
            matches += 1

    return matches / (n - 1)

def load_subtype_mapping(eval_path):
    """Load q_id -> subtype mapping from eval file"""
    mapping = {}
    with open(eval_path) as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            mapping[data['id']] = data['counting_subtype']
    return mapping

def compute_metrics(unified_path, eval_path):
    """
    Compute metrics from unified format results

    Parameters
    ----------
    unified_path : str
        Path to *_unified.jsonl (format: {"id": "...", "query_times": [...], "predictions": [...], "gts": [...]})
    eval_path : str
        Path to vcbench_eval.jsonl (for subtype mapping)
    """
    # Load subtype mapping
    subtype_map = load_subtype_mapping(eval_path)

    # Load unified results
    with open(unified_path) as f:
        results = [json.loads(line) for line in f if line.strip()]

    # Per-question metrics
    per_question = {}
    for r in results:
        qid = r['id']
        preds = r['predictions']
        gts = r['gts']
        n = len(preds)

        # Get subtype
        subtype = subtype_map.get(qid, 'Unknown')

        # GPA (all subtypes)
        gpa = compute_gpa(preds, gts)

        # MoC (only for applicable subtypes with n >= 2)
        moc = None
        if subtype in MOC_SUBTYPES and n >= 2:
            moc = compute_moc(preds)

        # UDA (only for applicable subtypes with n >= 2)
        uda = None
        if subtype in UDA_SUBTYPES and n >= 2:
            uda = compute_uda(preds, gts)

        per_question[qid] = {
            'gpa': gpa,
            'moc': moc,
            'uda': uda,
            'n_queries': n,
            'subtype': subtype,
        }

    # Aggregate by subtype
    subtype_groups = defaultdict(list)
    for qid, m in per_question.items():
        subtype_groups[m['subtype']].append(m)

    by_subtype = {}
    for subtype, ms in subtype_groups.items():
        n = len(ms)
        gpa_vals = [m['gpa'] for m in ms if m['gpa'] is not None]
        moc_vals = [m['moc'] for m in ms if m['moc'] is not None]
        uda_vals = [m['uda'] for m in ms if m['uda'] is not None]

        by_subtype[subtype] = {
            'n_questions': n,
            'gpa': sum(gpa_vals) / len(gpa_vals) if gpa_vals else None,
            'moc': sum(moc_vals) / len(moc_vals) if moc_vals else None,
            'uda': sum(uda_vals) / len(uda_vals) if uda_vals else None,
        }

    # Overall
    all_ms = list(per_question.values())
    gpa_vals = [m['gpa'] for m in all_ms if m['gpa'] is not None]
    moc_vals = [m['moc'] for m in all_ms if m['moc'] is not None]
    uda_vals = [m['uda'] for m in all_ms if m['uda'] is not None]

    overall = {
        'n_questions': len(all_ms),
        'gpa': sum(gpa_vals) / len(gpa_vals) if gpa_vals else None,
        'moc': sum(moc_vals) / len(moc_vals) if moc_vals else None,
        'uda': sum(uda_vals) / len(uda_vals) if uda_vals else None,
        'gpa_n': len(gpa_vals),
        'moc_n': len(moc_vals),
        'uda_n': len(uda_vals),
    }

    return {
        'overall': overall,
        'by_subtype': by_subtype,
        'per_question': per_question
    }

def main():
    import sys

    if len(sys.argv) != 3:
        print("Usage: python compute_metrics.py <unified.jsonl> <eval.jsonl>")
        sys.exit(1)

    unified_path = sys.argv[1]
    eval_path = sys.argv[2]

    print(f"Computing metrics...")
    print(f"  Unified results: {unified_path}")
    print(f"  Eval file: {eval_path}")

    metrics = compute_metrics(unified_path, eval_path)

    # Print results
    print("\n" + "="*60)
    print("OVERALL METRICS")
    print("="*60)
    overall = metrics['overall']
    print(f"Questions: {overall['n_questions']}")
    print(f"GPA:       {overall['gpa']:.4f} (n={overall['gpa_n']})")
    print(f"MoC:       {overall['moc']:.4f} (n={overall['moc_n']})")
    print(f"UDA:       {overall['uda']:.4f} (n={overall['uda_n']})")

    print("\n" + "="*60)
    print("BY SUBTYPE")
    print("="*60)
    for subtype, m in sorted(metrics['by_subtype'].items()):
        print(f"\n{subtype} (n={m['n_questions']})")
        if m['gpa'] is not None:
            print(f"  GPA: {m['gpa']:.4f}")
        if m['moc'] is not None:
            print(f"  MoC: {m['moc']:.4f}")
        if m['uda'] is not None:
            print(f"  UDA: {m['uda']:.4f}")

    # Save to JSON
    output_path = unified_path.replace('.jsonl', '_metrics.json')
    with open(output_path, 'w') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(f"\n\nMetrics saved to: {output_path}")

if __name__ == '__main__':
    main()
