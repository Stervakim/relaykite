import unittest
from pathlib import Path
class MemoryPowerTests(unittest.TestCase):
    def test_stops_at_twenty_and_never_runs_unknown_battery(self):
        source=Path(__file__).with_name('memory_power.py')
        self.assertTrue(source.exists(),'Phone model power policy is missing')
        from memory_power import permitted
        self.assertFalse(permitted({'enabled':True,'battery':20}))
        self.assertFalse(permitted({'enabled':True,'battery':19}))
        self.assertTrue(permitted({'enabled':True,'battery':21}))
        self.assertFalse(permitted({'enabled':True,'battery':-1}))
        self.assertFalse(permitted({'enabled':False,'battery':100}))
        self.assertFalse(permitted({'enabled':True}))
    def test_stale_sdk_power_state_does_not_authorize_background_request(self):
        import tempfile,json,time
        source=Path(__file__).with_name('memory_power.py')
        from memory_power import sdk_state,permitted
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'power.json'
            path.write_text(json.dumps({'enabled':True,'battery':90,'updated':time.time()-180}))
            self.assertFalse(permitted(sdk_state(path)))
            path.write_text(json.dumps({'enabled':True,'battery':21,'updated':time.time()}))
            self.assertTrue(permitted(sdk_state(path)))
