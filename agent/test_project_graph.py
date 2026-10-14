import unittest, tempfile, json, sys, hashlib
from pathlib import Path
runtime=Path(__file__).with_name('graph-runtime.zip')
if runtime.exists():sys.path.insert(0,str(runtime))
import networkx as nx
from networkx.readwrite import json_graph
from graphify.serve import _query_graph_text, _read_graph
sys.path.insert(0,str(Path(__file__).parent))
from project_graph import ProjectGraph
from unittest.mock import patch

class GraphTests(unittest.TestCase):
 def test_private_source_mirror_is_checked_after_mode_path_remapping(self):
  with tempfile.TemporaryDirectory() as d:
   g,_=self.fixture(d);p=Path(d);mirror=p/'project-source/codaki/portable/engine.py';mirror.parent.mkdir(parents=True);mirror.write_text('owned source')
   m=json.loads((p/'manifest.json').read_text());m['sources']={'@base/project-source/codaki/portable/engine.py':hashlib.sha256(mirror.read_bytes()).hexdigest()};(p/'manifest.json').write_text(json.dumps(m))
   with patch('project_graph.BASE',p):
    self.assertFalse(g.query('entry')['stale'])
    mirror.write_text('new source');self.assertTrue(g.query('entry')['stale'])
 def fixture(self,d):
  p=Path(d);G=nx.DiGraph()
  G.add_node('entry',label='entry',type='function',source_file='agent/main.py',source_location='L1')
  G.add_node('save',label='save',type='function',source_file='agent/memory.py',source_location='L2')
  G.add_edge('entry','save',relation='calls',confidence='EXTRACTED')
  data=json_graph.node_link_data(G,edges='links');data['graph'].update(schema_version=1,graphify_version='0.9.88')
  raw=json.dumps(data).encode();(p/'graph.json').write_bytes(raw)
  (p/'manifest.json').write_text(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'graphify_version':'0.9.88','created_at':'2026-10-13','revision':'test','sources':{}}))
  return ProjectGraph(p),G
 def test_query_matches_original_graphify(self):
  with tempfile.TemporaryDirectory() as d:
   g,G=self.fixture(d);r=g.query('entry')
   self.assertEqual(r['engine'],'graphify-original')
   self.assertEqual(r['text'],_query_graph_text(_read_graph(str(Path(d)/'graph.json')),'entry',depth=2,token_budget=900))
   self.assertFalse(r['stale'])
 def test_node_and_directed_path(self):
  with tempfile.TemporaryDirectory() as d:
   g,_=self.fixture(d);self.assertIn('save',g.node('entry')['text']);self.assertIn('save',g.path('entry','save')['text'])
   with self.assertRaises(ValueError):g.node('does-not-exist')
 def test_corrupt_and_modified_graph_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   g,_=self.fixture(d);(Path(d)/'graph.json').write_text('{}')
   with self.assertRaises(ValueError):g.query('entry')
 def test_staleness_and_utf8_budget(self):
  with tempfile.TemporaryDirectory() as d:
   g,_=self.fixture(d);p=Path(d);m=json.loads((p/'manifest.json').read_text());m['sources']={str(p/'missing.py'):'abcd'};(p/'manifest.json').write_text(json.dumps(m))
   r=g.query('entry');self.assertTrue(r['stale']);self.assertLessEqual(len(json.dumps(r,ensure_ascii=False).encode()),6144)

if __name__=='__main__':unittest.main()
