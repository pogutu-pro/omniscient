FROM node:22-alpine AS build

WORKDIR /app

# `npm ci`, not `npm install`: it installs exactly the lockfile, which is
# the only way the image is reproducible and the only way a tampered
# transitive dependency fails the build instead of shipping.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines import.meta.env.* into the bundle, so this is fixed at
# build time and there is no runtime override. The deploy workflow passes
# the real API URL here; changing the API's public URL means rebuilding
# the frontend.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
