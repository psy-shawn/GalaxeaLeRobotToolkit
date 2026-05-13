# cd到脚本所在目录
cd "$(dirname "$0")"
source .env
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/stack-xx \
    --fps 2