# Media stack shortcuts. Source it from ~/.zshrc or ~/.bashrc; MEDIA_STACK_DIR overrides the repo path.
# Used by: your shell, sourced from ~/.zshrc or ~/.bashrc.
# Changes: nothing.
MEDIA_STACK_DIR=${MEDIA_STACK_DIR:-$HOME/homelab-media-stack}
alias arr='managarr'                                    # Radarr + Sonarr + Lidarr TUI
alias qbt='qbt-tui'                                     # qBittorrent TUI
alias dock='lazydocker'                                 # every container
alias stack="cd $MEDIA_STACK_DIR"
alias health="$MEDIA_STACK_DIR/scripts/stack-health"
alias update="$MEDIA_STACK_DIR/scripts/stack-update"                # snapshot, update, health; --rollback <svc>
alias indexers="$MEDIA_STACK_DIR/scripts/indexers-check"
alias leaktest="$MEDIA_STACK_DIR/scripts/vpn-leak-test"
alias drive-off="$MEDIA_STACK_DIR/scripts/drive-off"
