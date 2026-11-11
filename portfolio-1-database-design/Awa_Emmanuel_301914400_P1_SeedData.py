#!/usr/bin/env python3
"""
Veracore MFB - Portfolio 1 seed data loader
MIT 8103 Advanced Database Systems, MIVA
Author: Emmanuel Awa (301914400)

Loads deterministic synthetic data into an EMPTY veracore database whose schema
was created by Awa_Emmanuel_301914400_P1_Schema.sql. All people, accounts and
transfers are fictional. External institution codes are the 3-digit CBN bank
codes (CBN NUBAN circular, 2010; code 076 was Skye Bank, now Polaris Bank).

Connection settings come only from the standard libpq environment variables:
    PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
No credentials are stored in this file.

Usage:
    python Awa_Emmanuel_301914400_P1_SeedData.py

Design notes
- A fixed random seed makes every run on a fresh database produce identical data.
- Identity ids are assigned by PostgreSQL and read back with RETURNING.
- Transfers and ledger entries reference Veracore accounts by account_number
  (char(10)); counterparty accounts at other banks are plain 10-digit numbers.
- Transfers are simulated in time order (Africa/Lagos, UTC+1, no DST). Each
  account keeps a running balance in kobo. A debit is shrunk to fit the
  available balance, or the transfer is deferred, so no balance ever goes below
  zero. Money credited by a transfer that will later be reversed is held, so
  the reversal debit can always be posted.
- Everything is loaded in one transaction: either the whole seed commits or
  nothing does.
"""

import heapq
import itertools
import math
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
SEED = 8103
rng = random.Random(SEED)

WAT = timezone(timedelta(hours=1))           # Africa/Lagos: UTC+1 all year
REF_DATE = date(2026, 11, 11)                # "today" for ages and closures
TX_START = datetime(2026, 10, 1, 0, 0, 0, tzinfo=WAT)
TX_END = datetime(2026, 11, 10, 23, 59, 59, tzinfo=WAT)   # last allowed timestamp
LAST_CREATE = TX_END - timedelta(seconds=60)              # room for posting delay
TX_DAYS = 41                                 # 2026-10-01 .. 2026-11-10
FUNDING_DAYS = 5                             # initial inward: 2026-10-01 .. 10-05

N_CUSTOMERS = 500
N_INTRABANK = 60_000
N_INWARD = 20_000                            # includes one funding inward per active account
N_OUTWARD = 20_000
N_AUDIT = 2_000

BATCH = 2_000                                # rows per INSERT statement
LEDGER_BATCH = 5_000
MIN_DEBIT_KOBO = 10_000                      # an account needs at least NGN 100 available to be debited
SESSION_PREFIX = "999901"                    # fictional 6-digit Veracore session prefix
SUCCESS_MSG = "Transaction is successful"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
class Weighted:
    """Weighted random choice with precomputed cumulative weights."""

    def __init__(self, pairs):
        self.values = [v for v, _ in pairs]
        self.cum = list(itertools.accumulate(w for _, w in pairs))

    def pick(self):
        return rng.choices(self.values, cum_weights=self.cum)[0]


def rand_date(lo, hi):
    """Uniform random date in [lo, hi]."""
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def digits(n):
    return "".join(rng.choice("0123456789") for _ in range(n))


def kobo_to_naira(k):
    return Decimal(k).scaleb(-2)


def fmt_naira(k):
    return f"NGN {k // 100:,}.{k % 100:02d}"


def add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:                       # 29 February
        return d.replace(year=d.year + years, day=28) + timedelta(days=1)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
CHANNELS = [("MOB", "Mobile app"), ("USSD", "USSD"), ("WEB", "Web banking")]
CHANNEL_WEIGHTS = {"MOB": 60, "USSD": 25, "WEB": 15}

INSTITUTIONS = [  # (CBN code, name, weight for traffic)
    ("044", "Access Bank", 14),
    ("058", "Guaranty Trust Bank", 14),
    ("011", "First Bank of Nigeria", 12),
    ("033", "United Bank for Africa", 12),
    ("057", "Zenith Bank", 12),
    ("221", "Stanbic IBTC Bank", 5),
    ("070", "Fidelity Bank", 6),
    ("214", "First City Monument Bank", 6),
    ("032", "Union Bank", 4),
    ("035", "Wema Bank", 5),
    ("076", "Polaris Bank", 4),
    ("050", "Ecobank Nigeria", 6),
]

