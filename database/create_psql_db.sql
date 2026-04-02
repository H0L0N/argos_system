CREATE DATABASE argos_system;

\c argos_system

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'argos') THEN
        CREATE USER argos WITH PASSWORD 'argos';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sql_agent') THEN
        CREATE ROLE sql_agent WITH LOGIN PASSWORD 'sql_agent';
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS app;

ALTER SCHEMA app OWNER TO argos;

ALTER USER argos
SET
    search_path TO app;
ALTER USER sql_agent SET search_path TO app;

GRANT USAGE ON SCHEMA app TO sql_agent;
GRANT CONNECT ON DATABASE argos_system TO sql_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO sql_agent;
ALTER DEFAULT PRIVILEGES FOR ROLE argos IN SCHEMA app GRANT SELECT ON TABLES TO sql_agent;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT SELECT ON TABLES TO sql_agent;

CREATE EXTENSION IF NOT EXISTS vector SCHEMA app;