# Source this before running scripts under sw/ (NOT executed — must be sourced):
#
#     source env.sh                 # or:  . env.sh
#     python tests/perip_test.py
#
# Adds sw/ to PYTHONPATH so `from lib...` / `from tools...` resolve in plain
# script mode (`python tests/perip_test.py`) from any cwd, using this server's
# own Python + packages. Self-locating: the same file works on every server /
# mount path with no edits.

# Directory this file lives in = the sw/ root (works when sourced from any cwd).
_sw_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prepend sw/ to PYTHONPATH, but only once (safe to re-source).
case ":${PYTHONPATH:-}:" in
  *":$_sw_dir:"*) ;;                                       # already present
  *) export PYTHONPATH="$_sw_dir${PYTHONPATH:+:$PYTHONPATH}" ;;
esac

echo "sw/ on PYTHONPATH -> $_sw_dir"
unset _sw_dir