NAMES = {  # group: (male first names, female first names, surnames)
    "yoruba": (
        ["Adebayo", "Olumide", "Babatunde", "Femi", "Segun", "Kayode", "Oluwaseun", "Gbenga",
         "Adewale", "Kunle", "Dapo", "Akinwale", "Tunde", "Ayodeji", "Olusegun", "Rotimi", "Lanre"],
        ["Folake", "Funmilayo", "Yetunde", "Adunni", "Bisola", "Titilayo", "Omolara", "Abimbola",
         "Morenike", "Kemi", "Bukola", "Temitope", "Adeola", "Oluwakemi", "Ronke", "Simisola"],
        ["Adeyemi", "Ogunleye", "Balogun", "Olawale", "Akinola", "Adebayo", "Oyelaran", "Fashola",
         "Ogunbiyi", "Adeleke", "Ogundipe", "Afolabi", "Oladipo", "Babalola", "Adesanya", "Ojo",
         "Oyewole", "Alabi"],
    ),
    "igbo": (
        ["Chukwuemeka", "Obinna", "Ikenna", "Chinedu", "Emeka", "Nnamdi", "Chidi", "Ifeanyi",
         "Okechukwu", "Tochukwu", "Uchenna", "Kelechi", "Chibuzor", "Ebuka", "Somto"],
        ["Ngozi", "Chiamaka", "Adaeze", "Nneka", "Chioma", "Ifeoma", "Obiageli", "Amarachi",
         "Uju", "Ebele", "Ogechi", "Nkechi", "Chidinma", "Ifunanya", "Onyinye"],
        ["Okafor", "Okonkwo", "Eze", "Nwosu", "Obi", "Okeke", "Chukwu", "Nwachukwu", "Onyeka",
         "Ibe", "Agu", "Okoro", "Nwankwo", "Ugwu", "Anyanwu", "Ezeh", "Obiora", "Udeh"],
    ),
    "hausa": (
        ["Abubakar", "Musa", "Ibrahim", "Aliyu", "Usman", "Sani", "Bashir", "Yusuf", "Garba",
         "Kabiru", "Nasiru", "Umar", "Mustapha", "Haruna", "Shehu"],
        ["Aisha", "Fatima", "Zainab", "Hauwa", "Amina", "Hadiza", "Halima", "Maryam", "Rukayya",
         "Jamila", "Safiya", "Bilkisu", "Zulaihat", "Asmau", "Khadija"],
        ["Bello", "Abdullahi", "Mohammed", "Danjuma", "Lawal", "Yakubu", "Sule", "Aminu",
         "Abdulkadir", "Shuaibu", "Tanko", "Idris", "Suleiman", "Dauda", "Mahmud", "Gambo", "Musa",
         "Ahmed"],
    ),
    "edo": (
        ["Osaze", "Efosa", "Osagie", "Eghosa", "Uyi", "Ehis"],
        ["Eki", "Ivie", "Osasu", "Itohan", "Omoye", "Esohe"],
        ["Igbinedion", "Omoregie", "Aigbe", "Ehigiator", "Osayande", "Iyamu", "Osagie"],
    ),
    "efik": (
        ["Etim", "Effiong", "Okon", "Edet", "Asuquo", "Udo"],
        ["Ekaette", "Affiong", "Imaobong", "Eno", "Idara", "Mfon"],
        ["Bassey", "Etim", "Effiong", "Okon", "Edet", "Akpan", "Ekpo", "Umoh", "Udoh"],
    ),
    "tiv": (
        ["Terver", "Aondona", "Sesugh", "Tersoo", "Msughter"],
        ["Doosuur", "Mnena", "Ngodoo", "Mwuese", "Seember"],
        ["Iorliam", "Akaa", "Gbenda", "Tarka", "Agber", "Orsar", "Hembe"],
    ),
    "urhobo": (
        ["Ovie", "Tega", "Oghenovo", "Akpo", "Edafe"],
        ["Ufuoma", "Ejiro", "Onome", "Oghenefejiro", "Rukevwe"],
        ["Okpako", "Omovie", "Ejovi", "Efetobor", "Ogaga", "Emuveyan"],
    ),
}
GROUP_W = Weighted([("yoruba", 30), ("igbo", 28), ("hausa", 24), ("edo", 5),
                    ("efik", 5), ("tiv", 4), ("urhobo", 4)])

