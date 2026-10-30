#------------------------------------------------------------------------------#
# CKAN 2.12 — Debian bookworm / Python 3.14
#
# The 2.9 image was Alpine/Python 3.9 and installed extensions with
# `setup.py install && setup.py develop` into /usr/lib/python3.9/site-packages.
# The 2.10+ base images are Debian-based, install CKAN as an editable checkout
# under /srv/app/src, and keep site-packages at /usr/local/lib/python3.14.
#
# Build: a `builder` stage carries the compilers and -dev headers, the final
# stage keeps only the shared libraries needed at runtime.
#------------------------------------------------------------------------------#

ARG CKAN_BASE_TAG=2.12

#------------------------------------------------------------------------------#
FROM ckan/ckan-base:${CKAN_BASE_TAG} AS builder
#------------------------------------------------------------------------------#

USER root

# Set by the base image already; repeated so the build does not depend on
# base image internals.
ENV APP_DIR=/srv/app
ENV SRC_DIR=/srv/app/src
ENV CKAN_INI=${APP_DIR}/ckan.ini
ENV PIP_SRC=${SRC_DIR}
ENV CKAN_STORAGE_PATH=/var/lib/ckan

RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        g++ \
        git \
        libgdal-dev \
        libgeos-dev \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# GDAL's Python bindings are source-only on PyPI (no wheels) and must be built
# against — and pinned to — the exact libgdal that Debian ships, hence
# `gdal-config --version`. They still use distutils-era build commands, so
# setuptools must stay below 81 and numpy must be importable at build time;
# --no-build-isolation makes both visible to the build.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install "setuptools<81" numpy \
    && pip3 install --no-build-isolation "gdal==$(gdal-config --version)"

# pyproj ships manylinux wheels with PROJ bundled, so the from-source PROJ
# build the 2.9 image needed is no longer required.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install \
        ckanapi \
        pyproj \
        requests \
        'flask-debugtoolbar>=0.16'

#------------------------------------------------------------------------------#
# Extension requirements.
# Copied before the extension sources so that editing extension code does not
# invalidate the (slow) dependency layers.
#------------------------------------------------------------------------------#

WORKDIR $SRC_DIR

COPY ./contrib/docker/src/ckanext-dcat/requirements.txt $SRC_DIR/ckanext-dcat/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r $SRC_DIR/ckanext-dcat/requirements.txt

COPY ./contrib/docker/src/ckanext-harvest/requirements.txt $SRC_DIR/ckanext-harvest/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r $SRC_DIR/ckanext-harvest/requirements.txt

COPY ./contrib/docker/src/ckanext-spatial/requirements.txt $SRC_DIR/ckanext-spatial/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r $SRC_DIR/ckanext-spatial/requirements.txt

COPY ./contrib/docker/src/ckanext-cioos_harvest/requirements.txt $SRC_DIR/ckanext-cioos_harvest/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r $SRC_DIR/ckanext-cioos_harvest/requirements.txt

COPY ./contrib/docker/src/ckanext-cioos_theme/requirements.txt $SRC_DIR/ckanext-cioos_theme/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r $SRC_DIR/ckanext-cioos_theme/requirements.txt

#------------------------------------------------------------------------------#
# Extensions, ordered least- to most-frequently changed so that a theme edit
# rebuilds as few layers as possible.
#
# `pip install -e` replaces `setup.py install && setup.py develop`: setuptools
# removed the install command and Python 3.12 removed distutils from the
# stdlib. ckanext-envvars is already installed by the base image.
#------------------------------------------------------------------------------#

COPY ./contrib/docker/src/ckanext-geoview $SRC_DIR/ckanext-geoview
RUN pip3 install -e $SRC_DIR/ckanext-geoview

COPY ./contrib/docker/src/ckanext-dcat $SRC_DIR/ckanext-dcat
RUN pip3 install -e $SRC_DIR/ckanext-dcat

