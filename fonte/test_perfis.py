import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from etiquetas import ProfileStore


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'perfis.json'
        self.values = {'width': '58', 'height': '30', 'gap': '2,5', 'offset': '-1'}

    def test_save_restore_update_select_and_delete(self):
        store = ProfileStore(self.path)
        self.assertEqual(store.profiles, {})
        store.save('Café 58 × 30', self.values)
        store.save('Produto maior', dict(self.values, height='50'))
        store.select('Café 58 × 30')
        restored = ProfileStore(self.path)
        self.assertEqual(restored.last, 'Café 58 × 30')
        self.assertEqual(restored.profiles[restored.last]['gap'], 2.5)
        self.assertEqual(restored.profiles[restored.last]['offset'], -1)
        restored.save('Café 58 × 30', dict(self.values, gap='3'))
        self.assertEqual(len(restored.profiles), 2)
        self.assertEqual(ProfileStore(self.path).profiles['Café 58 × 30']['gap'], 3)
        restored.delete('Café 58 × 30')
        self.assertNotIn('Café 58 × 30', ProfileStore(self.path).profiles)
        self.assertEqual(ProfileStore(self.path).last, '')

    def test_bad_values_do_not_replace_saved_profiles(self):
        store = ProfileStore(self.path)
        store.save('Teste', self.values)
        before = self.path.read_bytes()
        for values in (dict(self.values, width='200'), dict(self.values, offset='nan')):
            with self.assertRaises(ValueError):
                store.save('Inválido', values)
        self.assertEqual(self.path.read_bytes(), before)
        with patch('etiquetas.os.replace', side_effect=PermissionError('read-only')):
            with self.assertRaises(OSError):
                store.save('Outro', self.values)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertNotIn('Outro', store.profiles)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_corrupt_file_is_preserved(self):
        self.path.write_text('{arquivo danificado')
        store = ProfileStore(self.path)
        self.assertTrue(store.error)
        with self.assertRaises(ValueError):
            store.save('Novo', self.values)
        self.assertEqual(self.path.read_text(), '{arquivo danificado')


if __name__ == '__main__':
    unittest.main()
