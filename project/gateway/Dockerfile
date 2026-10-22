# Build context: the project folder (the client is built here, then served by nginx)
FROM node:22-alpine AS build
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY client/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /client/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
