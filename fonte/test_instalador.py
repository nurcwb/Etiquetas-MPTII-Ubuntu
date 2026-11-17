"""Exercita o instalador com comandos simulados; não modifica o CUPS real."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

MOCK = r'''
import json, os, sys
from pathlib import Path
cmd = Path(sys.argv[0]).name
args = sys.argv[1:]
folder = Path(os.environ['MOCK_DIR'])
with (folder/'commands.jsonl').open('a') as log:
    log.write(json.dumps([cmd] + args) + '\n')
mode = os.environ.get('MOCK_MODE', '')
if cmd == 'sudo':
    if args == ['-v']: sys.exit(0)
    os.execvp(args[0], args)
elif cmd == 'id': print('1000')
elif cmd == 'uname': print('x86_64')
elif cmd == 'dpkg-query':
    if mode == 'missing': sys.exit(1)
    print('install ok installed', end='')
elif cmd == 'lpinfo':
    if mode == 'absent': print('network socket')
    elif mode == 'multiple':
        print('direct usb://TECH/CLA58?serial=SECOND')
        print('direct usb://TECH/CLA58?serial=FIRST')
    else: print('direct usb://TECH/CLA58?serial=NEW123&interface=0')
elif cmd == 'lpadmin':
    if mode == 'raw_failure': sys.exit(1)
    (folder/'configured').write_text(args[args.index('-v')+1])
elif cmd == 'lpstat':
    if '-v' in args:
        if (folder/'configured').exists():
            print('device for MPTII: ' + (folder/'configured').read_text())
        elif mode == 'existing_other': print('device for MPTII: usb://Other/Printer')
        elif mode == 'existing_same': print('device for MPTII: usb://TECH/CLA58?serial=NEW123&interface=0')
        else: sys.exit(1)
    else: print('printer MPTII is idle. enabled')
'''


class InstallerTests(unittest.TestCase):
    def run_install(self, mode='', answer=''):
        with tempfile.TemporaryDirectory(prefix='mptii installer ') as folder:
            root = Path(folder)
            binary_dir = root/'bin'; binary_dir.mkdir()
            for name in ('sudo','id','uname','dpkg-query','apt-get','systemctl','lpinfo','lpstat','lpadmin','cupsenable','cupsaccept','Etiquetas-MPTII'):
                p = binary_dir/name
                p.write_text('#!' + sys.executable + '\n' + MOCK)
                p.chmod(0o755)
            source = Path(__file__).resolve().parent.parent/'instalar.sh'
            # O fonte exportado pode ter o instalador ao lado deste arquivo.
            if not source.exists(): source = Path(__file__).with_name('instalar.sh')
            shutil.copy2(source, binary_dir/'instalar.sh')
            result = subprocess.run(['bash', str(binary_dir/'instalar.sh')], input=answer, text=True,
                                    capture_output=True, timeout=10,
                                    env=dict(os.environ, PATH=str(binary_dir)+':'+os.environ['PATH'],
                                             MOCK_DIR=folder, MOCK_MODE=mode))
            calls = [json.loads(line) for line in (root/'commands.jsonl').read_text().splitlines()]
            return result, calls

    def test_new_printer_and_shortcut(self):
        result, calls = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        admin = next(c for c in calls if c[0]=='lpadmin')
        self.assertEqual(admin[admin.index('-v')+1], 'usb://TECH/CLA58?serial=NEW123&interface=0')
        self.assertIn('raw', admin)
        self.assertIn(['Etiquetas-MPTII','--install-kde'], calls)
        self.assertFalse(any(c[0]=='apt-get' for c in calls))

    def test_installs_missing_cups(self):
        result, calls = self.run_install('missing')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['apt-get','update'], calls)
        self.assertIn(['apt-get','install','-y','cups','cups-client'], calls)

    def test_disconnected_does_not_create_queue(self):
        result, calls = self.run_install('absent')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0]=='lpadmin' for c in calls))

    def test_existing_same_is_idempotent(self):
        result, calls = self.run_install('existing_same')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_other_requires_choice(self):
        result, calls = self.run_install('existing_other', 'n\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0]=='lpadmin' for c in calls))
        result, calls = self.run_install('existing_other', 's\n')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multiple_printers(self):
        result, calls = self.run_install('multiple', '2\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        admin = next(c for c in calls if c[0]=='lpadmin')
        self.assertEqual(admin[admin.index('-v')+1], 'usb://TECH/CLA58?serial=SECOND')

    def test_raw_failure_does_not_report_success(self):
        result, calls = self.run_install('raw_failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(['Etiquetas-MPTII','--install-kde'], calls)
        self.assertNotIn('Instalação concluída', result.stdout)


if __name__ == '__main__':
    unittest.main()