LOCATIONS = [  # (state, lga, city, weight, streets) - only the agreed state/LGA/city triples
    ("Lagos", "Ikeja", "Ikeja", 14,
     ["Allen Avenue", "Opebi Road", "Obafemi Awolowo Way", "Toyin Street", "Adeniyi Jones Avenue"]),
    ("Lagos", "Eti-Osa", "Lekki", 12,
     ["Admiralty Way", "Fola Osibo Road", "Adeola Odeku Street", "Ajose Adeogun Street", "Kusenla Road"]),
    ("Lagos", "Surulere", "Surulere", 10,
     ["Bode Thomas Street", "Adeniran Ogunsanya Street", "Ojuelegba Road", "Akerele Street", "Randle Avenue"]),
    ("FCT", "Abuja Municipal Area Council", "Abuja", 14,
     ["Aminu Kano Crescent", "Ahmadu Bello Way", "Adetokunbo Ademola Crescent", "Gimbiya Street", "Gana Street"]),
    ("Rivers", "Port Harcourt", "Port Harcourt", 9,
     ["Aba Road", "Ikwerre Road", "Olu Obasanjo Road", "Trans-Amadi Road", "Stadium Road"]),
    ("Oyo", "Ibadan North", "Ibadan", 9,
     ["Oyo Road", "Awolowo Avenue", "Agodi Gate Road", "University Crescent", "Sango-Eleyele Road"]),
    ("Kano", "Kano Municipal", "Kano", 8,
     ["Kofar Mata Road", "Zoo Road", "Ibrahim Taiwo Road", "Gidan Makama Street", "Kofar Nassarawa Road"]),
    ("Enugu", "Enugu North", "Enugu", 8,
     ["Ogui Road", "Okpara Avenue", "Zik Avenue", "Chime Avenue", "Bank Road"]),
    ("Kaduna", "Kaduna North", "Kaduna", 8,
     ["Ali Akilu Road", "Isa Kaita Road", "Constitution Road", "Independence Way", "Ahmadu Bello Way"]),
    ("Anambra", "Onitsha North", "Onitsha", 8,
     ["New Market Road", "Old Market Road", "Awka Road", "Modebe Avenue", "Venn Road"]),
]
LOCATION_W = Weighted([(loc, loc[3]) for loc in LOCATIONS])

PHONE_PREFIX_W = Weighted([("070", 15), ("080", 30), ("081", 25), ("090", 18), ("091", 12)])
KYC_W = Weighted([(1, 50), (2, 35), (3, 15)])
ACCOUNTS_PER_CUSTOMER_W = Weighted([(1, 40), (2, 40), (3, 20)])
ACCOUNT_STATUS_W = Weighted([("active", 90), ("frozen", 7), ("closed", 3)])
TRANSFER_STATUS_W = Weighted([("success", 920), ("failed", 50), ("pending", 5), ("reversed", 25)])
CHANNEL_CODE_W = Weighted(list(CHANNEL_WEIGHTS.items()))
INSTITUTION_W = Weighted([(code, w) for code, _, w in INSTITUTIONS])

HOUR_W = Weighted(list(enumerate(
    [1, 0.6, 0.4, 0.3, 0.4, 0.8, 2, 4, 6, 7, 7, 7, 7, 7, 7, 7, 6.5, 6, 5.5, 5, 4.5, 3.5, 2.5, 1.5])))

FAIL_REASONS = ["Beneficiary bank unavailable", "Invalid beneficiary account",
                "Transaction limit exceeded", "Request timed out"]
REVERSAL_REASONS = ["Duplicate transfer", "Customer dispute", "Wrong beneficiary", "Fraud suspected"]

NARRATION_INTRABANK = ["Rent", "School fees", "Groceries", "Feeding money", "Upkeep", "Salary advance",
                       "Loan repayment", "Ajo contribution", "Thank you", "Transport fare",
                       "Hospital bill", "Birthday gift", "Refund", "Association dues", "Light bill share"]
NARRATION_INWARD = ["Salary", "Salary advance", "Payment for goods", "Refund", "Feeding money",
                    "Allowance", "Business payment", "Contract payment", "Upkeep", "Transfer from self",
                    "Pocket money", "School fees support"]
NARRATION_OUTWARD = ["Rent", "School fees", "Groceries", "Payment for goods", "Supplier payment",
                     "Hospital bill", "Car repairs", "Electricity bill", "Transfer to self",
                     "Market purchase", "Diesel purchase", "House help salary", "Building materials"]
BUSINESS_SUFFIXES = ["Ventures", "Enterprises", "Global Services Ltd", "Stores", "Nigeria Ltd",
                     "Integrated Services", "Provisions"]

AUDIT_TYPE_W = Weighted([("failed_login", 35), ("large_transfer", 15), ("new_device", 20),
                         ("password_change", 15), ("kyc_update", 15)])
SEVERITY_W = {
    "failed_login": Weighted([("low", 20), ("medium", 50), ("high", 30)]),
    "new_device": Weighted([("low", 50), ("medium", 40), ("high", 10)]),
    "password_change": Weighted([("low", 70), ("medium", 30)]),
    "kyc_update": Weighted([("low", 80), ("medium", 20)]),
}
NULL_CUSTOMER_SHARE_OF_FAILED_LOGIN = 0.10 / 0.35   # about 10% of all audit events
LARGE_TRANSFER_KOBO = 50_000_000                    # NGN 500,000
IP_FIRST_OCTETS = [41, 102, 105, 129, 154, 160, 165, 196, 197]
DEVICES = ["Android phone (Tecno)", "Android phone (Infinix)", "Android phone (Samsung)",
           "iPhone", "Windows PC (Chrome)", "MacBook (Safari)", "Feature phone (USSD)"]


