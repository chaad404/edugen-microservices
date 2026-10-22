#!/bin/sh
# One PostgreSQL server, one database and one role per data-owning service (course chapter 5.1:
# database per service). A role can connect only to its own database.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE ROLE lab LOGIN PASSWORD '${LAB_DB_PASSWORD}';
    CREATE DATABASE lab OWNER lab;
    REVOKE ALL ON DATABASE lab FROM PUBLIC;

    CREATE ROLE review LOGIN PASSWORD '${REVIEW_DB_PASSWORD}';
    CREATE DATABASE review OWNER review;
    REVOKE ALL ON DATABASE review FROM PUBLIC;
EOSQL
