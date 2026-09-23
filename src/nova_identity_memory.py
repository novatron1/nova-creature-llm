"""Explicit, owner-scoped user and assistant display names.

Assistant names are per-owner aliases; renaming never changes Nova's underlying
personality, permissions, or system identity. Only anchored direct commands write.
"""
from pathlib import Path
from contextlib import closing
import os
import re
import sqlite3

_NAME = r"([^\W\d_][\w'’\-]*(?: [^\W\d_][\w'’\-]*){0,4})"


class IdentityMemory:
    def __init__(self, database):
        self.path = Path(database)

    def respond(self, text, owner_id, *, read_allowed=True, write_allowed=True):
        value = str(text).strip().rstrip('.!?').strip()
        user = re.fullmatch(r'(?:my name is|call me) ' + _NAME + r'(?:\s*;\s*your name is ' + _NAME + r')?', value, re.I)
        rename = re.fullmatch(r'(?:please )?(?:rename yourself to|change your name to) ' + _NAME, value, re.I)
        assertion = re.fullmatch(r'your name is ' + _NAME, value, re.I)
        query = value.lower().replace("what's", 'what is')
        user_query = query in ('what is my name', 'who am i', 'do you know my name')
        assistant_query = query in ('what is your name', 'tell me your name')
        if not (user or rename or assertion or user_query or assistant_query):
            return None
        if (user or rename) and not write_allowed:
            return 'Identity memory updates are disabled for this turn.'
        if not read_allowed and not (user or rename):
            return 'Identity memory access is disabled for this turn.'
        if not str(owner_id).strip():
            raise ValueError('Identity memory requires an owner')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS identity_names (owner_id TEXT NOT NULL, subject TEXT NOT NULL CHECK(subject IN (\'user\', \'assistant\')), name TEXT NOT NULL, PRIMARY KEY(owner_id, subject))')
            if user or rename:
                subject, name = ('user', user.group(1)) if user else ('assistant', rename.group(1))
                db.execute('INSERT INTO identity_names VALUES (?, ?, ?) ON CONFLICT(owner_id, subject) DO UPDATE SET name=excluded.name', (owner_id, subject, name))
            names = dict(db.execute('SELECT subject, name FROM identity_names WHERE owner_id=?', (owner_id,))) if read_allowed else {}
        assistant = names.get('assistant', 'Nova')
        if user:
            response = f'Nice to meet you, {user.group(1)}.'
            if user.group(2) and read_allowed:
                response += f' My name is {assistant}.'
            return response
        if rename:
            return f'You can call me {rename.group(1)}.'
        if user_query:
            return f"Your name is {names['user']}." if 'user' in names else "I don't have your name saved yet."
        response = f'My name is {assistant}.'
        if assertion:
            response += ' To change it, explicitly ask me to rename myself.'
        return response


def identity_response(text, owner_id, **permissions):
    root = Path(__file__).resolve().parents[1]
    path = Path(os.environ.get('NOVA_IDENTITY_DATABASE', str(root / 'data' / 'nova_identity.db')))
    return IdentityMemory(path).respond(text, owner_id, **permissions)
