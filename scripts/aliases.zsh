# Media stack shortcuts. Source it from ~/.zshrc or ~/.bashrc; ARR_STACK_DIR overrides the repo path.
ARR_STACK_DIR=${ARR_STACK_DIR:-$HOME/arr-stack}
alias arr='managarr'                                    # Radarr + Sonarr + Lidarr TUI
alias qbt='qbt-tui'                                     # qBittorrent TUI
alias dock='lazydocker'                                 # every container
alias stack="cd $ARR_STACK_DIR"
alias health="$ARR_STACK_DIR/scripts/health-check"
alias update="$ARR_STACK_DIR/scripts/update"                # snapshot, update, health; --rollback <svc>
alias indexers="$ARR_STACK_DIR/scripts/check-indexers"
alias leaktest="$ARR_STACK_DIR/scripts/leak-test"
alias storage-off="$ARR_STACK_DIR/scripts/storage-off"
