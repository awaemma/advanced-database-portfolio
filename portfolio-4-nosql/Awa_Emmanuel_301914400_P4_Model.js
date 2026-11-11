// Veracore MFB: MongoDB model (database veracore)
// Run with mongosh against the veracore-mongo container.
const v = db.getSiblingDB('veracore');

['customers', 'transfers', 'audit_events'].forEach(n => v.getCollection(n).drop());

// customers: one document per customer, with the address and the accounts embedded
v.createCollection('customers', {
  validator: { $jsonSchema: {
    bsonType: 'object',
    required: ['_id', 'first_name', 'last_name', 'date_of_birth', 'phone', 'kyc_tier', 'registered_on', 'address', 'accounts'],
    properties: {
      _id: { bsonType: ['int', 'long'], description: 'customer_id from the relational database' },
      first_name: { bsonType: 'string' },
      last_name: { bsonType: 'string' },
      date_of_birth: { bsonType: 'date' },
      gender: { enum: ['male', 'female'] },
      phone: { bsonType: 'string' },
      email: { bsonType: ['string', 'null'] },
      bvn: { bsonType: ['string', 'null'], pattern: '^[0-9]{11}$' },
      kyc_tier: { bsonType: ['int', 'long'], minimum: 1, maximum: 3 },
      registered_on: { bsonType: 'date' },
      address: {
        bsonType: 'object',
        required: ['street', 'city', 'lga', 'state'],
        properties: {
          street: { bsonType: 'string' }, city: { bsonType: 'string' },
          lga: { bsonType: 'string' }, state: { bsonType: 'string' }
        }
      },
      accounts: {
        bsonType: 'array',
        items: {
          bsonType: 'object',
          required: ['account_number', 'account_type', 'status', 'opened_on'],
          properties: {
            account_number: { bsonType: 'string', pattern: '^[0-9]{10}$' },
            account_type: { enum: ['wallet', 'savings'] },
            status: { enum: ['active', 'frozen', 'closed'] },
            opened_on: { bsonType: 'date' },
            closed_on: { bsonType: ['date', 'null'] }
          }
        }
      }
    }
  } },
  validationLevel: 'strict',
  validationAction: 'error'
});

// transfers: one document per transfer, with its ledger entries embedded
// _id is the 30-digit session ID, which is unique across all three transfer types
v.createCollection('transfers', {
  validator: { $jsonSchema: {
    bsonType: 'object',
    required: ['_id', 'transfer_type', 'sender_account', 'destination_account', 'amount', 'status', 'created_at', 'ledger_entries'],
    properties: {
      _id: { bsonType: 'string', pattern: '^[0-9]{30}$' },
      transfer_type: { enum: ['intrabank', 'outward', 'inward'] },
      sender_account: { bsonType: 'string', pattern: '^[0-9]{10}$' },
      destination_account: { bsonType: 'string', pattern: '^[0-9]{10}$' },
      channel_code: { bsonType: ['string', 'null'] },
      amount: { bsonType: 'decimal', minimum: NumberDecimal('0.01') },
      narration: { bsonType: ['string', 'null'] },
      status: { enum: ['pending', 'success', 'failed', 'reversed'] },
      created_at: { bsonType: 'date' },
      posted_at: { bsonType: ['date', 'null'] },
      response_message: { bsonType: ['string', 'null'] },
      ledger_entries: {
        bsonType: 'array',
        items: {
          bsonType: 'object',
          required: ['account_number', 'direction', 'amount', 'posted_at'],
          properties: {
            account_number: { bsonType: 'string', pattern: '^[0-9]{10}$' },
            direction: { enum: ['debit', 'credit'] },
            amount: { bsonType: 'decimal' },
            posted_at: { bsonType: 'date' }
          }
        }
      }
    }
  } },
  validationLevel: 'strict',
  validationAction: 'error'
});

// audit_events: the details field is a free-form object that differs by event type
v.createCollection('audit_events', {
  validator: { $jsonSchema: {
    bsonType: 'object',
    required: ['event_type', 'severity', 'occurred_at'],
    properties: {
      customer_id: { bsonType: ['int', 'long', 'null'] },
      event_type: { bsonType: 'string' },
      severity: { bsonType: 'string' },
      occurred_at: { bsonType: 'date' },
      ip_address: { bsonType: ['string', 'null'] },
      details: { bsonType: ['object', 'string', 'null'] }
    }
  } },
  validationLevel: 'strict',
  validationAction: 'error'
});

v.customers.createIndex({ phone: 1 }, { unique: true });
v.customers.createIndex({ 'accounts.account_number': 1 }, { unique: true });
v.transfers.createIndex({ sender_account: 1, created_at: -1 });
v.transfers.createIndex({ destination_account: 1, created_at: -1 });
v.transfers.createIndex({ status: 1, created_at: -1 });
v.audit_events.createIndex({ customer_id: 1, occurred_at: -1 });
v.audit_events.createIndex({ event_type: 1, occurred_at: -1 });

print('Collections:');
v.getCollectionNames().forEach(n => print('  ' + n));
print('Indexes:');
['customers', 'transfers', 'audit_events'].forEach(n =>
  v.getCollection(n).getIndexes().forEach(i => print('  ' + n + '.' + i.name)));
