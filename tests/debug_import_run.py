import os
import sys
import sqlite3
# Ensure project root is on sys.path so `importers` (in repo root) can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import importers

class FakePD:
    def __init__(self, rows, columns):
        self._rows = rows
        self.columns = columns
    def read_csv(self, path):
        class FakeDF(list):
            def __init__(self, rows, cols):
                super().__init__(rows)
                self.columns = cols
            def iterrows(self):
                for i, r in enumerate(self):
                    yield i, r
            def __len__(self):
                return list.__len__(self)
            @property
            def iloc(self):
                class Iloc:
                    def __init__(self, parent):
                        self.parent = parent
                    def __getitem__(self, idx):
                        row = self.parent[idx]
                        class RowLike:
                            def __init__(self, values):
                                self.values = values
                        return RowLike(list(row.values()))
                return Iloc(self)
        return FakeDF(self._rows, self.columns)
    @staticmethod
    def notna(v):
        return v is not None and v != ""
    @staticmethod
    def isna(v):
        return not FakePD.notna(v)

rows=[{
    'Substation Name':'S1','Element Type':'Διακόπτης ΜΤ','Name':'Breaker1','Serial Number':'SN1','Gate':'G1','Operating Status':'Ενεργή','Model Name':'M200','Model Manufacturer':'Acme'
}]
cols=['Substation Name','Element Type','Name','Serial Number','Gate','Operating Status','Model Name','Model Manufacturer']

fake_pd=FakePD(rows,cols)
import sys
sys.modules['pandas']=fake_pd
importers.pd=fake_pd

conn=sqlite3.connect(':memory:')
cur=conn.cursor()
cur.execute('CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
cur.execute('CREATE TABLE element_models (id INTEGER PRIMARY KEY, element_category TEXT, model_name TEXT, manufacturer TEXT)')
cur.execute('CREATE TABLE elements (id INTEGER PRIMARY KEY, substation_id INTEGER, element_type TEXT, name TEXT, serial_number TEXT, maintenance_date TEXT, voltage_level TEXT, manufacturer TEXT, gate TEXT, is_main_switch INTEGER, breaker_category TEXT, element_model_id INTEGER, operating_status TEXT)')
cur.execute('INSERT INTO substations (id, name) VALUES (?,?)',(1,'S1'))
cur.execute("INSERT INTO element_models (element_category, model_name, manufacturer) VALUES (?,?,?)",('Διακόπτης ΜΤ','M200','Acme'))
conn.commit()

res={}
def on_success(m):
    print('SUCCESS:', m)
    res['ok']=m

def on_error(m):
    print('ERROR:', m)
    res['err']=m

importers.import_elements_from_csv(conn,'dummy.csv',on_success,on_error)
print('RESULTS', res)
cur.execute('SELECT * FROM element_models')
print('MODELS', cur.fetchall())
cur.execute('SELECT * FROM elements')
print('ELEMENTS', cur.fetchall())
