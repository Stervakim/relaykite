import json, unittest
from pathlib import Path

class SchemaTests(unittest.TestCase):
 def test_new_tools_are_read_only_and_memory_fields_optional(self):
  defs=json.loads(Path(__file__).with_name('tool-definitions.json').read_text(encoding='utf-8'))
  tools={d['name']:d for d in defs}
  for name in ['project_graph_query','project_graph_node','project_graph_path','phone_memory_read','phone_memory_health']:
   self.assertTrue(tools[name]['annotations']['readOnlyHint'])
   self.assertFalse(tools[name]['annotations']['destructiveHint'])
  save=tools['phone_memory_save']['inputSchema'];self.assertIn('memory',save['properties']);self.assertNotIn('memory',save.get('required',[]))
  search=tools['phone_memory_search']['inputSchema'];self.assertIn('filters',search['properties']);self.assertNotIn('filters',search.get('required',[]))

if __name__=='__main__':unittest.main()
