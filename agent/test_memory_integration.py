import unittest,sys
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).parent))
import native_phone as n

class IntegrationTests(unittest.TestCase):
 def test_structured_save_uses_original_tencent_bridge(self):
  b=MagicMock(configured=True);b.save.return_value={'saved':True,'engine':'tencentdb-original-external'}
  with patch.object(n,'_memory_bridge',return_value=b):
   r=n.phone_memory_save('test','checked',['x'],memory={'status':'verified','source':'test'})
   self.assertEqual(r['engine'],'tencentdb-original-external');self.assertEqual(b.save.call_args.args[3]['source'],'test')
 def test_structured_failure_never_silently_saves_legacy(self):
  b=MagicMock(configured=True);b.save.side_effect=RuntimeError('offline')
  with patch.object(n,'_memory_bridge',return_value=b),patch.object(n,'_legacy_phone_memory_save') as old:
   with self.assertRaises(RuntimeError):n.phone_memory_save('test','checked',[],memory={'layer':'L2'})
   old.assert_not_called()
 def test_plain_old_call_can_fallback_with_honest_engine(self):
  from memory_bridge import MemoryUnavailable
  b=MagicMock(configured=True);b.save.side_effect=MemoryUnavailable('offline')
  with patch.object(n,'_memory_bridge',return_value=b),patch.object(n,'_legacy_phone_memory_save',return_value={'saved':True}):
   self.assertEqual(n.phone_memory_save('test','checked',[])['engine'],'legacy-fallback')
 def test_rejected_plain_save_must_not_bypass_tencent(self):
  b=MagicMock(configured=True);b.save.side_effect=RuntimeError('memory quota exceeded')
  with patch.object(n,'_memory_bridge',return_value=b),patch.object(n,'_legacy_phone_memory_save') as old:
   with self.assertRaises(RuntimeError):n.phone_memory_save('test','checked',[])
   old.assert_not_called()
 def test_graph_tools_available(self):
  with patch('project_graph.ProjectGraph') as G:
   G.return_value.query.return_value={'engine':'graphify-original'}
   self.assertEqual(n.project_graph_query('memory')['engine'],'graphify-original')
 def test_healthy_search_keeps_outage_writes_visible(self):
  b=MagicMock(configured=True);b.search.return_value={'engine':'tencentdb-original-external','notes':[{'id':'t','title':'fix','content':'old','tags':[],'updated':10,'memory':{'source_id':'legacy:notes:1'}}]}
  with patch.object(n,'_memory_bridge',return_value=b),patch.object(n,'_legacy_phone_memory_search',return_value={'notes':[{'id':1,'title':'fix','content':'new','tags':[],'updated':20,'archived':False}]}):
   r=n.phone_memory_search('fix');self.assertEqual(r['notes'][0]['content'],'new');self.assertEqual(r['notes'][0]['engine'],'legacy')
   self.assertEqual(r['engine'],'tencentdb-original-external+legacy')
 def test_old_legacy_cannot_displace_new_tencent_fix(self):
  b=MagicMock(configured=True);b.search.return_value={'engine':'tencentdb-original-external','notes':[{'id':'t','title':'fix','content':'new verified','tags':[],'updated':100,'memory':{'source_id':'legacy:notes:1','status':'verified'}}]}
  with patch.object(n,'_memory_bridge',return_value=b),patch.object(n,'_legacy_phone_memory_search',return_value={'notes':[{'id':1,'title':'fix','content':'old historical','tags':[],'updated':1,'archived':False}]}):
   self.assertEqual(n.phone_memory_search('fix',limit=1)['notes'][0]['content'],'new verified')
 def test_filtered_search_does_not_invent_scope_for_legacy(self):
  b=MagicMock(configured=True);b.search.return_value={'engine':'tencentdb-original-external','notes':[]}
  with patch.object(n,'_memory_bridge',return_value=b),patch.object(n,'_legacy_phone_memory_search') as old:
   n.phone_memory_search('x',filters={'device':'windows'});old.assert_not_called()

if __name__=='__main__':unittest.main()
