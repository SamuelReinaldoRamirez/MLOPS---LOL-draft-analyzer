FROM grafana/grafana:11.2.0

# Provisioned datasource (-> Prometheus over Fly private net) + dashboard, baked
# into the image so the app is stateless (no volume needed).
COPY provisioning/ /etc/grafana/provisioning/
COPY dashboards/ /var/lib/grafana/dashboards/

# Admin user is fixed; the password is injected at deploy time via the Fly secret
# GF_SECURITY_ADMIN_PASSWORD (never baked into the image).
ENV GF_SECURITY_ADMIN_USER=admin
