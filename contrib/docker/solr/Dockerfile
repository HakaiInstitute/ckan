FROM solr:9
MAINTAINER Open Knowledge

EXPOSE 8983

# Enviroment
ENV SOLR_CORE ckan
ENV SOLR_CONFIG_DIR="/opt/solr/server/solr/configsets"
# Solr 9 names the managed schema file "managed-schema.xml" (it was
# "managed-schema", with no extension, up to Solr 8).
ENV SOLR_SCHEMA_FILE="$SOLR_CONFIG_DIR/ckan/conf/managed-schema.xml"
ENV SOLR_LOG_LEVEL=${SOLR_LOG_LEVEL:-WARN}

USER root

# Create a CKAN configset by copying the default one
RUN cp -R $SOLR_CONFIG_DIR/_default $SOLR_CONFIG_DIR/ckan

# Adding Files
ADD ./ckan/config/solr/schema.xml $SOLR_SCHEMA_FILE
RUN chmod 644 $SOLR_SCHEMA_FILE

# User
USER $SOLR_USER:$SOLR_USER

CMD ["sh", "-c", "solr-precreate ckan $SOLR_CONFIG_DIR/ckan"]
