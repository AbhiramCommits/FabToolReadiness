#!/usr/bin/env python3
"""fabtoolreadiness synthetic data generator.

Generates 24 months of realistic fab operations data and loads it into
PostgreSQL via SQLAlchemy/pandas. Both RNGs are seeded so runs are
reproducible. Expects the lookup tables (sites, parts, certifications)
to be populated already (sql/02_seed_lookups.sql).
"""

import calendar
import datetime as dt
import os
import random
from pathlib import Path

import pandas as pd
from faker import Faker
from sqlalchemy import create_engine, text

SEED = 42
TODAY = dt.date.today()
N_MONTHS = 24
N_TOOLS = 250
N_TECHS = 600
STOCKOUT_FRACTION = 0.08
NEAR_EXPIRY_FRACTION = 0.09
IN_PROGRESS_FRACTION = 0.08

TOOL_TYPES = ["ETCH", "LITHO", "CVD", "PVD", "CMP", "DIFF", "IMPLANT", "METRO", "WETS", "AMHS"]
TYPE_WEIGHTS = [0.14, 0.10, 0.13, 0.09, 0.10, 0.08, 0.07, 0.09, 0.09, 0.11]
PROCESS_AREA = {
    "ETCH": "Dry Etch Bay",
    "LITHO": "Litho Bay",
    "CVD": "Thin Films",
    "PVD": "Thin Films",
    "CMP": "Planarization",
    "DIFF": "Thermal",
    "IMPLANT": "Ion Implant",
    "METRO": "Metrology",
    "WETS": "Wet Clean",
    "AMHS": "Interbay Transport",
}
# Calendar-month utilization factor (fab loading is higher mid-year and Q3).
SEASONAL = {1: 0.95, 2: 0.92, 3: 1.05, 4: 1.10, 5: 1.08, 6: 1.12,
            7: 1.00, 8: 1.02, 9: 1.15, 10: 1.12, 11: 1.05, 12: 0.88}
SHIFT_WEIGHTS = {"A": 0.33, "B": 0.33, "C": 0.24, "D": 0.10}

random.seed(SEED)
Faker.seed(SEED)
fake = Faker()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env() -> dict:
    env = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def connect():
    env = load_env()
    params = {
        "host": os.environ.get("FABTOOL_DB_HOST", "localhost"),
        "port": int(os.environ.get("FABTOOL_DB_PORT", "5433")),
        "name": os.environ.get("FABTOOL_DB_NAME", "fabtool"),
        "user": os.environ.get("FABTOOL_DB_USER", "fabtool"),
        "password": env.get("POSTGRES_PASSWORD")
                    or os.environ.get("POSTGRES_PASSWORD", ""),
    }
    url = (f"postgresql+psycopg2://{params['user']}:{params['password']}"
           f"@{params['host']}:{params['port']}/{params['name']}")
    return create_engine(url)


def month_start(d: dt.date) -> dt.date:
    return dt.date(d.year, d.month, 1)


def add_months(d: dt.date, months: int) -> dt.date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def rand_date(start: dt.date, end: dt.date) -> dt.date:
    span = (end - start).days
    return start + dt.timedelta(days=random.randint(0, max(span, 0)))


def day_in_month(ms: dt.date) -> dt.date:
    days = calendar.monthrange(ms.year, ms.month)[1]
    last = min(days, TODAY.day) if ms == month_start(TODAY) else days
    return ms + dt.timedelta(days=random.randint(0, last - 1))


# ---------------------------------------------------------------------------
# Tools + BOM
# ---------------------------------------------------------------------------

