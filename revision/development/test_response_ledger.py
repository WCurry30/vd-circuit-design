"""Exercise the production ledger without network access or SDK installation."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from alignment_runner import ProviderInterruption, ResponseLedger


class LedgerRestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.network = []
        self.sdk = ModuleType('openai')
        chat = ModuleType('openai.types.chat')
        class Response:
            model = 'fixture'
            def model_dump(self, **kwargs):
                return {'model': self.model}
            @classmethod
            def model_validate(cls, data):
                obj = cls()
                obj.model = data['model']
                return obj
        def factory(**kwargs):
            def create(**request):
                self.network.append(request)
                return Response()
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self.sdk.OpenAI = factory
        chat.ChatCompletion = Response
        modules = {'openai': self.sdk, 'openai.types': ModuleType('openai.types'),
                   'openai.types.chat': chat}
        patcher = patch.dict('sys.modules', modules)
        patcher.start()
        self.addCleanup(patcher.stop)

    def client(self):
        ledger = ResponseLedger(expected_model='fixture')
        ledger.install()
        return ledger, self.sdk.OpenAI()

    def test_completed_response_replays_without_second_transport(self):
        ledger, client = self.client()
        request = {'model': 'fixture', 'messages': [{'role': 'user', 'content': 'design'}]}
        for _ in range(2):
            with ledger.scope(self.root):
                result = client.chat.completions.create(**request)
                self.assertEqual(result.model, 'fixture')
                self.assertEqual(ledger.index, 1)
        self.assertEqual(len(self.network), 1)

    def test_changed_request_stops_before_transport(self):
        ledger, client = self.client()
        with ledger.scope(self.root):
            client.chat.completions.create(model='fixture', messages=[])
        with self.assertRaises(ProviderInterruption):
            with ledger.scope(self.root):
                client.chat.completions.create(model='fixture', messages=[{'role': 'user', 'content': 'changed'}])
        self.assertEqual(len(self.network), 1)

    def test_ambiguous_interruption_stops_before_transport(self):
        call = self.root / 'call_01'
        call.mkdir()
        (call / 'request.json').write_text(json.dumps({'model': 'fixture', 'messages': []}))
        ledger, client = self.client()
        with self.assertRaises(ProviderInterruption):
            with ledger.scope(self.root):
                client.chat.completions.create(model='fixture', messages=[])
        self.assertEqual(self.network, [])


if __name__ == '__main__':
    unittest.main()
