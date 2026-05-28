FROM postgres:16-alpine

# Copy init scripts and set execute permissions
COPY init.sql /docker-entrypoint-initdb.d/01_init.sql
COPY restore.sh /docker-entrypoint-initdb.d/02_restore.sh

RUN chmod +x /docker-entrypoint-initdb.d/02_restore.sh
