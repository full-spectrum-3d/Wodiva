# Etap 1: build Angulara (Node z .nvmrc)
FROM node:24.22.3-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npx ng build

# Etap 2: statyczne pliki + proxy /api do backendu
FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/wodiva/browser /usr/share/nginx/html
EXPOSE 80
