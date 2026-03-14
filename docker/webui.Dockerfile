FROM node:22-alpine AS build

WORKDIR /webui
COPY webui/package*.json ./
RUN npm ci
COPY webui/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.default.conf /etc/nginx/templates/default.conf.template
COPY --from=build /webui/dist /usr/share/nginx/html

EXPOSE 80