COPY ./contrib/docker/src/ckanext-scheming $SRC_DIR/ckanext-scheming
RUN pip3 install -e $SRC_DIR/ckanext-scheming

COPY ./contrib/docker/src/ckanext-fluent $SRC_DIR/ckanext-fluent
RUN pip3 install -e $SRC_DIR/ckanext-fluent

COPY ./contrib/docker/src/ckanext-harvest $SRC_DIR/ckanext-harvest
RUN pip3 install -e $SRC_DIR/ckanext-harvest

COPY ./contrib/docker/src/ckanext-spatial $SRC_DIR/ckanext-spatial
RUN pip3 install -e $SRC_DIR/ckanext-spatial

COPY ./contrib/docker/src/ckanext-cioos_harvest $SRC_DIR/ckanext-cioos_harvest
RUN pip3 install -e $SRC_DIR/ckanext-cioos_harvest

COPY ./contrib/docker/src/ckanext-cioos_theme $SRC_DIR/ckanext-cioos_theme
# `setup.py compile_catalog` is unavailable now that distutils is gone; pybabel
# is invoked directly with the domain/directory from the extension's setup.cfg.
RUN pip3 install -e $SRC_DIR/ckanext-cioos_theme \
    && cd $SRC_DIR/ckanext-cioos_theme \
    && pybabel compile -d ckanext/cioos_theme/i18n -D ckanext-cioos_theme -l fr

# Schemas are read at runtime from inside the scheming package directory.
COPY ./contrib/docker/src/cioos-siooc-schema/cioos-siooc_schema.json $SRC_DIR/ckanext-scheming/ckanext/scheming/cioos_siooc_schema.json
COPY ./contrib/docker/src/cioos-siooc-schema/organization.json $SRC_DIR/ckanext-scheming/ckanext/scheming/
COPY ./contrib/docker/src/cioos-siooc-schema/ckan_license.json $SRC_DIR/ckanext-scheming/ckanext/scheming/
COPY ./contrib/docker/src/cioos-siooc-schema/group.json $SRC_DIR/ckanext-scheming/ckanext/scheming/

#------------------------------------------------------------------------------#
FROM ckan/ckan-base:${CKAN_BASE_TAG}
#------------------------------------------------------------------------------#

USER root

ENV APP_DIR=/srv/app
ENV SRC_DIR=/srv/app/src
ENV CKAN_INI=${APP_DIR}/ckan.ini
ENV PIP_SRC=${SRC_DIR}
ENV CKAN_STORAGE_PATH=/var/lib/ckan

# Runtime counterparts of the -dev packages used in the builder stage.
#   libgdal32    — ckanext-spatial parses GML/WKT/GeoJSON geometries via OGR
#   libgeos-c1v5 — GEOS, for Shapely
#   cron         — drives contrib/docker/crontab in the ckan_run_harvester
#                  service. The 2.9 Alpine image provided busybox crond; Debian
#                  slim ships no cron at all.
RUN apt-get update && apt-get install --no-install-recommends -y \
        cron \
        libgdal32 \
        libgeos-c1v5 \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY --from=builder $SRC_DIR $SRC_DIR

# Setup CKAN. who.ini is gone: repoze.who was replaced by Flask-Login in 2.10.
COPY ./contrib/docker/production.ini $CKAN_INI
COPY ./contrib/docker/crontab $SRC_DIR/ckan/contrib/docker/crontab
COPY ./contrib/docker/wait-for-postgres.sh /wait-for-postgres.sh

RUN chmod +x /wait-for-postgres.sh \
    && mkdir -p $APP_DIR/logs \
    && touch "$APP_DIR/logs/ckan_access.log" \
    && touch "$APP_DIR/logs/ckan_default.log" \
    && chown -R ckan:ckan-sys $APP_DIR $CKAN_STORAGE_PATH

WORKDIR $APP_DIR

USER ckan
EXPOSE 5000

CMD ["bash", "/wait-for-postgres.sh", "db", "/srv/app/start_ckan.sh"]
