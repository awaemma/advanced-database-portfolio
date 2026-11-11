// Veracore MFB: schema validation and index tests on the MongoDB collections
const v = db.getSiblingDB('veracore');

function expectError(label, fn) {
  try {
    fn();
    print('FAIL (accepted): ' + label);
  } catch (e) {
    print('PASS (rejected): ' + label + ' -> code ' + e.code + ' ' + e.codeName);
  }
}

const sample = v.customers.findOne();

expectError('customer with kyc_tier 5', () => {
  const d = Object.assign({}, sample, { _id: 900001, phone: '08000000001', accounts: [] });
  d.kyc_tier = 5;
  v.customers.insertOne(d);
});

expectError('customer with an 11-digit account number', () => {
  const d = Object.assign({}, sample, { _id: 900002, phone: '08000000002' });
  d.accounts = [{ account_number: '12345678901', account_type: 'wallet', status: 'active', opened_on: new Date() }];
  v.customers.insertOne(d);
});

expectError('customer with a duplicate phone number', () => {
  const d = Object.assign({}, sample, { _id: 900003, accounts: [] });
  v.customers.insertOne(d);
});

expectError('transfer with a 29-digit session ID', () => {
  v.transfers.insertOne({
    _id: '12345678901234567890123456789', transfer_type: 'intrabank',
    sender_account: '1111111111', destination_account: '2222222222',
    amount: NumberDecimal('100.00'), status: 'success', created_at: new Date(), ledger_entries: []
  });
});

expectError('transfer with amount 0', () => {
  v.transfers.insertOne({
    _id: '999000000000000000000000000001', transfer_type: 'intrabank',
    sender_account: '1111111111', destination_account: '2222222222',
    amount: NumberDecimal('0.00'), status: 'success', created_at: new Date(), ledger_entries: []
  });
});

expectError('transfer with ledger direction sideways', () => {
  v.transfers.insertOne({
    _id: '999000000000000000000000000002', transfer_type: 'intrabank',
    sender_account: '1111111111', destination_account: '2222222222',
    amount: NumberDecimal('100.00'), status: 'success', created_at: new Date(),
    ledger_entries: [{ account_number: '1111111111', direction: 'sideways', amount: NumberDecimal('100.00'), posted_at: new Date() }]
  });
});

expectError('audit event without severity', () => {
  v.audit_events.insertOne({ event_type: 'login_failed', occurred_at: new Date() });
});

print('Counts after the tests (unchanged if every insert was rejected):');
['customers', 'transfers', 'audit_events'].forEach(n => print('  ' + n + ' ' + v.getCollection(n).countDocuments({})));
