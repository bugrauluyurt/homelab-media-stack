- VPN recovery no longer recreates downloaders while the tunnel is unhealthy. The existing
  port-sync timer restores stopped or detached downloaders after the VPN recovers, without
  restarting unrelated services. Invalid qBittorrent API responses no longer result in guessed
  preference writes, and recovery is reported only after port verification.
