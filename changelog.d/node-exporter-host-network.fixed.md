- Grafana's network panels show the server's real traffic. node-exporter now runs on the host
  network; in a container network it counted only its own container. `configure-uptime-kuma.py`
  updates the URL of a monitor whose service moved, so re-run it after updating.
