import sqlite3
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据/智能助手/backend"))
import qa_response_projection as projection

@pytest.fixture
def conn():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute("CREATE TABLE qa_conversations(id TEXT,owner_subject TEXT)")
    database.execute("CREATE TABLE qa_messages(id INTEGER,conversation_id TEXT,role TEXT,content TEXT,created_at TEXT,snapshot_id INTEGER,hidden_context_json TEXT)")
    database.executemany("INSERT INTO qa_conversations VALUES(?,?)", [("room-a","a"),("room-b","b")])
    database.executemany("INSERT INTO qa_messages VALUES(?,?,?,?,?,?,?)", [(1,"room-a","user","older","t",None,"private"),(2,"room-a","user","current","t",None,"private"),(3,"room-a","assistant","answer","t",None,"private"),(4,"room-b","assistant","other owner","t",None,"private"),(5,"room-a","assistant","concurrent other turn","t",None,"private")])
    yield database
    database.close()

def test_projection_uses_exact_turn_not_latest_shared_message(conn):
    rows = projection.load_turn_messages(conn, {"owner_subject":"a","conversation_id":"room-a","user_message_id":2},3)
    assert [row["id"] for row in rows] == [2,3]
    assert set(rows[0]) == set(projection.PUBLIC_FIELDS)
    assert "private" not in str(rows)

@pytest.mark.parametrize("owner,room,user,assistant", [("b","room-a",2,3),("a","room-a",2,4),("a","room-b",2,4),("a","room-a",1,2),("","room-a",2,3)])
def test_wrong_owner_cross_room_or_wrong_role_fails_closed(conn,owner,room,user,assistant):
    with pytest.raises(PermissionError):
        projection.load_turn_messages(conn, {"owner_subject":owner,"conversation_id":room,"user_message_id":user},assistant)
