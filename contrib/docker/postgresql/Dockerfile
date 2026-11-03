#FROM postgres:9.6
#FROM mdillon/postgis:11
#FROM postgis/postgis:11-3.3
FROM postgis/postgis:16-3.6
LABEL org.opencontainers.image.authors="Open Knowledge"

# NOTE: there used to be a
#   RUN echo "host all all 0.0.0.0/0 md5" >> /var/lib/postgresql/data/pg_hba.conf
# here. It never had any effect: /var/lib/postgresql/data is a declared VOLUME
# in the upstream image, so writes to it during build are discarded, and the
# directory is empty at build time anyway because initdb runs at container
# start. The entrypoint already writes a `host all all all <method>` rule;
# POSTGRES_HOST_AUTH_METHOD overrides the method if it ever needs to change.
# From PostgreSQL 14 the default is scram-sha-256 rather than md5.

# Customize default user/pass/db
ENV POSTGRES_DB ckan
ENV POSTGRES_USER ckan
ARG POSTGRES_PASSWORD
ARG DS_RO_PASS

# Include datastore setup scripts
ADD ./contrib/docker/postgresql/docker-entrypoint-initdb.d /docker-entrypoint-initdb.d
