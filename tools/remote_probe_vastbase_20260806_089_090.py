from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db_dashboard"))

import heat_service  # noqa: E402


TARGETS = ("2#20260806-089", "2#20260806-090")


def dump(name: str, rows: list[dict]) -> None:
    print(json.dumps({"section": name, "count": len(rows)}, ensure_ascii=False))
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, default=str))


def main() -> int:
    params = heat_service.imes_ops_params()
    safe_params = {k: v for k, v in params.items() if "password" not in k.lower()}
    print(json.dumps({"section": "connection", "params": safe_params}, ensure_ascii=False, default=str))
    with heat_service._vastbase_connect(params) as conn:
        rows = conn.execute(
            """
            SELECT meltno, workdate, prodcentercode, sumbatchstart, sumbatchend,
                   sumbatch, opentime, closetime, tappingtime, theoryquan,
                   ironquan, slagrate, workshift, workclass
            FROM public.t_ipes_cond
            WHERE meltno = ANY(%s)
            ORDER BY meltno
            """,
            (list(TARGETS),),
        ).fetchall()
        dump("t_ipes_cond_exact", [dict(row) for row in rows])

        rows = conn.execute(
            """
            SELECT meltno, workdate, prodcentercode, ironquan, workshift, workclass, id
            FROM public.t_ipes_out_put
            WHERE meltno = ANY(%s)
            ORDER BY meltno, id
            """,
            (list(TARGETS),),
        ).fetchall()
        dump("t_ipes_out_put_exact", [dict(row) for row in rows])

    params = heat_service.imes_ops_params()
    safe_params = {k: v for k, v in params.items() if "password" not in k.lower()}
    print(json.dumps({"section": "hot_metal_ops_connection", "params": safe_params}, ensure_ascii=False, default=str))
    with heat_service._vastbase_connect(params) as conn:
        rows = conn.execute(
            """
            SELECT s.heatno, s.businessdate, s.prodcentercode, s.batchno,
                   b.judgetime, b.publishtime,
                   b.value_01 AS c, b.value_02 AS si, b.value_03 AS mn,
                   b.value_04 AS p, b.value_05 AS s
            FROM public.t_qpes_inner_batch AS s
            JOIN public.inner_batch_insp_bb AS b ON b.batchno = s.batchno
            WHERE s.heatno = ANY(%s)
            ORDER BY s.heatno, b.publishtime
            """,
            (list(TARGETS),),
        ).fetchall()
        dump("hot_metal_lab_exact", [dict(row) for row in rows])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