# ---------------------------------------------------------------------------
# Random value generators
# ---------------------------------------------------------------------------
def person_name():
    group = GROUP_W.pick()
    males, females, surnames = NAMES[group]
    gender = "male" if rng.random() < 0.52 else "female"
    first = rng.choice(males if gender == "male" else females)
    return gender, first, rng.choice(surnames)


def counterparty_name():
    _, first, last = person_name()
    if rng.random() < 0.15:
        return f"{last} {rng.choice(BUSINESS_SUFFIXES)}"
    return f"{first} {last}"


def draw_amount_kobo():
    """Skewed amount: mostly NGN 500-50,000, some up to 300,000, a few up to 2,000,000."""
    r = rng.random()
    if r < 0.85:
        lo, hi = 500, 50_000
    elif r < 0.98:
        lo, hi = 50_000, 300_000
    else:
        lo, hi = 300_000, 2_000_000
    naira = math.exp(rng.uniform(math.log(lo), math.log(hi)))
    if rng.random() < 0.7:                   # most people send round figures
        step = 50 if naira < 10_000 else 500 if naira < 100_000 else 5_000
        naira = max(step, round(naira / step) * step)
        return int(naira) * 100
    return max(100, int(naira * 100))


def draw_funding_kobo():
    """Opening inward transfer: NGN 20,000 - 1,500,000, rounded to NGN 1,000."""
    naira = math.exp(rng.uniform(math.log(20_000), math.log(1_500_000)))
    return max(1_000, round(naira / 1_000) * 1_000) * 100


def rand_ts(day_lo, day_hi):
    """Timestamp on a random day in [day_lo, day_hi) with a daytime-heavy hour profile."""
    day = TX_START + timedelta(days=rng.randrange(day_lo, day_hi))
    ts = day + timedelta(hours=HOUR_W.pick(), minutes=rng.randrange(60), seconds=rng.randrange(60))
    if ts > LAST_CREATE:
        ts = LAST_CREATE - timedelta(seconds=rng.randint(0, 3600))
    return ts


def random_ip():
    return (f"{rng.choice(IP_FIRST_OCTETS)}.{rng.randint(0, 255)}."
            f"{rng.randint(0, 255)}.{rng.randint(1, 254)}")


# ---------------------------------------------------------------------------
# In-memory model
# ---------------------------------------------------------------------------
class Account:
    __slots__ = ("id", "customer_id", "number", "type", "status", "opened_on", "closed_on",
                 "balance", "held", "funded_at")

    def __init__(self, customer_id, number, acct_type, status, opened_on, closed_on):
        self.id = None
        self.customer_id = customer_id
        self.number = number
        self.type = acct_type
        self.status = status
        self.opened_on = opened_on
        self.closed_on = closed_on
        self.balance = 0          # kobo, posted credits minus posted debits
        self.held = 0             # kobo reserved for a scheduled reversal debit
        self.funded_at = None     # posted_at of the opening inward transfer

    @property
    def available(self):
        return self.balance - self.held


class Transfer:
    __slots__ = ("kind", "status", "created_at", "posted_at", "reversed_at", "amount",
                 "src", "dst", "channel_id", "institution_id", "cp_name", "cp_account",
                 "narration", "response", "reversal_reason", "session_id", "is_funding",
                 "order", "db_id")

    def __init__(self, kind, status, is_funding=False):
        self.kind = kind
        self.status = status
        self.is_funding = is_funding
        self.created_at = self.posted_at = self.reversed_at = None
        self.amount = 0
        self.src = self.dst = None
        self.channel_id = self.institution_id = None
        self.cp_name = self.cp_account = None
        self.narration = self.response = self.reversal_reason = None
        self.session_id = None
        self.order = None
        self.db_id = None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
TABLES = ["channel", "external_institution", "customer", "account", "session_registry",
          "intrabank_transfer", "inward_transfer", "outward_transfer", "ledger_entry", "audit_event"]


