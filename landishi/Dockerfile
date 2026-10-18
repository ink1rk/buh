FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html novosti.html dokumenty.html oplata.html zayavka.html kontakty.html 404.html /usr/share/nginx/html/
COPY assets /usr/share/nginx/html/assets
EXPOSE 80
