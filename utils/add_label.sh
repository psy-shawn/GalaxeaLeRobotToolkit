# 数据集目录结构：
# /home/psy/galaxea/r1lite/{date}/{task_category}/{detail_task}/{arm}
# 可通过传参指定目录，默认使用脚本所在目录
DATA_DIR="$(cd "$(dirname "$0")" && pwd)"

ARM_NAME="$(basename "$DATA_DIR")"
if [ "$ARM_NAME" == "right" ] || [ "$ARM_NAME" == "left" ]; then
  ARM_NAME="single"
fi
DETAIL_TASK="$(basename "$(dirname "$DATA_DIR")")"
TASK_CATEGORY="$(basename "$(dirname "$(dirname "$DATA_DIR")")")"

TEMPORAL=short # options: short, long
OBJ=deformable # options: rigid, deformable
INTER=environment # options: object, environment
TOWNER="${TASK_CATEGORY}_${OBJ}"
# 根据目录结构，添加相应的名称标签
python /Users/psy/workspace/GalaxeaLeRobotToolkit/utils/add_label.py \
--pname "$TASK_CATEGORY" \
--tname "$DETAIL_TASK" \
--towner "$TOWNER" \
--opname gripper \
--dir "$DATA_DIR" \
--temporal "$TEMPORAL" \
--arm "$ARM_NAME" \
--obj "$OBJ" \
--inter "$INTER"