def connect():
    missing = [v for v in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER") if not os.environ.get(v)]
    if missing:
        sys.exit(f"Missing environment variable(s): {', '.join(missing)}. "
                 "Set PGHOST, PGPORT, PGDATABASE, PGUSER and PGPASSWORD before running.")
    return psycopg2.connect()               # libpq reads the PG* environment variables


def ensure_empty(cur):
    non_empty = []
    for t in TABLES:
        cur.execute(f"SELECT EXISTS (SELECT 1 FROM {t})")
        if cur.fetchone()[0]:
            non_empty.append(t)
    if non_empty:
        sys.exit("Refusing to seed: these tables already contain rows: " + ", ".join(non_empty)
                 + ". Load into a freshly created database.")


def insert_returning(cur, sql, rows, page_size=BATCH):
    """execute_values with RETURNING; returns all result rows across pages."""
    if not rows:
        return []
    return execute_values(cur, sql, rows, page_size=page_size, fetch=True)


# ---------------------------------------------------------------------------
# Seeding steps
# ---------------------------------------------------------------------------
def seed_reference(cur):
    res = insert_returning(cur, "INSERT INTO channel (channel_code, channel_name) VALUES %s "
                                "RETURNING channel_code, channel_id", CHANNELS)
    channel_ids = dict(res)
    res = insert_returning(cur, "INSERT INTO external_institution (institution_code, institution_name) "
                                "VALUES %s RETURNING institution_code, institution_id",
                           [(code, name) for code, name, _ in INSTITUTIONS])
    institution_ids = dict(res)
    return channel_ids, institution_ids


def build_customers():
    customers = []
    phones, emails, bvns = set(), set(), set()
    oldest = date(1955, 11, 12)              # 70 on 2026-11-11
    youngest = date(2008, 9, 30)             # 18 on 2026-11-11 and 18 before registering
    span = (youngest - oldest).days
    for _ in range(N_CUSTOMERS):
        gender, first, last = person_name()
        if rng.random() < 0.04:
            title = "Dr"
        elif gender == "male":
            title = "Mr"
        else:
            title = Weighted([("Mrs", 50), ("Miss", 25), ("Ms", 21)]).pick()
        dob = youngest - timedelta(days=int(rng.triangular(0, 1, 0.25) * span))
        reg_lo = max(date(2024, 1, 1), add_years(dob, 18))
        registered = rand_date(reg_lo, date(2026, 9, 30))
        while True:
            phone = PHONE_PREFIX_W.pick() + digits(8)
            if phone not in phones:
                phones.add(phone)
                break
        while True:
            email = f"{first}.{last}{rng.randint(1, 999)}@example.com".lower()
            if email not in emails:
                emails.add(email)
                break
        kyc = KYC_W.pick()
        bvn = None
        if not (kyc == 1 and rng.random() < 0.30):
            while True:
                bvn = "22" + digits(9)
                if bvn not in bvns:
                    bvns.add(bvn)
                    break
        state, lga, city, _, streets = LOCATION_W.pick()
        street = f"{rng.randint(1, 150)} {rng.choice(streets)}"
        customers.append({
            "title": title, "first": first, "last": last, "dob": dob, "gender": gender,
            "phone": phone, "email": email, "bvn": bvn, "kyc": kyc, "registered": registered,
            "street": street, "city": city, "lga": lga, "state": state, "id": None,
        })
    customers.sort(key=lambda c: c["registered"])  # ids follow registration order
    return customers


def seed_customers(cur, customers):
    rows = [(c["title"], c["first"], c["last"], c["dob"], c["gender"], c["phone"], c["email"],
             c["bvn"], c["kyc"], c["registered"], c["street"], c["city"], c["lga"], c["state"])
            for c in customers]
    res = insert_returning(cur, """
        INSERT INTO customer (title, first_name, last_name, date_of_birth, gender, phone, email,
                              bvn, kyc_tier, registered_on, street, city, lga, state)
        VALUES %s RETURNING phone, customer_id""", rows)
    ids = dict(res)
    for c in customers:
        c["id"] = ids[c["phone"]]


def build_accounts(customers):
    accounts = []
    numbers = set()
    last_open = date(2026, 9, 30)
    for c in customers:
        n = ACCOUNTS_PER_CUSTOMER_W.pick()
        for j in range(n):
            if j == 0:
                acct_type = "wallet" if rng.random() < 0.75 else "savings"
                opened = c["registered"]
            else:
                acct_type = "savings" if rng.random() < 0.65 else "wallet"
                opened = rand_date(c["registered"], last_open)
            status = ACCOUNT_STATUS_W.pick()
            closed = rand_date(opened + timedelta(days=1), REF_DATE) if status == "closed" else None
            while True:
                number = digits(10)
                if number not in numbers:
                    numbers.add(number)
                    break
            accounts.append(Account(c["id"], number, acct_type, status, opened, closed))
    accounts.sort(key=lambda a: a.opened_on)       # ids follow opening order (stable sort)
    return accounts


def seed_accounts(cur, accounts):
    rows = [(a.customer_id, a.number, a.type, a.status, a.opened_on, a.closed_on) for a in accounts]
    res = insert_returning(cur, """
        INSERT INTO account (customer_id, account_number, account_type, status, opened_on, closed_on)
        VALUES %s RETURNING account_number, account_id""", rows)
    ids = dict(res)
    for a in accounts:
        a.id = ids[a.number]


def simulate(accounts, channel_ids, institution_ids):
    """Generate transfers and ledger entries in time order with running balances."""
    stats = {"deferred": 0, "dropped": {"intrabank": 0, "inward": 0, "outward": 0},
             "shrunk": 0, "reversal_downgraded": 0}
    active = [a for a in accounts if a.status == "active"]
    own_accounts = {}
    for a in active:
        own_accounts.setdefault(a.customer_id, []).append(a)

    funded = []                 # active accounts whose opening inward has posted
    session_ids = set()
    transfers = []
    ledger = []                 # (posted_at, seq, transfer, account_number, direction, kobo, entry_kind)
    heap = []
    seq = itertools.count()
    order = itertools.count()

    def push(ts, kind, tx):
        heapq.heappush(heap, (ts, next(seq), kind, tx))

    def set_times(tx, created):
        """Set created/posted times; return the time the transfer takes effect."""
        tx.created_at = created
        if tx.status in ("success", "reversed"):
            tx.posted_at = created + timedelta(seconds=rng.randint(1, 8))
            return tx.posted_at
        tx.posted_at = None
        return created

    def eligible(a, created):
        return a.funded_at is not None and a.funded_at + timedelta(seconds=10) <= created

    def pick_account(created, needs_funds=False, exclude=None):
        if not funded:
            return None
        for _ in range(40):
            a = rng.choice(funded)
            if a is exclude or not eligible(a, created):
                continue
            if needs_funds and a.available < MIN_DEBIT_KOBO:
                continue
            return a
        return None

    def fit_debit(amount, acct):
        if amount <= acct.available:
            return amount
        stats["shrunk"] += 1
        new = int(acct.available * rng.uniform(0.3, 1.0))
        new -= new % 100                         # whole naira
        return max(100, min(new, acct.available))

    def add_entry(ts, tx, acct, direction, kobo, entry_kind):
        ledger.append((ts, next(seq), tx, acct.number, direction, kobo, entry_kind))
        if direction == "credit":
            acct.balance += kobo
        else:
            acct.balance -= kobo
            if acct.balance < 0:
                raise RuntimeError(f"Internal error: account {acct.number} would go negative")

    def apply(tx):
        """Choose accounts and amount and post ledger effects. False means retry later."""
        posts = tx.status in ("success", "reversed")
        if tx.status == "reversed" and tx.posted_at > TX_END - timedelta(seconds=120):
            tx.status = "success"                # no room left in the window to reverse it
            stats["reversal_downgraded"] += 1

        if tx.kind == "inward":
            if tx.is_funding:
                acct = tx.dst
                tx.amount = draw_funding_kobo()
                tx.narration = "Wallet funding" if acct.type == "wallet" else "Initial deposit"
            else:
                acct = pick_account(tx.created_at)
                if acct is None:
                    return False
                tx.amount = draw_amount_kobo()
                tx.narration = rng.choice(NARRATION_INWARD)
            tx.dst = acct
            tx.institution_id = institution_ids[INSTITUTION_W.pick()]
            tx.cp_name = counterparty_name()
            tx.cp_account = digits(10)
            if posts:
                add_entry(tx.posted_at, tx, acct, "credit", tx.amount, "original")
                if tx.is_funding:
                    acct.funded_at = tx.posted_at
                    funded.append(acct)
                if tx.status == "reversed":
                    acct.held += tx.amount
            return True

        src = pick_account(tx.created_at, needs_funds=posts)
        if src is None:
            return False
        amount = draw_amount_kobo()
        if posts:
            amount = fit_debit(amount, src)

        if tx.kind == "outward":
            tx.src = src
            tx.amount = amount
            tx.channel_id = channel_ids[CHANNEL_CODE_W.pick()]
            tx.institution_id = institution_ids[INSTITUTION_W.pick()]
            tx.cp_name = counterparty_name()
            tx.cp_account = digits(10)
            tx.narration = rng.choice(NARRATION_OUTWARD)
            if posts:
                add_entry(tx.posted_at, tx, src, "debit", amount, "original")
            return True

        # intrabank
        own = [a for a in own_accounts.get(src.customer_id, [])
               if a is not src and eligible(a, tx.created_at)]
        if own and rng.random() < 0.12:
            dst = rng.choice(own)
            tx.narration = "Transfer to savings" if dst.type == "savings" else "Own account transfer"
        else:
            dst = pick_account(tx.created_at, exclude=src)
            if dst is None:
                return False
            tx.narration = rng.choice(NARRATION_INTRABANK)
        tx.src, tx.dst, tx.amount = src, dst, amount
        tx.channel_id = channel_ids[CHANNEL_CODE_W.pick()]
        if posts:
            add_entry(tx.posted_at, tx, src, "debit", amount, "original")
            add_entry(tx.posted_at, tx, dst, "credit", amount, "original")
            if tx.status == "reversed":
                dst.held += amount
        return True

    def apply_reversal(tx):
        ts = tx.reversed_at
        if tx.kind == "intrabank":
            tx.dst.held -= tx.amount
            add_entry(ts, tx, tx.dst, "debit", tx.amount, "reversal")
            add_entry(ts, tx, tx.src, "credit", tx.amount, "reversal")
        elif tx.kind == "inward":
            tx.dst.held -= tx.amount
            add_entry(ts, tx, tx.dst, "debit", tx.amount, "reversal")
        else:
            add_entry(ts, tx, tx.src, "credit", tx.amount, "reversal")

    # Plan: one opening inward per active account, then the general traffic.
    for a in active:
        tx = Transfer("inward", "success", is_funding=True)
        tx.dst = a
        push(set_times(tx, rand_ts(0, FUNDING_DAYS)), "tx", tx)
    general = (["intrabank"] * N_INTRABANK + ["inward"] * (N_INWARD - len(active))
               + ["outward"] * N_OUTWARD)
    for kind in general:
        tx = Transfer(kind, TRANSFER_STATUS_W.pick())
        push(set_times(tx, rand_ts(0, TX_DAYS)), "tx", tx)

    while heap:
        _, _, event, tx = heapq.heappop(heap)
        if event == "reversal":
            apply_reversal(tx)
            continue
        if not apply(tx):
            later = tx.created_at + timedelta(minutes=rng.randint(5, 30))
            if later > LAST_CREATE:
                stats["dropped"][tx.kind] += 1
                continue
            stats["deferred"] += 1
            push(set_times(tx, later), "tx", tx)
            continue

        while True:
            sid = f"{SESSION_PREFIX}{tx.created_at:%y%m%d%H%M%S}{rng.randrange(10**12):012d}"
            if sid not in session_ids:
                session_ids.add(sid)
                break
        tx.session_id = sid
        if tx.status in ("success", "reversed"):
            tx.response = SUCCESS_MSG
        elif tx.status == "failed":
            tx.response = rng.choice(FAIL_REASONS)
        if tx.status == "reversed":
            room = int((TX_END - tx.posted_at).total_seconds())
            delay = rng.randint(600, 48 * 3600) if room > 600 else rng.randint(60, room)
            tx.reversed_at = min(tx.posted_at + timedelta(seconds=delay), TX_END)
            tx.reversal_reason = rng.choice(REVERSAL_REASONS)
            push(tx.reversed_at, "reversal", tx)
        tx.order = next(order)
        transfers.append(tx)

    return transfers, ledger, stats


# Veracore accounts are referenced by account NUMBER. For outward transfers the
# destination is a plain 10-digit number at the beneficiary's bank; for inward
# transfers the sender is a plain 10-digit number at the sender's bank.
TRANSFER_SQL = {
    "intrabank": ("""INSERT INTO intrabank_transfer
        (session_id, sender_account, destination_account, channel_id, amount, narration,
         status, created_at, posted_at, response_message, reversed_at, reversal_reason)
        VALUES %s RETURNING session_id, intrabank_transfer_id""",
                  lambda t: (t.session_id, t.src.number, t.dst.number, t.channel_id)),
    "outward": ("""INSERT INTO outward_transfer
        (session_id, sender_account, destination_account, beneficiary_name, channel_id,
         institution_id, amount, narration, status, created_at, posted_at,
         response_message, reversed_at, reversal_reason)
        VALUES %s RETURNING session_id, outward_transfer_id""",
                lambda t: (t.session_id, t.src.number, t.cp_account, t.cp_name, t.channel_id,
                           t.institution_id)),
    "inward": ("""INSERT INTO inward_transfer
        (session_id, sender_account, sender_name, destination_account, institution_id,
         amount, narration, status, created_at, posted_at, response_message, reversed_at,
         reversal_reason)
        VALUES %s RETURNING session_id, inward_transfer_id""",
               lambda t: (t.session_id, t.cp_account, t.cp_name, t.dst.number, t.institution_id)),
}


def seed_transfers(cur, transfers):
    """Per batch, in created_at order: session_registry rows first, then the transfer rows."""
    transfers.sort(key=lambda t: (t.created_at, t.order))
    for i in range(0, len(transfers), BATCH):
        chunk = transfers[i:i + BATCH]
        execute_values(cur, "INSERT INTO session_registry (session_id, transfer_type) VALUES %s",
                       [(t.session_id, t.kind) for t in chunk], page_size=BATCH)
        for kind in ("intrabank", "inward", "outward"):
            sql, head = TRANSFER_SQL[kind]
            items = [t for t in chunk if t.kind == kind]
            rows = [head(t) + (kobo_to_naira(t.amount), t.narration, t.status, t.created_at,
                               t.posted_at, t.response, t.reversed_at, t.reversal_reason)
                    for t in items]
            ids = dict(insert_returning(cur, sql, rows))
            for t in items:
                t.db_id = ids[t.session_id]


def seed_ledger(cur, ledger):
    ledger.sort(key=lambda e: (e[0], e[1]))
    rows = []
    for posted_at, _, tx, account_number, direction, kobo, entry_kind in ledger:
        rows.append((account_number,
                     tx.db_id if tx.kind == "intrabank" else None,
                     tx.db_id if tx.kind == "outward" else None,
                     tx.db_id if tx.kind == "inward" else None,
                     direction, kobo_to_naira(kobo), posted_at, entry_kind))
    execute_values(cur, """INSERT INTO ledger_entry
        (account_number, intrabank_transfer_id, outward_transfer_id, inward_transfer_id,
         direction, amount, posted_at, entry_kind) VALUES %s""", rows, page_size=LEDGER_BATCH)
    return len(rows)


def build_audit(customers, accounts, transfers):
    owner = {a.id: a.customer_id for a in accounts}
    customer_by_id = {c["id"]: c for c in customers}
    customer_ids = [c["id"] for c in customers]
    large = [t for t in transfers
             if t.status in ("success", "reversed") and t.amount >= LARGE_TRANSFER_KOBO]
    rng.shuffle(large)
    events = []
    for _ in range(N_AUDIT):
        etype = AUDIT_TYPE_W.pick()
        if etype == "large_transfer" and not large:
            etype = "failed_login"
        ip = random_ip()
        if etype == "large_transfer":
            t = large.pop()
            acct = t.dst if t.kind == "inward" else t.src
            cid = owner[acct.id]
            occurred = min(t.posted_at + timedelta(seconds=rng.randint(1, 120)), TX_END)
            severity = "high" if t.amount >= 100_000_000 else rng.choice(["medium", "high"])
            details = (f"{t.kind.capitalize()} transfer of {fmt_naira(t.amount)} flagged for review; "
                       f"session_id {t.session_id}")
        else:
            occurred = rand_ts(0, TX_DAYS)
            severity = SEVERITY_W[etype].pick()
            cid = rng.choice(customer_ids)
            if etype == "failed_login":
                if rng.random() < NULL_CUSTOMER_SHARE_OF_FAILED_LOGIN:
                    cid = None
                    severity = rng.choice(["medium", "high"])
                    details = (f"Failed login for unregistered phone number "
                               f"{PHONE_PREFIX_W.pick()}{digits(8)}")
                else:
                    n = rng.randint(3, 6)
                    details = (f"{n} failed PIN attempts on {rng.choice(['mobile app', 'web banking', 'USSD'])}"
                               + ("; access temporarily locked" if n >= 5 else ""))
            elif etype == "new_device":
                details = f"Login from new device: {rng.choice(DEVICES)}"
            elif etype == "password_change":
                details = rng.choice(["Password changed via mobile app",
                                      "Transaction PIN reset after OTP verification",
                                      "Password reset from web banking"])
            else:
                tier = customer_by_id[cid]["kyc"]
                details = (f"KYC upgraded to tier {tier} after document verification" if tier > 1
                           else rng.choice(["BVN submitted for verification",
                                            "Identity document uploaded, pending review"]))
        events.append((cid, etype, severity, occurred, ip, details))
    events.sort(key=lambda e: e[3])
    return events


def seed_audit(cur, events):
    execute_values(cur, """INSERT INTO audit_event
        (customer_id, event_type, severity, occurred_at, ip_address, details) VALUES %s""",
                   events, page_size=BATCH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    started = time.time()
    conn = connect()
    try:
        with conn:                                   # one transaction; rolls back on error
            with conn.cursor() as cur:
                ensure_empty(cur)
                channel_ids, institution_ids = seed_reference(cur)
                print(f"channel: {len(channel_ids)}  external_institution: {len(institution_ids)}")

                customers = build_customers()
                seed_customers(cur, customers)
                print(f"customer: {len(customers)}")

                accounts = build_accounts(customers)
                seed_accounts(cur, accounts)
                by_status = {s: sum(a.status == s for a in accounts) for s in ("active", "frozen", "closed")}
                print(f"account: {len(accounts)}  {by_status}")

                transfers, ledger, stats = simulate(accounts, channel_ids, institution_ids)
                by_kind = {k: sum(t.kind == k for t in transfers) for k in ("intrabank", "inward", "outward")}
                print(f"transfers simulated: {len(transfers)}  {by_kind}")
                print(f"  deferred (no eligible account yet, retried later): {stats['deferred']}")
                print(f"  dropped (could not be placed before the cut-off): {stats['dropped']}")
                print(f"  debits shrunk to fit the available balance: {stats['shrunk']}")
                print(f"  reversals turned into success (too close to cut-off): {stats['reversal_downgraded']}")

                seed_transfers(cur, transfers)
                print(f"session_registry + transfers inserted: {len(transfers)}")
                print(f"ledger_entry: {seed_ledger(cur, ledger)}")

                events = build_audit(customers, accounts, transfers)
                seed_audit(cur, events)
                print(f"audit_event: {len(events)}")
        print(f"Committed in {time.time() - started:.1f} s (seed {SEED}).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
