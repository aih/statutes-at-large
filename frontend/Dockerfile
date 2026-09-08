# The reader: Astro 5 SSR on Node, behind the Caddy in deploy/.
FROM node:22-alpine AS build

WORKDIR /srv

COPY package.json package-lock.json ./
RUN NPM_CONFIG_FETCH_RETRIES=10 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=15000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=60000 \
    NPM_CONFIG_FETCH_TIMEOUT=120000 \
    npm ci

COPY . .
RUN npm run build

FROM node:22-alpine

WORKDIR /srv

ENV HOST=0.0.0.0 \
    PORT=4321 \
    NODE_ENV=production

# dist/server imports @xmldom/xmldom and astro's runtime from node_modules.
# @uswds/uswds is SCSS the build compiled away and stays out of this stage.
COPY package.json package-lock.json ./
RUN NPM_CONFIG_FETCH_RETRIES=10 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=15000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=60000 \
    NPM_CONFIG_FETCH_TIMEOUT=120000 \
    npm ci --omit=dev --ignore-scripts

COPY --from=build /srv/dist ./dist

EXPOSE 4321
CMD ["node", "./dist/server/entry.mjs"]
