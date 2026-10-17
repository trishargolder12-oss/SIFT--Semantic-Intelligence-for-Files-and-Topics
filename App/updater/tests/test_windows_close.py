"""Exercise real WM_CLOSE against isolated native fixtures, never the user's app."""
import importlib.util
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('updater_close', Path(__file__).parents[1] / 'sift_updater.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def test_only_registered_installation_window_closes(tmp_path):
    compiler = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.exists():
        pytest.skip('Windows .NET Framework compiler is unavailable')
    source = tmp_path / 'Window.cs'
    source.write_text('''using System; using System.IO; using System.Windows.Forms;
class Fixture {
 [STAThread] static void Main(string[] args) {
  Form form = new Form(); form.Text="SIFT updater isolated test";
  form.ShowInTaskbar=false; form.Opacity=0;
  form.Shown += (sender, e) => File.WriteAllText(args[0], "ready");
  Application.Run(form);
 }
}''')
    approved, other = tmp_path / 'approved', tmp_path / 'unrelated'
    approved.mkdir()
    other.mkdir()
    result = subprocess.run([str(compiler), '/nologo', '/target:winexe', '/reference:System.Windows.Forms.dll',
                             '/out:' + str(approved / 'SIFT.exe'), str(source)], capture_output=True)
    assert result.returncode == 0, result.stdout
    shutil.copyfile(approved / 'SIFT.exe', other / 'SIFT.exe')
    processes = []
    try:
        for directory in (approved, other):
            marker = directory / 'ready'
            process = subprocess.Popen([str(directory / 'SIFT.exe'), str(marker)])
            processes.append(process)
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            assert marker.exists(), 'Native fixture did not become ready'
        updater.close_sift([{'location': approved}])
        assert processes[0].wait(timeout=5) == 0
        assert processes[1].poll() is None
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
