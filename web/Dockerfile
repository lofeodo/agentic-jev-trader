# The web app's image: the built web app, served to the browser (spec appendix 10, section 3).
# Built and loaded into kind by `conda run -n agentic-jev-trader python infra/images.py build`, tagged with the git commit.
#
# Two stages: Node builds the app into plain files, then nginx (a standard web server) serves
# those files on port 80 and hands the page's /api/... requests to the API.

FROM node:24-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.28-alpine
COPY --from=build /web/dist /usr/share/nginx/html
# nginx fills ${API_URL} into this file when the container starts.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Where the API answers inside the cluster: the Kubernetes service named "api".
ENV API_URL=http://api:8000
