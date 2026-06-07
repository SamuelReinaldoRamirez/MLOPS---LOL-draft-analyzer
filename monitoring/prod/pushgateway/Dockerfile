FROM prom/pushgateway:v1.9.0

# Bind IPv6 ([::]) so Fly's proxy (6PN) can reach it. Holds drift metrics pushed
# by the batch drift job; Prometheus scrapes it.
CMD ["--web.listen-address=[::]:9091"]
