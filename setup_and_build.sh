#!/bin/bash
# One-time setup of a clean workspace on the Desktop, then Muse Code builds Tasks 1-7.
set -e
SPECS="$(cd "$(dirname "$0")" && pwd)"
WS="$HOME/Desktop/formsaathi-muse"
if [ ! -d "$WS/.git" ]; then
  git clone -q https://github.com/nanduoop/form-saathi.git "$WS"
  cd "$WS"
  git checkout -q --orphan muse-build
  git rm -rq .
  git checkout -q 9190e6e -- LICENSE .gitignore
  printf '\n# FormSaathi\napp/state/\nsamples/answer_*.m4a\n._*\n.DS_Store\n' >> .gitignore
  printf '# FormSaathi\n\nVoice-first agent that fills Indian government forms from document photos and proves every field. Built with Muse Code and Meta models during the Meta Global AI Developer Hackathon.\n' > README.md
  git add -A && git commit -qm "Start FormSaathi (Muse Code build)"
fi
cd "$WS"
[ -f .env ] || cp "$HOME/snap-to-claim/.env" .env      # copied, never printed
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r "$SPECS/requirements.txt"
for n in ${TASKS:-1 2 3 4 5 6 7}; do "$SPECS/run_task.sh" "$n" || { echo "Task $n failed - stopping"; exit 1; }; done
echo "ALL TASKS DONE"
