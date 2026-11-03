#!/bin/bash
# Rebuild the Solr core from the image's managed schema. If you changed
# ckan/config/solr/schema.xml you must rebuild the image first - once the
# container has started there is no way to update the managed schema except
# through the Solr API.
#
#   sudo docker compose --env-file ./.hakaienv pull solr
#   # or: sudo docker compose --env-file ./.hakaienv build solr
#
# Every site shares one docker-compose.yml, so point this at the site's env
# file: `CKAN_ENV_FILE=./.mappenv ./update_solr.sh`. Defaults to ./.env.
set -euo pipefail

COMPOSE="sudo docker compose --env-file ${CKAN_ENV_FILE:-./.env}"

$COMPOSE rm -f -s solr
sudo docker volume rm docker_solr_data
$COMPOSE up -d ckan
sleep 5
sudo docker exec -it ckan ckan --config=/srv/app/ckan.ini search-index rebuild -r
