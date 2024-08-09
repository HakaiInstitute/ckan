Hakai CKAN Catalogue

This repository is the Hakai fork of the CKAN metadata catalogue. it is heavily based on the CIOOS fork which it's self is forked from the core CKAN project. For a full description of what CKAN is and how it works see https://github.com/ckan/ckan/. Some documentation as it pertains to the Hakai catalogue can be found in ./docs

- [How to install this code](#how-to-install-this-code)
- [Section # How to run/deploy this code](#section--how-to-rundeploy-this-code)
- [Section # The URL where this code is deployed](#section--the-url-where-this-code-is-deployed)

# How to install this code
clone this repo
```
git clone https://github.com/HakaiInstitute/ckan.git
```

populate the env file
```
cd ckan/contrib/docker
cp .env.template .env
nano .env
```

pull images from docker hub and start the containers
```
sudo docker-compose up -d
```

assuming you used the default settings you can now visit the site at `http://localhost:5000`


# Section # How to run/deploy this code
Same as above but use an apache or nginx proxy to direct traffic to the container. CKAN assumes it is at the root of your domain so directing `/` to localhost:5000 will work while `/ckan/` will not.

# Section # The URL where this code is deployed
- https://catalogue.hakai.org/