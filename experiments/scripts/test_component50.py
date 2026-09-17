import unittest
from types import SimpleNamespace
from component50 import covered, NoDirectLookup, parse_plan

class ComponentTests(unittest.TestCase):
    def test_label_and_role_distinction(self):
        self.assertTrue(covered('R',[{'lib_id':'Device:R'}]))
        self.assertFalse(covered('OPA1622',[{'lib_id':'LM2904'}]))
        self.assertTrue(covered('@opamp',[{'lib_id':'LM2904'}]))
        self.assertTrue(covered('@npn',[{'lib_id':'Transistor_BJT:Q_NPN_BEC'}]))
        self.assertFalse(covered('@npn',[{'lib_id':'Q_PNP_BEC'}]))
        self.assertFalse(covered('@resistor',[{'lib_id':'RANDOM_IC'}]))
    def test_disables_lookup_but_preserves_vector_query(self):
        collection=SimpleNamespace(get=lambda **k: {'ids':['x']}, query=lambda **k: 'vector')
        proxy=NoDirectLookup(collection)
        self.assertEqual(proxy.get(where={'lib_id':'LM2904'})['ids'],[])
        self.assertEqual(proxy.query(query_embeddings=[[0]]),'vector')
    def test_invalid_bom_is_not_format_success(self):
        planner=SimpleNamespace(_clean_and_repair_json=lambda x:x)
        for value in ('{}','{"components":[]}','{"components":[{}]}','not json'):
            self.assertIsNone(parse_plan(planner,value))
        self.assertIsNotNone(parse_plan(planner,'{"components":[{"search_query":"Resistor"}]}'))

if __name__=='__main__':unittest.main()
