from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


POINTS = (
    'Q_soft_water',
    'P_soft_water',
    'Q_high_pressure_water',
    'P_high_pressure_water',
    'P_medium_pressure_water',
    'ExpansionTankLevel',
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / 'src'))
    from pg_store import connect

    conn = connect(args.root / 'config' / 'sync_config.json')
    rows = conn.execute(
        '''
        SELECT r.variable_name, r.chinese_name, r.short_name, r.tag_long_name,
               r.description, v.ts, v.value, v.quality, v.value_type,
               v.source_server, v.collected_at
          FROM bf_sensor.sensor_registry r
          LEFT JOIN LATERAL (
              SELECT *
                FROM bf_sensor.one_minute_values x
               WHERE x.tag_long_name = r.tag_long_name
               ORDER BY x.ts DESC
               LIMIT 1
          ) v ON true
         WHERE r.variable_name = ANY(%s::text[])
         ORDER BY array_position(%s::text[], r.variable_name)
        ''',
        (list(POINTS), list(POINTS)),
    ).fetchall()
    print(json.dumps({'points': [dict(row) for row in rows]}, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
