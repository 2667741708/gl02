-- Run this file from a maintenance database such as postgres.
-- It creates the application database used by 数据库同步和存取.

CREATE DATABASE bf_trend
    WITH
    ENCODING = 'UTF8'
    TEMPLATE = template0;

COMMENT ON DATABASE bf_trend IS 'GL02/GF2 required sensor 1min average storage, retained for 3 years.';
