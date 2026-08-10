"""Step-by-step MCP tool test using SSH tunnel via plink + direct DB queries.

Each step corresponds to an IMES MCP tool, verified against the real database.
"""
import subprocess, sys, time, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ---------------------------------------------------------------------------
# Step 0: Start SSH tunnel via plink
# ---------------------------------------------------------------------------
PASSWORD_FILE = r"C:\Users\hmw20\.codex\secrets\reliable-ssh-10-30-220-12.password"
with open(PASSWORD_FILE, 'rb') as f:
    PASSWORD = f.read().decode('utf-8').strip()

HOSTKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDYkfg0Zva6XyQP1pSRwxOcUozBc6p3ltK8YcAaHipzf"

print("=" * 60)
print("STEP 0: Start SSH tunnel via plink")
print("=" * 60)

# Kill existing plink on 15433
subprocess.run('taskkill /F /IM plink.exe 2>nul', shell=True, capture_output=True)
time.sleep(0.5)

proc = subprocess.Popen(
    [
        r"C:\Users\hmw20\.local\bin\plink.exe",
        "-batch", "-N",
        "-hostkey", HOSTKEY,
        "-pw", PASSWORD,
        "-L", "15433:10.10.181.195:5432",
        "administrator@10.30.220.12",
    ],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)

# Wait for port
for i in range(15):
    time.sleep(1)
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 15433), timeout=1)
        s.close()
        print(f"  Tunnel ready after {i+1}s")
        break
    except OSError:
        if i == 14:
            print("  ERROR: Tunnel did not come up")
            sys.exit(1)

# ---------------------------------------------------------------------------
# Import psycopg
# ---------------------------------------------------------------------------
import psycopg

def query(user, password, sql, params=None):
    """Run a read-only query through the tunnel."""
    conn = psycopg.connect(
        host="127.0.0.1", port=15433, dbname="vastbase",
        user=user, password=password, connect_timeout=5,
        options="-c default_transaction_read_only=on",
    )
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    try:
        rows = cur.fetchall()
    except psycopg.ProgrammingError:
        rows = []
    cols = [d[0] for d in cur.description] if cur.description else []
    cur.close()
    conn.close()
    return cols, rows

# Credentials
LAB_USER = "lg_fq"
LAB_PW = "Jnmesxt@2026"
OPS_USER = "gl2#dmx"
OPS_PW = "gl2#dmx!"

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 1: imes_relay_status() - Connection health")
print("=" * 60)
for name, u, pw in [("lab (lg_fq)", LAB_USER, LAB_PW), ("ops (gl2#dmx)", OPS_USER, OPS_PW)]:
    try:
        cols, rows = query(u, pw, "SELECT current_database(), current_user, current_setting('transaction_read_only')")
        if rows:
            db, cu, ro = rows[0]
            print(f"  [{name}] OK - db={db}, user={cu}, read_only={ro}")
    except Exception as e:
        print(f"  [{name}] FAIL - {type(e).__name__}: {str(e)[:80]}")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 2: list_imes_business_objects() - Accessible tables")
print("=" * 60)
for name, u, pw in [("lab (lg_fq)", LAB_USER, LAB_PW), ("ops (gl2#dmx)", OPS_USER, OPS_PW)]:
    cols, rows = query(u, pw, """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema='public' AND table_type='VIEW'
        ORDER BY table_name
    """)
    print(f"  [{name}] {len(rows)} accessible views:")
    for r in rows[:12]:
        print(f"    {r[0]}.{r[1]} ({r[2]})")
    if len(rows) > 12:
        print(f"    ... and {len(rows)-12} more")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 3: 2#高炉生产实绩 - Latest batches")
print("=" * 60)
# Try lg_fq first, then gl2#dmx
for u, pw in [(OPS_USER, OPS_PW), (LAB_USER, LAB_PW)]:
    try:
        cols, rows = query(u, pw, """
            SELECT workdate, meltno, ironquan, workshift, prodcentercode
            FROM public.t_ipes_out_put
            WHERE prodcentercode = '2D012'
            ORDER BY workdate DESC, meltno DESC
            LIMIT 10
        """)
        if rows:
            print(f"  User={u}: Found {len(rows)} latest batches:")
            for r in rows:
                print(f"    workdate={r[0]}  meltno={r[1]}  ironquan={r[2]}t  shift={r[3]}")
            break
    except Exception as e:
        print(f"  User={u}: {type(e).__name__}")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 4: 2#高炉炉次总数")
print("=" * 60)
for u, pw in [(OPS_USER, OPS_PW), (LAB_USER, LAB_PW)]:
    try:
        cols, rows = query(u, pw, """
            SELECT COUNT(*) AS total, COUNT(DISTINCT meltno) AS unique_heats
            FROM public.t_ipes_out_put
            WHERE prodcentercode = '2D012'
        """)
        if rows:
            print(f"  User={u}: total={rows[0][0]}, unique heats={rows[0][1]}")
            break
    except Exception as e:
        print(f"  User={u}: {type(e).__name__}")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 5: 铁水化验 - Latest chemistry results")
print("=" * 60)
cols, rows = query(LAB_USER, LAB_PW, """
    SELECT meltno, takesampletime, "C", "Si", "Mn", "P", "S", "Ti", "V", "Cr", "Cu", "Ni", "As"
    FROM public.v_qpes_inner_batch_insp_final_sample
    WHERE meltno LIKE '2#%'
    ORDER BY takesampletime DESC
    LIMIT 10
""")
print(f"  Found {len(rows)} chemistry records:")
for r in rows:
    print(f"    {r[0]} @ {r[1]}: C={r[2]} Si={r[3]} Mn={r[4]} P={r[5]} S={r[6]}")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 6: 炉渣化验 - Latest slag results")
