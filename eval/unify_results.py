#!/usr/bin/env python3
"""
Convert parallel evaluation results to unified format.
Groups results by video ID and aggregates query_times, predictions, and ground_truths.
"""

import json
import sys
from collections import OrderedDict

def unify_results(input_file, output_file):
    # Read all results
    with open(input_file) as f:
        results = [json.loads(line) for line in f]

    # Group by id
    grouped = OrderedDict()
    for r in results:
        vid = r['id']
        if vid not in grouped:
            grouped[vid] = {
                'id': vid,
                'query_times': [],
                'predictions': [],
                'gts': []
            }

        grouped[vid]['query_times'].append(r['query_time'])

        # Parse prediction to int if possible
        pred = r.get('prediction', r.get('pred'))
        if pred is not None:
            try:
                pred = int(pred)
            except (ValueError, TypeError):
                pred = None
        grouped[vid]['predictions'].append(pred)

        grouped[vid]['gts'].append(r.get('ground_truth', r.get('gt')))

    # Write unified format
    with open(output_file, 'w') as f:
        for item in grouped.values():
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"Unified {len(results)} results into {len(grouped)} videos")
    print(f"Output: {output_file}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python unify_results.py <input.jsonl> <output.jsonl>")
        sys.exit(1)

    unify_results(sys.argv[1], sys.argv[2])
