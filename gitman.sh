#!/data/data/com.termux/files/usr/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo -e "${RED}Error:${NC} Folder ini bukan Git Repository"
    exit 1
fi

current_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null
}

pause() {
    echo
    read -rp "Tekan Enter untuk lanjut..."
}

header() {
    clear

    BRANCH=$(current_branch)

    echo -e "${CYAN}"
    echo "========================================"
    echo "          GIT MANAGER TERMUX"
    echo "========================================"
    echo -e "${NC}"

    echo -e "Branch Aktif : ${GREEN}${BRANCH}${NC}"
    echo

    git status --short

    echo
    echo "----------------------------------------"
}

commit_only() {
    read -rp "Pesan commit: " MSG

    [ -z "$MSG" ] && return

    git add .

    if git diff --cached --quiet; then
        echo
        echo -e "${YELLOW}Tidak ada perubahan.${NC}"
        pause
        return
    fi

    git commit -m "$MSG"

    pause
}

push_only() {
    read -rp "Push ke branch [$(current_branch)]: " BRANCH

    BRANCH=${BRANCH:-$(current_branch)}

    echo
    read -rp "Yakin push ke $BRANCH? [y/N]: " CONFIRM

    [[ ! "$CONFIRM" =~ ^[Yy]$ ]] && return

    git push origin "$BRANCH"

    pause
}

commit_push() {
    read -rp "Pesan commit: " MSG

    [ -z "$MSG" ] && return

    read -rp "Push ke branch [$(current_branch)]: " BRANCH

    BRANCH=${BRANCH:-$(current_branch)}

    git add .

    if git diff --cached --quiet; then
        echo
        echo -e "${YELLOW}Tidak ada perubahan.${NC}"
        pause
        return
    fi

    git commit -m "$MSG" || return

    echo
    read -rp "Push sekarang? [Y/n]: " CONFIRM

    if [[ ! "$CONFIRM" =~ ^[Nn]$ ]]; then
        git push origin "$BRANCH"
    fi

    pause
}

pull_repo() {
    read -rp "Pull branch [$(current_branch)]: " BRANCH

    BRANCH=${BRANCH:-$(current_branch)}

    git pull origin "$BRANCH"

    pause
}

fetch_repo() {
    git fetch --all --prune

    pause
}

show_log() {
    git log \
    --oneline \
    --graph \
    --decorate \
    -20

    pause
}

switch_branch() {
    echo
    git branch -a

    echo
    read -rp "Nama branch: " BRANCH

    [ -z "$BRANCH" ] && return

    git checkout "$BRANCH"

    pause
}

status_repo() {
    git status

    pause
}

while true
do
    header

    echo "[1] Status"
    echo "[2] Commit"
    echo "[3] Push"
    echo "[4] Commit + Push"
    echo "[5] Pull"
    echo "[6] Fetch"
    echo "[7] Log Terakhir"
    echo "[8] Ganti Branch"
    echo "[0] Keluar"
    echo

    read -rp "Pilih menu: " CHOICE

    case $CHOICE in
        1) status_repo ;;
        2) commit_only ;;
        3) push_only ;;
        4) commit_push ;;
        5) pull_repo ;;
        6) fetch_repo ;;
        7) show_log ;;
        8) switch_branch ;;
        0)
            echo
            echo "Bye."
            exit 0
            ;;
        *)
            echo
            echo "Menu tidak valid."
            sleep 1
            ;;
    esac
done
