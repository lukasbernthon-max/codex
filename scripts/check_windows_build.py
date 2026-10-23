"""Run the actual bundled app and preserve its exit status and smoke report."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    executable = Path('dist/Focus.exe').resolve()
    report = Path(os.environ['RUNNER_TEMP']) / 'focus-smoke.json'
    report.unlink(missing_ok=True)
    try:
        result = subprocess.run([str(executable), '--smoke-report', str(report)], timeout=120)
        details = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {'status': 'missing report'}
        print(json.dumps({'exit_code': result.returncode, 'report': details}), flush=True)
        if result.returncode != 0 or details.get('status') != 'passed':
            raise RuntimeError(f'App exit {result.returncode}: {details}')
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        executable.with_name('SHA256SUMS.txt').write_text(digest + '  Focus.exe\n', encoding='ascii')
    except Exception as error:
        message = str(error).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error title=Packaged app diagnostic::{message}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