print("=" * 60)
cols, rows = query(LAB_USER, LAB_PW, """
    SELECT meltno, publishtime, tfe, feo, cao, sio2, mgo, al2o3, tio2, r2, r3, r4
    FROM public.v_qpes_slag_insoection_final
    WHERE meltno LIKE '2#%'
    ORDER BY publishtime DESC
    LIMIT 5
""")
print(f"  Found {len(rows)} slag records:")
for r in rows:
    print(f"    {r[0]} @ {r[1]}: TFe={r[2]} FeO={r[3]} CaO={r[4]} SiO2={r[5]} R2={r[9]} R3={r[10]}")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 7: query_hot_metal_chemistry_by_heat()")
print("=" * 60)
# Find a specific heat number
cols, rows = query(LAB_USER, LAB_PW, """
    SELECT meltno FROM public.v_qpes_inner_batch_insp_final_sample
    WHERE meltno LIKE '2#%'
    ORDER BY takesampletime DESC LIMIT 1
""")
if rows:
    heat = rows[0][0]
    print(f"  Latest heat: {heat}")
    cols, rows = query(LAB_USER, LAB_PW, """
        SELECT meltno, takesampletime, "C", "Si", "Mn", "P", "S", "Ti", "V", "Cr", "Cu", "Ni", "As", judgetime
        FROM public.v_qpes_inner_batch_insp_final_sample
        WHERE meltno = %s
        ORDER BY takesampletime DESC
    """, (heat,))
    if rows:
        r = rows[0]
        print(f"  Chemistry for {r[0]}:")
        print(f"    sample_time: {r[1]}  judge_time: {r[12]}")
        print(f"    C={r[2]}%  Si={r[3]}%  Mn={r[4]}%  P={r[5]}%  S={r[6]}%")
        print(f"    Ti={r[7]}%  V={r[8]}%  Cr={r[9]}%  Cu={r[10]}%  Ni={r[11]}%  As={r[12] if len(r)>12 else 'N/A'}")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 8: resolve_imes_natural_language()")
print("=" * 60)
tests = [
    "查一下2号炉最近5炉的铁水硅含量",
    "最近3炉出了多少铁",
    "当前有多少个炉次",
    "最近炉次的化验结果",
]
# Use Python semantic matching (same logic as MCP server)
import re
OBJECT_SEMANTICS = {
    "public.t_ipes_out_put": {"name": "生产实绩", "aliases": ["生产实绩", "出铁实绩", "铁量", "出铁量", "每炉铁量", "出了多少铁", "产量"]},
    "public.inner_batch_insp_bb": {"name": "铁水化验结果", "aliases": ["铁水化验", "铁水成分", "硅含量", "铁水硅", "碳硅锰磷硫"]},
    "public.v_qpes_inner_batch_insp_final_sample": {"name": "高炉铁水化验", "aliases": ["铁水成分", "炉次成分", "硅含量", "化验结果", "铁水化验"]},
    "public.v_qpes_slag_insoection_final": {"name": "高炉炉渣化验", "aliases": ["炉渣含量", "炉渣成分", "炉渣化验"]},
}

for q in tests:
    q_lower = q.lower()
    matches = []
    for obj, info in OBJECT_SEMANTICS.items():
        score = 0
        for alias in info["aliases"]:
            if alias in q:
                score += len(alias) * 2
        if score > 0:
            matches.append((score, obj, info["name"]))
    matches.sort(reverse=True)

    has_furnace = any(w in q for w in ["2号炉", "2#", "高炉", "炉"])
    has_count = any(w in q for w in ["多少", "几个", "总数", "计数", "统计"])
    has_recent = any(w in q for w in ["最近", "最新", "近期", "最近几", "最近n"])
    has_si = "硅" in q

    intent = "query"
    if has_count:
        intent = "count"
    elif has_recent:
        intent = "recent_query"

    rec = matches[0][1] if matches else "unknown"
    print(f"  Q: {q}")
    print(f"    intent={intent}, recommended_object={rec}, has_2f={has_furnace}")
    if matches:
        print(f"    top_matches: {[(m[1].split('.')[-1], m[2]) for m in matches[:3]]}")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("STEP 9: 第65炉次精确查询")
print("=" * 60)
# Search for heat 65
cols, rows = query(LAB_USER, LAB_PW, """
    SELECT meltno, takesampletime, "C", "Si", "Mn", "P", "S", "Ti", "V", "Cr", "Cu", "Ni", "As"
    FROM public.v_qpes_inner_batch_insp_final_sample
    WHERE meltno LIKE '2#%%-65' OR meltno LIKE '2#%%065'
    ORDER BY takesampletime DESC
    LIMIT 5
""")
if rows:
    print(f"  Found {len(rows)} records matching '65':")
    for r in rows:
        print(f"    {r[0]}: Si={r[3]}% C={r[2]}% Mn={r[4]}% P={r[5]}% S={r[6]}%")
else:
    print("  No exact '-65' match. Searching broader...")
    cols, rows = query(LAB_USER, LAB_PW, """
        SELECT meltno, takesampletime, "C", "Si", "Mn", "P", "S"
        FROM public.v_qpes_inner_batch_insp_final_sample
        WHERE meltno LIKE '2#%'
        ORDER BY takesampletime DESC
        LIMIT 20
    """)
    for r in rows:
        print(f"    {r[0]}: Si={r[3]}% C={r[2]}%")

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)

# Cleanup
subprocess.run('taskkill /F /IM plink.exe 2>nul', shell=True, capture_output=True)
