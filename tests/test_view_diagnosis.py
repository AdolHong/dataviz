from pathlib import Path
import subprocess


def test_view_diagnosis_uses_real_status_and_omits_business_payloads():
    script = Path(__file__).parent / 'js/view-diagnosis.mjs'
    result = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
