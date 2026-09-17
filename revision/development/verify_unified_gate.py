"""Verify all references and negative fixtures through the production callback."""

import argparse
import hashlib
import json
from pathlib import Path

from qualify_reference_tasks import NEGATIVES
from unified_benchmark import ROOT, evaluate_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    dataset = ROOT / 'synthesis_20.json'
    cases = json.loads(dataset.read_text())['cases']
    rows = []
    for case in cases:
        source = ROOT / 'references' / (case['id'] + '.cir')
        positive = evaluate_candidate(source, case, output / case['id'] / 'reference')
        negative_text = source.read_text()
        for old, new in NEGATIVES[case['id']]:
            assert negative_text.count(old) == 1
            negative_text = negative_text.replace(old, new)
        negative = output / case['id'] / 'negative.cir'
        negative.write_text(negative_text)
        rejected = evaluate_candidate(negative, case, output / case['id'] / 'negative')
        rows.append({'id': case['id'], 'reference': positive.as_dict(), 'negative': rejected.as_dict(),
                     'passed': positive.passed and not rejected.passed})
    report = {'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
              'passed': len(rows) == 20 and all(row['passed'] for row in rows), 'tasks': rows}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'tasks': len(rows), 'qualified': sum(row['passed'] for row in rows),
                      'all_passed': report['passed'], 'failures': [row for row in rows if not row['passed']]}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
