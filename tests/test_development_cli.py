from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development import __main__ as cli


class DevelopmentCliTests(unittest.TestCase):
    def run_cli(self, arguments):
        service = MagicMock()
        service.url = 'http://127.0.0.1:1'
        service.token = 'fixture-token'
        service.start.return_value = service
        with patch.object(cli, 'DevelopmentServer', return_value=service) as constructor, \
                patch.object(cli.threading, 'Event'), patch.object(cli.signal, 'signal'), \
                patch('builtins.print'):
            cli.main(arguments)
        service.close.assert_called_once()
        return constructor

    def test_default_cli_keeps_workspace_policy(self):
        constructor = self.run_cli(['serve', '--data', 'fixture-data', '--port', '0'])
        self.assertEqual(constructor.call_args.kwargs['execution_policy'], 'workspace-write')
        self.assertFalse(constructor.call_args.kwargs['android_ui'])

    def test_android_root_and_ui_flags_are_explicitly_forwarded(self):
        constructor = self.run_cli(['serve', '--execution-policy', 'android-root', '--android-ui'])
        self.assertEqual(constructor.call_args.kwargs['execution_policy'], 'android-root')
        self.assertTrue(constructor.call_args.kwargs['android_ui'])


if __name__ == '__main__':
    unittest.main()
