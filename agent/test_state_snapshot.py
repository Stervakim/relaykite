import os,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
from state_snapshot import copy_store

class StateSnapshotTests(unittest.TestCase):
    def test_wal_database_and_blob_copy_preserve_committed_notes_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();(source/'blob.json').write_text('immutable owned note')
            db=sqlite3.connect(source/'notes.sqlite3');db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE notes(id TEXT,version INTEGER)');db.execute("INSERT INTO notes VALUES('same-owner-note',3)");db.commit()
            try:
                result=copy_store(source,Path(tmp)/'snapshot')
                with closing(sqlite3.connect(Path(tmp)/'snapshot/notes.sqlite3')) as snapshot:self.assertEqual(snapshot.execute('SELECT * FROM notes').fetchall(),[('same-owner-note',3)])
                self.assertEqual((Path(tmp)/'snapshot/blob.json').read_bytes(),(source/'blob.json').read_bytes())
                self.assertEqual(result['databases'],1);self.assertNotIn('notes.sqlite3-wal',result['files'])
                self.assertEqual(db.execute('SELECT version FROM notes').fetchone()[0],3)
            finally:db.close()
    def test_existing_destination_and_insufficient_capacity_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();(source/'blob').write_bytes(b'owned')
            dest=Path(tmp)/'existing';dest.mkdir();(dest/'keep').write_text('keep')
            with self.assertRaises(ValueError):copy_store(source,dest)
            self.assertEqual((dest/'keep').read_text(),'keep')
            with self.assertRaises(ValueError):copy_store(source,Path(tmp)/'small',max_bytes=1)
            self.assertFalse((Path(tmp)/'small').exists())

if __name__=='__main__':unittest.main()
