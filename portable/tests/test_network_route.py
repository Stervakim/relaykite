import json,os,tempfile,time,unittest
from pathlib import Path
from portable.network_route import choose_proxy

class ShadowRouteTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'status.json';self.proxy='http://127.0.0.1:17890'
    def tearDown(self):self.temp.cleanup()
    def write(self,**values):self.path.write_text(json.dumps(values))
    def choose(self,proxy=None):return choose_proxy(self.proxy if proxy is None else proxy,status_path=self.path,require_root=False)
    def test_fresh_standby_with_android_vpn_uses_system_route(self):
        self.write(mode='standby',any_android_vpn=True);self.assertEqual(self.choose(),'')
    def test_shadow_fallback_remains_on_owned_proxy(self):
        self.write(mode='fallback',any_android_vpn=False);self.assertEqual(self.choose(),self.proxy)
    def test_standby_without_vpn_does_not_disable_the_proxy(self):
        self.write(mode='standby',any_android_vpn=False);self.assertEqual(self.choose(),self.proxy)
    def test_another_configured_proxy_and_blank_config_are_preserved(self):
        self.write(mode='standby',any_android_vpn=True)
        for proxy in ('','http://127.0.0.1:7890'):self.assertEqual(self.choose(proxy),proxy)
    def test_stale_corrupt_future_and_writable_status_cannot_change_route(self):
        self.path.write_text('bad');self.assertEqual(self.choose(),self.proxy)
        for timestamp in (time.time()-120,time.time()+120):
            self.write(mode='standby',any_android_vpn=True);os.utime(self.path,(timestamp,timestamp));self.assertEqual(self.choose(),self.proxy)
        self.write(mode='standby',any_android_vpn=True)
        os.chmod(self.path,0o666)
        self.assertEqual(choose_proxy(self.proxy,status_path=self.path,require_root=True),self.proxy)
