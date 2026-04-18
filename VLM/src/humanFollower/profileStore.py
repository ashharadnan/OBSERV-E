from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional


class ProfileStore:
    def __init__(self, dbPath: str) -> None:
        self.dbPath = dbPath
        Path(self.dbPath).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.dbPath)
        self.connection.row_factory = sqlite3.Row
        self._ensureTables()

    def _ensureTables(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            '''
            create table if not exists users (
                id integer primary key autoincrement,
                name text not null,
                alertVerbosity text default 'medium',
                emergencyEnabled integer default 0,
                emergencyAddress text,
                safeWord text default 'i am okay',
                cancelWord text default 'cancel'
            )
            '''
        )
        cursor.execute(
            '''
            create table if not exists contacts (
                id integer primary key autoincrement,
                userId integer,
                name text not null,
                phone text,
                relation text,
                priorityOrder integer default 1,
                allowSms integer default 1,
                allowCall integer default 1
            )
            '''
        )
        cursor.execute(
            '''
            create table if not exists events (
                id integer primary key autoincrement,
                timestamp real not null,
                eventType text not null,
                riskScore real,
                summary text,
                location text,
                acknowledged integer default 0,
                payloadJson text
            )
            '''
        )
        self.connection.commit()

    def ensureDefaultUser(self, name: str = 'User', emergencyEnabled: bool = False) -> int:
        cursor = self.connection.cursor()
        row = cursor.execute('select id from users order by id asc limit 1').fetchone()
        if row is not None:
            return int(row['id'])
        cursor.execute(
            'insert into users (name, emergencyEnabled) values (?, ?)',
            (name, 1 if emergencyEnabled else 0),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def addContact(
        self,
        userId: int,
        name: str,
        phone: str,
        relation: str = 'trusted_contact',
        priorityOrder: int = 1,
        allowSms: bool = True,
        allowCall: bool = True,
    ) -> None:
        self.connection.execute(
            '''
            insert into contacts (userId, name, phone, relation, priorityOrder, allowSms, allowCall)
            values (?, ?, ?, ?, ?, ?, ?)
            ''',
            (userId, name, phone, relation, int(priorityOrder), 1 if allowSms else 0, 1 if allowCall else 0),
        )
        self.connection.commit()

    def getContacts(self, userId: Optional[int] = None) -> List[Dict]:
        if userId is None:
            rows = self.connection.execute('select * from contacts order by priorityOrder asc, id asc').fetchall()
        else:
            rows = self.connection.execute(
                'select * from contacts where userId = ? order by priorityOrder asc, id asc',
                (int(userId),),
            ).fetchall()
        return [dict(row) for row in rows]

    def logEvent(self, timestamp: float, eventType: str, riskScore: float, summary: str, payload: Dict, location: str = '') -> None:
        self.connection.execute(
            '''
            insert into events (timestamp, eventType, riskScore, summary, location, payloadJson)
            values (?, ?, ?, ?, ?, ?)
            ''',
            (float(timestamp), eventType, float(riskScore), summary, location, json.dumps(payload)),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
