// Veracore MFB: MongoDB queries and aggregation pipelines
const v = db.getSiblingDB('veracore');

function stages(p) {
  if (!p) return '';
  const s = [p.stage];
  const kids = p.inputStage ? [p.inputStage] : (p.inputStages || []);
  kids.forEach(k => s.push(stages(k)));
  return s.join(' > ');
}

function planOf(ex) {
  const qp = ex.queryPlanner || (ex.stages && ex.stages[0].$cursor.queryPlanner);
  const es = ex.executionStats || (ex.stages && ex.stages[0].$cursor.executionStats);
  return { plan: stages(qp.winningPlan.queryPlan || qp.winningPlan), stats: es };
}

function report(label, ex) {
  const r = planOf(ex);
  print('  plan: ' + r.plan);
  print('  keys examined: ' + r.stats.totalKeysExamined + ', documents examined: ' + r.stats.totalDocsExamined +
        ', returned: ' + r.stats.nReturned + ', time: ' + r.stats.executionTimeMillis + ' ms');
}

// Q1: customer profile by account number (one document holds the customer and all accounts)
const acct = v.customers.findOne().accounts[0].account_number;
print('Q1: customer profile for account ' + acct);
const q1 = v.customers.findOne({ 'accounts.account_number': acct }, { first_name: 1, last_name: 1, kyc_tier: 1, address: 1, accounts: 1 });
printjson(q1);
report('Q1', v.customers.find({ 'accounts.account_number': acct }).explain('executionStats'));

// Q2: latest 20 transfers for an account, as sender or destination
const acct2 = v.transfers.findOne({ transfer_type: 'intrabank', status: 'success' }).sender_account;
print('\nQ2: latest 20 transfers for account ' + acct2);
const q2 = { $or: [{ sender_account: acct2 }, { destination_account: acct2 }] };
v.transfers.find(q2, { transfer_type: 1, sender_account: 1, destination_account: 1, amount: 1, status: 1, created_at: 1 })
  .sort({ created_at: -1 }).limit(20).forEach(d => print('  ' + d.created_at.toISOString() + ' ' + d.transfer_type + ' ' + d.sender_account + ' -> ' + d.destination_account + ' ' + d.amount + ' ' + d.status));
report('Q2', v.transfers.find(q2).sort({ created_at: -1 }).limit(20).explain('executionStats'));

// Q3: failed transfers by channel and day
print('\nQ3: failed transfers by channel and day (first 10 rows)');
const p3 = [
  { $match: { status: 'failed' } },
  { $group: { _id: { channel: '$channel_code', day: { $dateToString: { format: '%Y-%m-%d', date: '$created_at' } } }, failed: { $sum: 1 } } },
  { $sort: { '_id.day': 1, failed: -1 } },
  { $limit: 10 }
];
v.transfers.aggregate(p3).forEach(d => print('  ' + d._id.day + ' ' + d._id.channel + ' ' + d.failed));
report('Q3', v.transfers.explain('executionStats').aggregate(p3));

// Q4: top 10 accounts by original debit volume, 1 to 10 November 2026
print('\nQ4: top 10 accounts by debit volume, 1 to 10 Nov 2026');
const from = new Date('2026-11-01T00:00:00Z'), to = new Date('2026-11-11T00:00:00Z');
const p4 = [
  { $match: { 'ledger_entries.posted_at': { $gte: from, $lt: to } } },
  { $unwind: '$ledger_entries' },
  { $match: { 'ledger_entries.direction': 'debit', 'ledger_entries.entry_kind': 'original', 'ledger_entries.posted_at': { $gte: from, $lt: to } } },
  { $group: { _id: '$ledger_entries.account_number', debit_total: { $sum: '$ledger_entries.amount' }, entries: { $sum: 1 } } },
  { $sort: { debit_total: -1 } },
  { $limit: 10 }
];
v.transfers.aggregate(p4).forEach(d => print('  ' + d._id + ' ' + d.debit_total + ' (' + d.entries + ' entries)'));
report('Q4', v.transfers.explain('executionStats').aggregate(p4));

// Q5: audit events with different detail shapes in the same collection (demo rows are removed afterwards)
print('\nQ5: audit events with different detail shapes');
v.audit_events.insertMany([
  { event_type: 'device_change', severity: 'medium', occurred_at: new Date(), ip_address: '10.0.0.5', details: { demo: true, device: { os: 'Android', model: 'Tecno Spark' }, trusted: false } },
  { event_type: 'limit_change', severity: 'low', occurred_at: new Date(), ip_address: '10.0.0.6', details: { demo: true, old_limit: 100000, new_limit: 250000, approved_by: 'ops' } }
]);
v.audit_events.find({ 'details.demo': true }, { _id: 0, event_type: 1, details: 1 }).forEach(d => printjson(d));
print('  events where details.device.os is Android: ' + v.audit_events.countDocuments({ 'details.device.os': 'Android' }));
print('  events where details.new_limit is above 200000: ' + v.audit_events.countDocuments({ 'details.new_limit': { $gt: 200000 } }));
const del = v.audit_events.deleteMany({ 'details.demo': true });
print('  demo rows removed: ' + del.deletedCount + ', audit_events now ' + v.audit_events.countDocuments({}));
