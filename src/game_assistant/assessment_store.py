"""Personal model/configuration persistence isolated by authorized scope."""
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
from .assessment import AssessmentModel, Configuration
from .accounts.models import AccountScope


class AssessmentStore:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.lock=threading.RLock()
        self.db.execute('CREATE TABLE IF NOT EXISTS personal_assessment (user_id TEXT, account_id TEXT, role_id TEXT, game TEXT, character TEXT, kind TEXT, id TEXT, payload TEXT, revision INTEGER, updated_at TEXT, PRIMARY KEY(user_id,account_id,role_id,game,character,kind,id))')
        self.db.commit()

    def close(self): self.db.close()

    def _key(self,scope,game,character,kind):
        if not isinstance(scope,AccountScope) or not all((scope.user_id,scope.account_id,scope.role_id)): raise ValueError('authorized scope required')
        return (scope.user_id,scope.account_id,scope.role_id,game,character,kind)

    def read(self,scope,game,character,kind):
        key=self._key(scope,game,character,kind)
        with self.lock:
            rows=self.db.execute('SELECT id,payload,revision,updated_at FROM personal_assessment WHERE user_id=? AND account_id=? AND role_id=? AND game=? AND character=? AND kind=? ORDER BY updated_at,id',key).fetchall()
        return [dict(id=r[0],data=json.loads(r[1]),revision=r[2],updated_at=r[3]) for r in rows]

    def save(self,scope,value,kind,identity=None):
        if kind not in ('model','configuration'): raise ValueError('unknown kind')
        expected=AssessmentModel if kind=='model' else Configuration
        if not isinstance(value,expected): raise ValueError('invalid payload')
        key=self._key(scope,value.game,value.character_id,kind)
        identity='selected' if kind=='model' else identity or uuid.uuid4().hex
        with self.lock,self.db:
            rows=self.read(scope,value.game,value.character_id,kind)
            old=next((r for r in rows if r['id']==identity),None)
            if kind=='configuration' and not old and len(rows)>=64: raise ValueError('configuration limit')
            revision=old['revision']+1 if old else 1
            now=datetime.now(timezone.utc).isoformat()
            self.db.execute('INSERT OR REPLACE INTO personal_assessment VALUES (?,?,?,?,?,?,?,?,?,?)',(*key,identity,value.model_dump_json(),revision,now))
        return dict(id=identity,data=value.model_dump(mode='json'),revision=revision,updated_at=now)

    def delete(self,scope,game,character,identity,kind='configuration'):
        if kind not in ('model','configuration'): raise ValueError('unknown kind')
        with self.lock,self.db:
            cursor=self.db.execute('DELETE FROM personal_assessment WHERE user_id=? AND account_id=? AND role_id=? AND game=? AND character=? AND kind=? AND id=?',(*self._key(scope,game,character,kind),identity))
        return bool(cursor.rowcount)