def generate_tools(sites: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tool_id = 1
    per_site = {site_id: N_TOOLS // len(sites) + (1 if i < N_TOOLS % len(sites) else 0)
                for i, site_id in enumerate(sites["site_id"])}
    for _, site in sites.iterrows():
        seq = {}
        for _ in range(per_site[site["site_id"]]):
            ttype = random.choices(TOOL_TYPES, weights=TYPE_WEIGHTS, k=1)[0]
            seq[ttype] = seq.get(ttype, 0) + 1
            rows.append({
                "tool_id": tool_id,
                "site_id": int(site["site_id"]),
                "tool_code": f"{ttype}-{site['site_code']}-{seq[ttype]:03d}",
                "tool_type": ttype,
                "process_area": PROCESS_AREA[ttype],
                "install_date": rand_date(dt.date(2015, 1, 1), dt.date(2024, 9, 30)),
                "criticality": random.choices([1, 2, 3, 4, 5],
                                              weights=[0.12, 0.18, 0.32, 0.26, 0.12], k=1)[0],
            })
            tool_id += 1
    return pd.DataFrame(rows)


def generate_bom(tools: pd.DataFrame, parts: pd.DataFrame) -> pd.DataFrame:
    consumable_ids = set(parts.loc[parts["is_consumable"], "part_id"])
    rows = []
    for _, tool in tools.iterrows():
        n_parts = random.randint(5, 15)
        for part_id in random.sample(list(parts["part_id"]), n_parts):
            if int(part_id) in consumable_ids:
                qty = random.choice([1, 1, 2, 2, 2, 3, 4, 4, 6, 8])
            else:
                qty = random.choice([1, 1, 1, 1, 2, 2, 3, 0.5])
            rows.append({
                "tool_id": int(tool["tool_id"]),
                "part_id": int(part_id),
                "qty_per_tool": float(qty),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Inventory + stock movements
# ---------------------------------------------------------------------------

def generate_inventory_and_movements(sites: pd.DataFrame, parts: pd.DataFrame,
                                     tools: pd.DataFrame):
    tools_by_site = {
        int(site_id): tools.loc[tools["site_id"] == site_id, "tool_id"].tolist()
        for site_id in sites["site_id"]
    }
    pairs = [(int(s.site_id), int(p.part_id))
             for s in sites.itertuples() for p in parts.itertuples()]
    random.shuffle(pairs)
    n_stockout = round(len(pairs) * STOCKOUT_FRACTION)
    stockout_pairs = set(random.sample(pairs, n_stockout))

    month_starts = []
    ms = month_start(TODAY)
    for _ in range(N_MONTHS):
        month_starts.append(ms)
        ms = month_start(ms - dt.timedelta(days=1))
    month_starts.reverse()

    inventory_rows = []
    movement_rows = []
    stockout_month_count = 0
    total_stockout_pairs_hit = 0
    movement_id = 1

    for site_id, part_id in pairs:
        part = parts.loc[parts["part_id"] == part_id].iloc[0]
        lead_months = max(1, int(round(int(part["lead_time_days"]) / 30)))
        lam = random.randint(8, 40) if bool(part["is_consumable"]) else random.randint(1, 6)
        safety = max(1, round(lam * lead_months * 0.6))
        reorder = safety * 2
        is_stockout = (site_id, part_id) in stockout_pairs
        if is_stockout:
            on_hand = round(reorder * random.uniform(0.1, 0.4))
            window_start = random.randint(4, 14)
            window_end = min(window_start + random.randint(4, 8), N_MONTHS - 2)
        else:
            on_hand = round(reorder * random.uniform(1.2, 2.4))
            window_start = window_end = None

        pending_arrival = None  # (arrival_month_index, qty)
        hit_zero = False

        for m, ms_date in enumerate(month_starts):
            # 1) receipts due this month
            if pending_arrival is not None and pending_arrival[0] == m:
                on_hand += pending_arrival[1]
                movement_rows.append({
                    "movement_id": movement_id, "site_id": site_id, "part_id": part_id,
                    "tool_id": None, "movement_date": day_in_month(ms_date),
                    "qty_delta": pending_arrival[1], "movement_type": "receipt",
                })
                movement_id += 1
                pending_arrival = None

            # 2) consumption (seasonal demand, split into several movements)
            in_window = is_stockout and window_start <= m < window_end
            mult = 4.0 if in_window else 1.0
            demand = round(lam * SEASONAL[ms_date.month] * random.uniform(0.8, 1.2)
                           * (1 + 0.004 * m) * mult)
            if in_window:
                demand = max(demand, 2)
            consume = min(demand, on_hand)
            if consume > 0:
                on_hand -= consume
                if consume < demand:
                    stockout_month_count += 1
                    hit_zero = True
                k = min(consume, random.choice([1, 2, 2, 2, 3, 3, 3, 4, 4, 5]))
                cuts = sorted(random.sample(range(1, consume), k - 1)) if k > 1 else []
                shares = []
                prev = 0
                for c in cuts:
                    shares.append(c - prev)
                    prev = c
                shares.append(consume - prev)
                tool_id = random.choice(tools_by_site[site_id])
                for share in shares:
                    movement_rows.append({
                        "movement_id": movement_id, "site_id": site_id, "part_id": part_id,
                        "tool_id": tool_id, "movement_date": day_in_month(ms_date),
                        "qty_delta": -share, "movement_type": "consumption",
                    })
                    movement_id += 1

            # 3) replenishment ordering
            if not in_window and pending_arrival is None and on_hand < reorder:
                if is_stockout:
                    order_qty = max(round(lam * 0.6) + safety, safety + 1)
                else:
                    order_qty = round(lam * 2.0) + safety
                arrival = m + lead_months
                if arrival < N_MONTHS:
                    pending_arrival = (arrival, order_qty)

            # 4) cycle-count adjustments
            if random.random() < 0.40:
                delta = random.randint(-6, 6)
                if delta < 0 and -delta > on_hand:
                    delta = -on_hand
                if delta != 0:
                    on_hand += delta
                    movement_rows.append({
                        "movement_id": movement_id, "site_id": site_id, "part_id": part_id,
                        "tool_id": None, "movement_date": day_in_month(ms_date),
                        "qty_delta": delta, "movement_type": "adjustment",
                    })
                    movement_id += 1

            # 5) scrap / write-off
            scrap_prob = 0.25 if bool(part["is_consumable"]) else 0.10
            if on_hand > 0 and random.random() < scrap_prob:
                scrap_qty = -min(random.randint(1, 5), on_hand)
                on_hand += scrap_qty
                movement_rows.append({
                    "movement_id": movement_id, "site_id": site_id, "part_id": part_id,
                    "tool_id": random.choice(tools_by_site[site_id])
                              if random.random() < 0.6 else None,
                    "movement_date": day_in_month(ms_date),
                    "qty_delta": scrap_qty, "movement_type": "scrap",
                })
                movement_id += 1

        if is_stockout and hit_zero:
            total_stockout_pairs_hit += 1
        inventory_rows.append({
            "site_id": site_id,
            "part_id": part_id,
            "on_hand_qty": on_hand,
            "reorder_point": reorder,
            "safety_stock": safety,
            "last_counted_date": rand_date(TODAY - dt.timedelta(days=90), TODAY),
        })

    inventory_df = pd.DataFrame(inventory_rows)
    movements_df = pd.DataFrame(movement_rows)
    return inventory_df, movements_df, {
        "n_stockout_pairs": n_stockout,
        "stockout_pairs_hit_zero": total_stockout_pairs_hit,
        "stockout_months": stockout_month_count,
    }


# ---------------------------------------------------------------------------
# Technicians, certifications, training
# ---------------------------------------------------------------------------

def generate_people(sites: pd.DataFrame, certs: pd.DataFrame,
                    thin_types: list) -> tuple:
    tech_rows = []
    shift_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    tech_id = 1
    for _, site in sites.iterrows():
        for _ in range(N_TECHS // len(sites)):
            shift = random.choices(list(SHIFT_WEIGHTS), weights=list(SHIFT_WEIGHTS.values()), k=1)[0]
            shift_counts[shift] += 1
            tech_rows.append({
                "tech_id": tech_id,
                "site_id": int(site["site_id"]),
                "employee_code": fake.unique.bothify("FAB-?#####"),
                "hire_date": rand_date(TODAY - dt.timedelta(days=365 * 12),
                                       TODAY - dt.timedelta(days=60)),
                "shift": shift,
                "is_active": random.random() < 0.88,
            })
            tech_id += 1
    technicians = pd.DataFrame(tech_rows)

    # Certification weights: deliberately thin on two tool types.
    cert_types = certs["tool_type"].tolist()
    weights = [0.12 if ct in thin_types else 1.0 for ct in cert_types]
    cert_ids = certs["cert_id"].tolist()

    def weighted_sample(k):
        pool = list(cert_ids)
        w = list(weights)
        picked = []
        for _ in range(min(k, len(pool))):
            total = sum(w)
            r = random.uniform(0, total)
            acc = 0
            for i, wi in enumerate(w):
                acc += wi
                if r <= acc:
                    picked.append(pool[i])
                    del pool[i]
                    del w[i]
                    break
        return picked

    tc_rows = []
    tr_rows = []
    completion_id = 1
    for _, tech in technicians.iterrows():
        if bool(tech["is_active"]):
            if tech["shift"] == "D":          # thin coverage on D shift
                n_certs = random.randint(0, 2)
            else:
                n_certs = random.randint(2, 6)
        else:
            n_certs = random.randint(0, 3)
        for cert_id in weighted_sample(n_certs):
            cert = certs.loc[certs["cert_id"] == cert_id].iloc[0]
            validity = int(cert["validity_months"])

            if random.random() < IN_PROGRESS_FRACTION:
                tc_rows.append({
                    "tech_id": int(tech["tech_id"]), "cert_id": int(cert_id),
                    "earned_date": None, "expires_date": None, "status": "in_progress",
                })
                # In-progress training: enrolled a while ago, never completed.
                for _ in range(random.randint(1, 2)):
                    enrolled = rand_date(TODAY - dt.timedelta(days=240),
                                         TODAY - dt.timedelta(days=15))
                    tr_rows.append({
                        "completion_id": completion_id,
                        "tech_id": int(tech["tech_id"]), "cert_id": int(cert_id),
                        "enrolled_date": enrolled, "completed_date": None,
                        "hours_spent": None,
                    })
                    completion_id += 1
                continue

            if random.random() < NEAR_EXPIRY_FRACTION:
                # Force expiry within the next 90 days.
                expires = TODAY + dt.timedelta(days=random.randint(1, 90))
                earned = add_months(expires, -validity)
            else:
                earned = add_months(TODAY, -random.randint(2, validity * 2))
                expires = add_months(earned, validity)
            status = "expired" if expires < TODAY else "active"
            tc_rows.append({
                "tech_id": int(tech["tech_id"]), "cert_id": int(cert_id),
                "earned_date": earned, "expires_date": expires, "status": status,
            })

            # Training history for completed certifications.
            for _ in range(random.randint(1, 3)):
                enrolled = add_months(earned, -random.randint(1, 4))
                if random.random() < 0.75:
                    completed = rand_date(enrolled, earned)
                    tr_rows.append({
                        "completion_id": completion_id,
                        "tech_id": int(tech["tech_id"]), "cert_id": int(cert_id),
                        "enrolled_date": enrolled, "completed_date": completed,
                        "hours_spent": round(random.uniform(4.0, 40.0), 1),
                    })
                else:
                    tr_rows.append({
                        "completion_id": completion_id,
                        "tech_id": int(tech["tech_id"]), "cert_id": int(cert_id),
                        "enrolled_date": enrolled, "completed_date": None,
                        "hours_spent": None,
                    })
                completion_id += 1

    tech_certs = pd.DataFrame(tc_rows)
    trainings = pd.DataFrame(tr_rows)
    return technicians, tech_certs, trainings, shift_counts


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

TRUNCATE_SQL = """
TRUNCATE training_completions, tech_certifications, technicians,
         stock_movements, inventory, tool_bom, tools
RESTART IDENTITY CASCADE
"""


def load(engine, **frames):
    with engine.begin() as conn:
        conn.execute(text(TRUNCATE_SQL))
        for table, df in frames.items():
            if df is None or df.empty:
                continue
            df.to_sql(table, conn, if_exists="append", index=False,
                      method="multi", chunksize=5000)
        for table, col in [("tools", "tool_id"),
                           ("stock_movements", "movement_id"),
                           ("technicians", "tech_id"),
                           ("training_completions", "completion_id")]:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                f"COALESCE(MAX({col}), 1)) FROM {table}"))


def print_row_counts(engine):
    tables = ["sites", "tools", "parts", "tool_bom", "inventory",
              "stock_movements", "technicians", "certifications",
              "tech_certifications", "training_completions"]
    print("\nTable row counts:")
    with engine.connect() as conn:
        for table in tables:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  {table:>22}: {n}")


def main():
    engine = connect()
    sites = pd.read_sql("SELECT site_id, site_code, site_name FROM sites", engine)
    parts = pd.read_sql("SELECT part_id, part_number, lead_time_days, is_consumable "
                        "FROM parts", engine)
    certs = pd.read_sql("SELECT cert_id, cert_code, tool_type, validity_months "
                        "FROM certifications", engine)

    thin_types = random.sample(sorted(certs["tool_type"].unique().tolist()), 2)
    print(f"RNG seeds: random={SEED}, faker={SEED}")
    print(f"Thin coverage tool types: {thin_types}")
    print(f"Lookups loaded: {len(sites)} sites, {len(parts)} parts, "
          f"{len(certs)} certifications")

    tools = generate_tools(sites)
    bom = generate_bom(tools, parts)
    inventory, movements, stockout_stats = generate_inventory_and_movements(
        sites, parts, tools)
    technicians, tech_certs, trainings, shift_counts = generate_people(
        sites, certs, thin_types)

    near_expiry = int(((tech_certs["status"] == "active")
                       & (tech_certs["expires_date"] <= TODAY + dt.timedelta(days=90))
                       & (tech_certs["expires_date"] >= TODAY)).sum())
    print(f"Tools: {len(tools)}, BOM rows: {len(bom)}, "
          f"movements: {len(movements)}, inventory rows: {len(inventory)}")
    print(f"Technicians: {len(technicians)} (by shift: "
          + ", ".join(f"{k}={v}" for k, v in shift_counts.items()) + ")")
    print(f"Stockouts: {stockout_stats['n_stockout_pairs']} part/site pairs flagged, "
          f"{stockout_stats['stockout_pairs_hit_zero']} actually hit zero, "
          f"{stockout_stats['stockout_months']} stockout pair-months")
    print(f"Tech certifications: {len(tech_certs)} "
          f"({(tech_certs['status'] == 'active').sum()} active, "
          f"{(tech_certs['status'] == 'expired').sum()} expired, "
          f"{(tech_certs['status'] == 'in_progress').sum()} in_progress, "
          f"{near_expiry} expiring within 90 days)")

    load(engine, tools=tools, tool_bom=bom, inventory=inventory,
         stock_movements=movements, technicians=technicians,
         tech_certifications=tech_certs, training_completions=trainings)
    print_row_counts(engine)


if __name__ == "__main__":
    main()
