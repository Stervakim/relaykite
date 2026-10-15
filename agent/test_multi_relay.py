"""One phone executor, distinct authenticated relay receipts, shared memory."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock
import configure
import phone_agent as agent


class MultiRelayTests(unittest.TestCase):
    def config(self, **values):
        return {'relay_url':'https://first.example','agent_token':'a'*48,**values}

    def test_explicit_secondary_connection_is_validated_and_duplicates_rejected(self):
        value=configure.validate(self.config(additional_relays=[{'relay_url':'https://second.example','agent_token':'b'*48}]))
        self.assertEqual(len(value['additional_relays']),1)
        for extra in ([{'relay_url':'http://unsafe.example','agent_token':'b'*48}],
                      [{'relay_url':'https://first.example/','agent_token':'b'*48}],
                      [{'relay_url':'https://second.example','agent_token':'b'*48,'state_dir':'/other'}],
                      [self.config()]*4):
            with self.subTest(extra=extra),self.assertRaises(ValueError):configure.validate(self.config(additional_relays=extra))

    def test_same_remote_id_cannot_leak_results_or_block_other_account(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=agent.Journal(Path(directory))
            first=agent.RelayJournal(journal,'https://first.example',primary=True)
            second=agent.RelayJournal(journal,'https://second.example')
            job={'id':'same-job','tool':'root_shell','arguments':{'command':'id'},'expires_at':time.time()+120}
            calls=[]
            for scoped,label in ((first,'first'),(second,'second')):
                executor=lambda *args: calls.append(label) or {'content':[{'type':'text','text':label}],'isError':False}
                agent.execute_job(job,scoped,executor)
                agent.execute_job(job,scoped,executor)
            self.assertEqual(calls,['first','second'])
            self.assertEqual(first.pending()[0][1]['content'][0]['text'],'first')
            self.assertEqual(second.pending()[0][1]['content'][0]['text'],'second')
            self.assertIsNone(first.get(second.ident('same-job')),'An internal ID must never be accepted as a legacy primary receipt')
            first.delivered('same-job')
            self.assertEqual(first.pending(),[]);self.assertEqual(len(second.pending()),1)
            journal.db.close()

    def test_legacy_pending_result_only_goes_to_original_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=agent.Journal(Path(directory))
            journal.start('old-job',time.time()+120,'fingerprint')
            journal.finish('old-job',{'content':[]})
            first=agent.RelayJournal(journal,'https://first.example',primary=True)
            second=agent.RelayJournal(journal,'https://second.example')
            self.assertEqual([r[0] for r in first.pending()],['old-job']);self.assertEqual(second.pending(),[])
            journal.db.close()

    def test_crashed_secondary_job_keeps_uncertainty_and_origin_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=agent.Journal(Path(directory))
            scoped=agent.RelayJournal(journal,'https://second.example');scoped.start('effect',time.time()+120,'fingerprint')
            journal.db.close();journal=agent.Journal(Path(directory))
            first=agent.RelayJournal(journal,'https://first.example',primary=True)
            second=agent.RelayJournal(journal,'https://second.example')
            self.assertEqual(first.pending(),[])
            self.assertEqual(second.pending()[0][0],'effect');self.assertEqual(second.pending()[0][2],'uncertain')
            journal.db.close()

    def test_primary_url_change_cannot_take_legacy_results_or_acknowledge_them(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);journal=agent.Journal(path)
            try:
                first=agent.RelayJournal(journal,'https://first.example/',primary=True)
                journal.start('legacy-effect',time.time()+120,'fingerprint')
                journal.finish('legacy-effect',{'content':[{'type':'text','text':'private old output'}]})
            finally:journal.db.close()
            journal=agent.Journal(path)
            try:
                replacement=agent.RelayJournal(journal,'https://replacement.example',primary=True)
                original=agent.RelayJournal(journal,'https://first.example')
                self.assertEqual(replacement.pending(),[])
                self.assertIsNone(replacement.get('legacy-effect'))
                with self.assertRaises(ValueError):replacement.delivered('legacy-effect')
                self.assertEqual([row[0] for row in original.pending()],['legacy-effect'])
                original.delivered('legacy-effect')
                self.assertEqual(original.pending(),[])
            finally:journal.db.close()


if __name__=='__main__':unittest.main()
