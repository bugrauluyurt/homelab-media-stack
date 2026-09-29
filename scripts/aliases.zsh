# Media stack shortcuts. Source it from ~/.zshrc or ~/.bashrc; MEDIA_STACK_DIR overrides the repo path.
MEDIA_STACK_DIR=${MEDIA_STACK_DIR:-$HOME/homelab-media-stack}
alias arr='managarr'                                    # Radarr + Sonarr + Lidarr TUI
alias qbt='qbt-tui'                                     # qBittorrent TUI
alias dock='lazydocker'                                 # every container
alias stack="cd $MEDIA_STACK_DIR"
alias health="$MEDIA_STACK_DIR/scripts/health-check"
alias update="$MEDIA_STACK_DIR/scripts/update"                # snapshot, update, health; --rollback <svc>
alias indexers="$MEDIA_STACK_DIR/scripts/check-indexers"
alias leaktest="$MEDIA_STACK_DIR/scripts/leak-test"
alias storage-off="$MEDIA_STACK_DIR/scripts/storage-off"
