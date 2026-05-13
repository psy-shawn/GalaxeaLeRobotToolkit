# cd到脚本所在目录
cd "$(dirname "$0")"
source .env
# # python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/pick_3_bottles_and_place_them_into_trashbin
# python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup \
#     --fps 2
# # 1) 拷贝数据集
# cp -r /DATA/lerobot/straighten_papercup /DATA/tmp_dataset_for_label

# 2) 对拷贝的数据集跑标注 + 导出
cd /lpai/volumes/mind-vla-ali-sh-mix/pengshaoyang/code/GalaxeaLeRobotToolkit/label
python auto_annotate.py /lpai/volumes/base-3da-ali-sh-mix/zzz_sh/repos/crossembodydataset/data/straighten_papercup_test/straighten_papercup_H264 \
  --fps 2 \
  --export /lpai/volumes/base-3da-ali-sh-mix/zzz_sh/repos/crossembodydataset/data/straighten_papercup_test/straighten_papercup_H264/qwen_label_with_videopath.json