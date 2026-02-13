# cd到脚本所在目录
cd "$(dirname "$0")"
source .env
# python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/pick_3_bottles_and_place_them_into_trashbin
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup \
    --fps 2