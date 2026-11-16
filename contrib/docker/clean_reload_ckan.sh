#!/bin/bash
# Stop CKAN and the harvesters and drop the ckan_home volume, so the next
# `up` reseeds /srv/app from the image instead of shadowing it with 2.9-era
# files. See docs/UPGRADE_2.9_TO_2.12.md.
#
# Every site shares one docker-compose.yml, so point this at the site's env
# file: `CKAN_ENV_FILE=./.mappenv ./clean_reload_ckan.sh`. Defaults to ./.env.
set -euo pipefail

COMPOSE="sudo docker compose --env-file ${CKAN_ENV_FILE:-./.env}"

$COMPOSE rm -f -s ckan_run_harvester
$COMPOSE rm -f -s ckan_fetch_harvester
$COMPOSE rm -f -s ckan_gather_harvester
$COMPOSE rm -f -s ckan
sudo docker volume rm docker_ckan_home
