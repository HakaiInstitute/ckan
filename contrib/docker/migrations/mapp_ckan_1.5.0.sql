-- backup db
sudo docker exec -u root -ti db /bin/bash -c "export TERM=xterm; exec bash"
pg_dump -U ckan --format=custom -d ckan > /tmp/mapp_ckan.dump
exit
sudo docker cp db:/tmp/mapp_ckan.dump mapp_ckan.dump

-- restore backup of db
-- sudo docker-compose -f docker-compose.mapp.yml down
-- sudo docker volume rm docker_pg_data
-- sudo docker-compose -f docker-compose.mapp.yml up -d db
sudo docker cp mapp_ckan.dump db:/tmp/mapp_ckan.dump
sudo docker exec -u root -ti db /bin/bash -c "export TERM=xterm; exec bash"

pg_restore -U ckan --clean --if-exists -d ckan < /tmp/mapp_ckan.dump 
exit

sudo docker-compose -f docker-compose.mapp.yml up -d ckan
sudo docker-compose -f docker-compose.mapp.yml up -d


-- update some package fields which may have bad data in them
sudo docker exec -it db psql -U ckan

select * from package_extra where key = 'metadata-reference-date';
select * from package_extra where key = 'temporal-extent';
select key, value from package_extra where key = 'cited-responsible-party' and value like '%"position-name": "",%';
select key, value from package_extra where key = 'metadata-point-of-contact' and value like '%position-name%';
select key, value from package_extra where key = 'cited-responsible-party' and value  ~ '.*?"contact-info_online-resource_.*?';
select key, value from package_extra where key = 'cited-responsible-party' and value ~ '.*?"contact-info_online-resource": "([^{"]+)",.*?';

update package_extra
  set value = '[]'
  where key = 'metadata-reference-date' and value = '';

update package_extra
  set value = '[{"begin": "", "end": ""}]'
  where key = 'temporal-extent' and value = '';

update package_extra
  set value = '[' || value || ']'
  where key = 'temporal-extent' and value NOT LIKE '[%';

update package_extra
  set value = REGEXP_REPLACE(value, '"position-name": ".*?",', '', 'g')
  where key = 'cited-responsible-party' and value::text LIKE '%"position-name"%';

update package_extra
  set value = REGEXP_REPLACE(value, '"position-name": ".*?",', '', 'g')
  where key = 'metadata-point-of-contact' and value::text LIKE '%"position-name"%';  

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource_url": "(.*?)",', '"contact-info_online-resource": "{\"protocol\": \"WWW:LINK\", \"function\": \"information\", \"url\": \"\1\"}",', 'g')
  where key = 'cited-responsible-party' and value::text LIKE '%"contact-info_online-resource_url"%';

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource_.*?": \[\],', '', 'g')
  where key = 'cited-responsible-party' and value  ~ '.*?"contact-info_online-resource_.*?": \[\],.*?';

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource_.*?": ".*?",', '', 'g')
  where key = 'cited-responsible-party' and value  ~ '.*?"contact-info_online-resource_.*?';

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource": "([^{"]+)",', '"contact-info_online-resource": "{\"protocol\": \"WWW:LINK\", \"function\": \"information\", \"url\": \"\1\"}",', 'g')
  where key = 'cited-responsible-party' and value ~ '.*?"contact-info_online-resource": "[^{"]+",.*?';

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource_url": "(.*?)",', '"contact-info_online-resource": "{\"protocol\": \"WWW:LINK\", \"function\": \"information\", \"url\": \"\1\"}",', 'g')
  where key = 'metadata-point-of-contact' and value::text LIKE '%"contact-info_online-resource_url"%';

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource_.*?": \[\],', '', 'g')
  where key = 'metadata-point-of-contact' and value  ~ '.*?"contact-info_online-resource_.*?": \[\],.*?';

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource_.*?": ".*?",', '', 'g')
  where key = 'metadata-point-of-contact' and value  ~ '.*?"contact-info_online-resource_.*?';

update package_extra
  set value = REGEXP_REPLACE(value, '"contact-info_online-resource": "([^{"]+)",', '"contact-info_online-resource": "{\"protocol\": \"WWW:LINK\", \"function\": \"information\", \"url\": \"\1\"}",', 'g')
  where key = 'metadata-point-of-contact' and value ~ '.*?"contact-info_online-resource": "[^{"]+",.*?';


-- once done reindex the packages
sudo docker exec -it ckan ckan --config=/etc/ckan/production.ini search-index rebuild -r
-- sudo docker exec -it ckan ckan  --config=/etc/ckan/production.ini harvester reindex

sudo cp -r ./contrib/docker/production.ini $VOL_CKAN_CONFIG/production.ini


-- Rename mapp harvester from 'mapp waf' to 'MaPP'


