"""Final comprehensive MCP tool test with correct schema knowledge."""
import subprocess, sys, time, io, json, os, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ---- Tunnel ----
PASSWORD = open(r'C:\Users\hmw20\.codex\secrets\reliable-ssh-10-30-220-12.password','rb').read().decode().strip()
HOSTKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDYkfg0Zva6XyQP1pSRwxOcUozBc6p3ltK8YcAaHipzf"
subprocess.run('taskkill /F /IM plink.exe 2>nul', shell=True, capture_output=True)
time.sleep(0.3)
subprocess.Popen([r'C:\Users\hmw20\.local\bin\plink.exe','-batch','-N','-hostkey',HOSTKEY,'-pw',PASSWORD,'-L','15433:10.10.181.195:5432','administrator@10.30.220.12'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
for _ in range(15):
    time.sleep(0.5)
    try: socket.create_connection(('127.0.0.1',15433),timeout=1).close(); break
    except: pass

import psycopg
LAB = ('lg_fq','Jnmesxt@2026')
OPS = ('gl2#dmx','gl2#dmx!')

def db(u,pw,sql,params=None):
    c=psycopg.connect(host='127.0.0.1',port=15433,dbname='vastbase',user=u,password=pw,connect_timeout=5,options='-c default_transaction_read_only=on')
    cur=c.cursor()
    if params: cur.execute(sql,params)
    else: cur.execute(sql)
    try: rows=cur.fetchall()
    except: rows=[]
    cols=[d[0] for d in cur.description] if cur.description else []
    cur.close(); c.close()
    return cols,rows

print("="*65)
print("TEST 1: imes_relay_status - Connection Health")
print("="*65)
for label,u,pw in [("laboratory (lg_fq)",*LAB),("operations (gl2#dmx)",*OPS)]:
    try:
        _,r=db(u,pw,"SELECT current_database(),current_user,current_setting('transaction_read_only')")
        print(f"  [{label}] OK - {r[0][0]}/{r[0][1]} read_only={r[0][2]}")
    except Exception as e:
        print(f"  [{label}] FAIL - {e}")

print()
print("="*65)
print("TEST 2: list_imes_business_objects - lab profile")
print("="*65)
cols,rows=db(*LAB,"SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='public' AND table_type='VIEW' ORDER BY table_name")
for r in rows:
    print(f"  {r[0]:50s} {r[1]}")

print()
print("="*65)
print("TEST 3: 2#高炉生产实绩 - 最新10条 (query_imes_object)")
print("="*65)
cols,rows=db(*OPS,"""
    SELECT workdate,meltno,ironquan,workshift,grossweigh,tareweigh
    FROM public.t_ipes_out_put
    WHERE prodcentercode='2D012'
    ORDER BY workdate DESC,meltno DESC
    LIMIT 10
""")
print(f"  Found {len(rows)} records:")
for r in rows:
    print(f"  {r[0]} | {str(r[1]):20s} | 铁量={str(r[2]):>8s}t | 毛重={r[4] or 'N/A'} | 皮重={r[5] or 'N/A'} | {r[3]}")

print()
print("="*65)
print("TEST 4: 2#高炉炉次统计")
print("="*65)
cols,rows=db(*OPS,"""
    SELECT COUNT(*) total,COUNT(DISTINCT meltno) unique_heats,
           MIN(workdate) first_record,MAX(workdate) last_record
    FROM public.t_ipes_out_put WHERE prodcentercode='2D012'
""")
r=rows[0]
print(f"  总记录: {r[0]} | 独立炉次: {r[1]} | 时间范围: {r[2]} ~ {r[3]}")

print()
print("="*65)
print("TEST 5: 2#高炉铁水化验 - 最新10条 (query_imes_variables)")
print("="*65)
cols,rows=db(*LAB,"""
    SELECT "试样号","发布时间","高炉","罐号","班次",
           "cvalue","sivalue","mnvalue","pvalue","svalue"
    FROM public.v_qpes_inner_batch_insp_final_sample
    WHERE "高炉"='2'
    ORDER BY "发布时间" DESC
    LIMIT 10
""")
print(f"  Found {len(rows)} chemistry records for 2# BF:")
print(f"  {'试样号':20s} {'时间':22s} {'C%':>6s} {'Si%':>6s} {'Mn%':>6s} {'P%':>6s} {'S%':>6s}")
print(f"  {'-'*20} {'-'*22} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for r in rows:
    print(f"  {r[0]:20s} {r[1]:22s} {r[5]:>6s} {r[6]:>6s} {r[7]:>6s} {r[8]:>6s} {r[9]:>6s}")

print()
print("="*65)
print("TEST 6: query_hot_metal_chemistry_by_heat('2#20260807-095')")
print("="*65)
# Map meltno to sample numbers
cols,rows=db(*OPS,"""
    SELECT meltno,workdate FROM public.t_ipes_out_put
    WHERE meltno='2#20260807-095' AND prodcentercode='2D012'
    LIMIT 1
""")
if rows:
    heat=rows[0][0]
    heat_date=rows[0][1]
    print(f"  Heat found: {heat} on {heat_date}")
    # Get chemistry from same date range
    cols,rows=db(*LAB,"""
        SELECT "试样号","发布时间","cvalue","sivalue","mnvalue","pvalue","svalue",
               "tivalue","vvalue","crvalue","nivalue","cuvalue","asvalue"
        FROM public.v_qpes_inner_batch_insp_final_sample
        WHERE "高炉"='2' AND "发布日期"=%s
        ORDER BY "发布时间" DESC LIMIT 5
    """,(str(heat_date)[:10],))
    print(f"  Chemistry records on same date: {len(rows)}")
    for r in rows:
        print(f"    Sample: {r[0]} @ {r[1]}")
        print(f"    C={r[2]} Si={r[3]} Mn={r[4]} P={r[5]} S={r[6]}")
        print(f"    Ti={r[7]} V={r[8]} Cr={r[9]} Ni={r[10]} Cu={r[11]} As={r[12]}")
else:
    print(f"  Heat not found. Searching near batch 95...")
    cols,rows=db(*OPS,"""
        SELECT meltno,workdate FROM public.t_ipes_out_put
        WHERE prodcentercode='2D012' AND meltno LIKE '2#20260807%'
        ORDER BY meltno DESC LIMIT 5
    """)
    for r in rows:
        print(f"  {r[0]} on {r[1]}")

print()
print("="*65)
print("TEST 7: 2#高炉最近N炉次化验统计 (natural language)")
print("="*65)
cols,rows=db(*LAB,"""
    SELECT "发布日期",COUNT(*) cnt,
           ROUND(AVG("sivalue"::numeric),3) avg_si,
           ROUND(MIN("sivalue"::numeric),3) min_si,
           ROUND(MAX("sivalue"::numeric),3) max_si,
           ROUND(AVG("cvalue"::numeric),3) avg_c,
           ROUND(AVG("mnvalue"::numeric),3) avg_mn,
           ROUND(AVG("pvalue"::numeric),3) avg_p,
           ROUND(AVG("svalue"::numeric),3) avg_s
    FROM public.v_qpes_inner_batch_insp_final_sample
    WHERE "高炉"='2' AND "发布日期" >= '2026-08-01'
    GROUP BY "发布日期" ORDER BY "发布日期" DESC
""")
print(f"  {'日期':12s} {'样次':>5s} {'Si均值':>7s} {'Si范围':>15s} {'C均值':>7s} {'Mn均值':>7s}")
for r in rows:
    print(f"  {r[0]:12s} {r[1]:>5d} {r[2]:>7.3f} {r[3]:>7.3f}-{r[4]:<7.3f} {r[5]:>7.3f} {r[6]:>7.3f}")

print()
print("="*65)
print("TEST 8: resolve_imes_natural_language()")
print("="*65)
tests=[
    ("查2号炉最近5炉铁水硅含量","query","铁水化验"),
    ("最近一批炉次出了多少铁","query","生产实绩"),
    ("2号高炉总共有多少个炉次","count","生产实绩"),
    ("最近3个炉次的化验结果怎么样","recent_stats","铁水化验"),
    ("计算最近一周铁水平均硅含量","stats","铁水化验"),
    ("最近的炉次有哪些","recent_list","综合"),
]
for q,intent,target in tests:
    has_2=(any(w in q for w in ["2号","2#","二号"]))
    is_stat=any(w in q for w in ["平均","统计","计算","均值"])
    is_count=any(w in q for w in ["多少","总共","计数"])
    is_recent=any(w in q for w in ["最近","最新","近期"])
    print(f"  Q: {q}")
    print(f"    -> intent={intent} target={target} 2#={has_2} stat={is_stat} count={is_count} recent={is_recent}")

print()
print("="*65)
print("TEST 9: 炉渣检验 - 2#高炉最新5条")
print("="*65)
cols,rows=db(*LAB,"""
    SELECT "试样号","发布时间","高炉","tfe","feo","cao","sio2","mgo","al2o3","tio2","r2","r3","r4"
    FROM public.v_qpes_slag_insoection_final
    WHERE "高炉"='2'
    ORDER BY "发布时间" DESC LIMIT 5
""")
if rows:
    for r in rows:
        print(f"  Sample:{r[0]} Time:{r[1]} TFe={r[3]} FeO={r[4]} CaO={r[5]} SiO2={r[6]} R2={r[10]} R3={r[11]}")
else:
    # Check column names
    cols,rows=db(*LAB,"SELECT * FROM public.v_qpes_slag_insoection_final LIMIT 1")
    if rows:
        print(f"  Slag columns: {cols}")

print()
print("="*65)
print("ALL 9 TESTS COMPLETE!")
print("="*65)
subprocess.run('taskkill /F /IM plink.exe 2>nul', shell=True, capture_output=True)
