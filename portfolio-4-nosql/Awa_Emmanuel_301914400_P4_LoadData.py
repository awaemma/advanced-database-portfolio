"""Copy the Veracore data from PostgreSQL into the MongoDB collections.

Reads PostgreSQL (database veracore on localhost) and writes to MongoDB
(database veracore on localhost:27017). The PostgreSQL password is read
from the PGPASSWORD environment variable.
"""
import json
import os
from datetime import datetime, time, timezone
from decimal import Decimal

import psycopg2
import psycopg2.extras
from bson.decimal128 import Decimal128
from pymongo import MongoClient


def as_date(d):
    return None if d is None else datetime.combine(d, time.min, tzinfo=timezone.utc)


def dec(x):
    return Decimal128(Decimal(x))


pg = psycopg2.connect(host='localhost', dbname='veracore', user='postgres',
                      password=os.environ['PGPASSWORD'])
cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
mongo = MongoClient('mongodb://localhost:27017')['veracore']

for name in ('customers', 'transfers', 'audit_events'):
    mongo[name].delete_many({})

# customers with their accounts embedded
cur.execute('SELECT * FROM account ORDER BY account_id')
accounts = {}
for a in cur.fetchall():
    accounts.setdefault(a['customer_id'], []).append({
        'account_number': a['account_number'],
        'account_type': a['account_type'],
        'status': a['status'],
        'opened_on': as_date(a['opened_on']),
        'closed_on': as_date(a['closed_on']),
    })

cur.execute('SELECT * FROM customer ORDER BY customer_id')
customers = []
for c in cur.fetchall():
    customers.append({
        '_id': c['customer_id'],
        'title': c['title'],
        'first_name': c['first_name'],
        'last_name': c['last_name'],
        'date_of_birth': as_date(c['date_of_birth']),
        'gender': c['gender'],
        'phone': c['phone'],
        'email': c['email'],
        'bvn': c['bvn'],
        'kyc_tier': c['kyc_tier'],
        'registered_on': as_date(c['registered_on']),
        'address': {'street': c['street'], 'city': c['city'], 'lga': c['lga'], 'state': c['state']},
        'accounts': accounts.get(c['customer_id'], []),
    })
mongo.customers.insert_many(customers)

# ledger entries grouped by transfer
cur.execute('SELECT * FROM ledger_entry ORDER BY entry_id')
entries = {}
for e in cur.fetchall():
    for kind, col in (('intrabank', 'intrabank_transfer_id'),
                      ('outward', 'outward_transfer_id'),
                      ('inward', 'inward_transfer_id')):
        if e[col] is not None:
            entries.setdefault((kind, e[col]), []).append({
                'account_number': e['account_number'],
                'direction': e['direction'],
                'amount': dec(e['amount']),
                'posted_at': e['posted_at'],
                'entry_kind': e['entry_kind'],
            })


def base(r, kind, key):
    return {
        '_id': r['session_id'],
        'transfer_type': kind,
        'sender_account': r['sender_account'],
        'destination_account': r['destination_account'],
        'amount': dec(r['amount']),
        'narration': r['narration'],
        'status': r['status'],
        'created_at': r['created_at'],
        'posted_at': r['posted_at'],
        'response_message': r['response_message'],
        'reversed_at': r['reversed_at'],
        'reversal_reason': r['reversal_reason'],
        'ledger_entries': entries.get((kind, r[key]), []),
    }


transfers = []

cur.execute('SELECT t.*, c.channel_code FROM intrabank_transfer t JOIN channel c USING (channel_id)')
for r in cur.fetchall():
    d = base(r, 'intrabank', 'intrabank_transfer_id')
    d['channel_code'] = r['channel_code']
    transfers.append(d)

cur.execute('SELECT t.*, c.channel_code, i.institution_code, i.institution_name '
            'FROM outward_transfer t JOIN channel c USING (channel_id) '
            'JOIN external_institution i USING (institution_id)')
for r in cur.fetchall():
    d = base(r, 'outward', 'outward_transfer_id')
    d['channel_code'] = r['channel_code']
    d['beneficiary_name'] = r['beneficiary_name']
    d['institution'] = {'code': r['institution_code'], 'name': r['institution_name']}
    transfers.append(d)

cur.execute('SELECT t.*, i.institution_code, i.institution_name '
            'FROM inward_transfer t JOIN external_institution i USING (institution_id)')
for r in cur.fetchall():
    d = base(r, 'inward', 'inward_transfer_id')
    d['channel_code'] = None
    d['sender_name'] = r['sender_name']
    d['institution'] = {'code': r['institution_code'], 'name': r['institution_name']}
    transfers.append(d)

for i in range(0, len(transfers), 5000):
    mongo.transfers.insert_many(transfers[i:i + 5000])

# audit events: details is stored as an object when it holds JSON, otherwise as text
cur.execute('SELECT * FROM audit_event ORDER BY event_id')
events = []
for e in cur.fetchall():
    details = e['details']
    if isinstance(details, str):
        try:
            parsed = json.loads(details)
            if isinstance(parsed, dict):
                details = parsed
        except ValueError:
            pass
    events.append({
        'customer_id': e['customer_id'],
        'event_type': e['event_type'],
        'severity': e['severity'],
        'occurred_at': e['occurred_at'],
        'ip_address': None if e['ip_address'] is None else str(e['ip_address']),
        'details': details,
    })
mongo.audit_events.insert_many(events)

for name in ('customers', 'transfers', 'audit_events'):
    print(name, mongo[name].count_documents({}))
