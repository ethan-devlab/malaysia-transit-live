FROM python:3.12-alpine

RUN apk add --no-cache iptables su-exec

COPY egress_proxy.py /app/egress_proxy.py
COPY egress-proxy-entrypoint.sh /app/egress-proxy-entrypoint.sh
RUN chmod 0555 /app/egress-proxy-entrypoint.sh

EXPOSE 8888

ENTRYPOINT ["/app/egress-proxy-entrypoint.sh"]
