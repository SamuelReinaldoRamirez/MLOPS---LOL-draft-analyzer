FROM prom/prometheus:v2.54.1

COPY prometheus.yml /etc/prometheus/prometheus.yml

# Same defaults as the upstream image, but bind on IPv6 ([::]) as well so Grafana
# can reach this instance over Fly's private 6PN network
# (http://lol-draft-prometheus.internal:9090). No public service is exposed.
CMD [ "--config.file=/etc/prometheus/prometheus.yml", \
      "--storage.tsdb.path=/prometheus", \
      "--web.console.libraries=/usr/share/prometheus/console_libraries", \
      "--web.console.templates=/usr/share/prometheus/consoles", \
      "--web.listen-address=[::]:9090" ]
