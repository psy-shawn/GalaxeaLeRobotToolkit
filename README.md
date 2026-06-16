# GalaxeaLeRobotToolkit

Convert Galaxea ROS bag / MCAP data to LeRobot datasets, with helpers for
raw-data metadata generation, external camera alignment, and VLM-based dataset
annotation.

## Environment

The current setup reference is [setup.md](/Users/psy/workspace/GalaxeaLeRobotToolkit/setup.md).
A typical macOS/RoboStack setup is:

```bash
conda create -n galaxea python=3.10 zstandard -y
conda activate galaxea

conda config --env --add channels conda-forge
conda config --env --add channels robostack-staging
conda config --env --remove channels defaults

# Use mamba if available. conda also works, but is slower.
mamba install -y \
  ros-humble-desktop \
  ros-humble-rosbag2-storage-mcap \
  compilers cmake pkg-config make ninja colcon-common-extensions

pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  numpy PyYAML lark matplotlib netifaces typing_extensions \
  empy==3.3.4 h5py rerun-sdk nspektr loguru pyquaternion scipy

GIT_LFS_SKIP_SMUDGE=1 pip install git+https://github.com/OpenGalaxea/GalaxeaLeRobot.git
```

Build the local ROS message package before conversion:

```bash
colcon build --packages-select hdas_msg
source install/setup.zsh
# or, on Linux/bash:
# source install/setup.bash
```

If OpenMP conflicts appear on macOS, keep `KMP_DUPLICATE_LIB_OK=TRUE` as in
[run.sh](/Users/psy/workspace/GalaxeaLeRobotToolkit/run.sh).

## Data Layout

The tools assume one date directory contains multiple task directories, and
each task can contain `left`, `right`, or `interact` collection branches:

```text
<data-root>/
  20260203/
    <task_name>/
      left/
        <detail_or_order>/
          RB..._RAW/
            *.mcap
            metadata.yaml
          RB..._RAW.json
      right/
      interact/
```

The exact depth under `left/right/interact` can vary. The important rules are:

- each raw episode folder ends with `_RAW`;
- its sidecar JSON is next to the `_RAW` folder and named `<RAW_FOLDER>.json`;
- `metadata.yaml` stays inside the `_RAW` folder;
- failed episodes should be moved under a `fail/` directory if they should be
  skipped by metadata generation.

## Workflow

### 1. Collect Data

Create the task directory first, then collect multiple episodes for the task
under `left`, `right`, or `interact`.

Keep the robot raw data and external-camera data in corresponding relative
paths. The external camera aligner matches by relative path and timestamp.

### 2. Add Raw JSON Labels

Copy [utils/add_label.sh](/Users/psy/workspace/GalaxeaLeRobotToolkit/utils/add_label.sh)
to the concrete task branch directory, for example a `left`, `right`, or
`interact` directory, then edit the label values:

```bash
cp utils/add_label.sh /path/to/<date>/<task>/left/add_label.sh
cd /path/to/<date>/<task>/left
bash add_label.sh
```

`add_label.sh` calls [utils/add_label.py](/Users/psy/workspace/GalaxeaLeRobotToolkit/utils/add_label.py)
and updates the sidecar JSON files with task names and labels:

- `temporal_length`: `short`, `medium`, or `long`
- `arm_mode`: `single`, `dual`, or `interact`
- `object_type`: `rigidity`, `articulated`, `deformable`, or `fluid`
- `interactive_mode`: `environment`, `tool`, or `human`
- `fail`: non-empty means the action is unqualified

Check the script before running it. Its default values are examples, not a
universal label policy.

### 3. Align External Cameras

Run the batch aligner before conversion if external camera videos should be
included in the LeRobot dataset:

```bash
python utils/align_and_crop_cam.py \
  --data-root /path/to/robot/raw/data/20260203 \
  --cam-root /path/to/external/camera/data/20260203 \
  --top-cam-subdir cam_CP0E753000BN \
  --left-cam-subdir cam_CP0E753000AH \
  --ext-fps 15 \
  --max-time-diff 60
```

The script scans `--data-root` for `*_RAW.json`, finds the nearest external
camera directory under the matching relative path in `--cam-root`, and writes:

```text
<task-branch>/extra_cam/<RAW_FOLDER>/top/rgb_cropped.mp4
<task-branch>/extra_cam/<RAW_FOLDER>/top/depth_cropped.mp4
<task-branch>/extra_cam/<RAW_FOLDER>/left/rgb_cropped.mp4
<task-branch>/extra_cam/<RAW_FOLDER>/left/depth_cropped.mp4
```

[dataset_converter.py](/Users/psy/workspace/GalaxeaLeRobotToolkit/dataset_converter.py)
detects these files automatically and adds the external RGB/depth streams when
present.

### 4. Generate `raw_data_meta.json`

After the day's collection and raw JSON labeling are complete, generate metadata
from the date directory:

```bash
python utils/generate_raw_data_meta.py /path/to/robot/raw/data/20260203
```

This creates `raw_data_meta.json` in every directory that directly contains
`*_RAW` episode folders. The converter recursively finds these files and merges
their `rawDataList` entries.

### 5. Convert to LeRobot

Edit [run.sh](/Users/psy/workspace/GalaxeaLeRobotToolkit/run.sh):

```bash
dataset_name=<output_dataset_name>
input_dir=/path/to/robot/raw/data/20260203/<task_name>
output_dir=/path/to/galaxea/lerobot
robot_type=R1Lite  # R1Pro, R1, or R1Lite
```

Then run:

```bash
source install/setup.zsh
bash run.sh
```

Equivalent direct command:

```bash
python -m dataset_converter \
  --input_dir /path/to/robot/raw/data/20260203/<task_name> \
  --output_dir /path/to/galaxea/lerobot \
  --robot_type R1Lite \
  --dataset_name <output_dataset_name>
```

Useful environment variables used by `run.sh`:

- `SAVE_VIDEO=1`: save image observations as video streams
- `USE_H264=0`: use the default codec instead of H.264
- `USE_COMPRESSION=0`: keep original files
- `IS_COMPUTE_EPISODE_STATS_IMAGE=1`: compute image statistics
- `MAX_PROCESSES=4`: conversion worker count
- `USE_TRANSLATION=0`: keep original annotation text

To only generate `training_data_set_meta.json` without converting episodes:

```bash
python -m dataset_converter \
  --input_dir /path/to/task \
  --output_dir /path/to/galaxea/lerobot \
  --robot_type R1Lite \
  --dataset_name <output_dataset_name> \
  --only_generate_meta
```

The output dataset is written under:

```text
<output_dir>/<dataset_name>/
```

### 6. Run VLM Annotation

The converted dataset can be refined with the tools in
[label/](/Users/psy/workspace/GalaxeaLeRobotToolkit/label). Install label
dependencies first:

```bash
cd label
pip install -r requirements.txt
```

Configure the VLM endpoint through environment variables or `label/.env`:

```bash
export VLM_API_URL="http://..."
export VLM_API_TOKEN="..."
```

Test one episode before batch annotation:

```bash
python auto_annotate.py /path/to/galaxea/lerobot/<dataset_name> --single 0 --fps 2
```

Then annotate the full dataset:

```bash
python auto_annotate.py /path/to/galaxea/lerobot/<dataset_name> --fps 2
```

The label pipeline reads episode videos, calls the VLM, and updates:

- `episodes.jsonl`
- `training_data_set_meta.json`

It also creates backups before modifying dataset metadata. More details are in
[label/README_AUTO_ANNOTATE.md](/Users/psy/workspace/GalaxeaLeRobotToolkit/label/README_AUTO_ANNOTATE.md).

## Checks

Before conversion:

- sidecar JSON files exist beside every `_RAW` folder;
- `metadata.yaml` exists inside every `_RAW` folder;
- `raw_data_meta.json` exists under each branch that should be converted;
- external camera outputs exist under `extra_cam/<RAW_FOLDER>/...` if external
  views are expected.

After conversion:

- `<output_dir>/<dataset_name>/training_data_set_meta.json` exists;
- episode files and videos exist in the LeRobot dataset directory;
- external camera features are present only for episodes with aligned
  `rgb_cropped.mp4` / `depth_cropped.mp4`;
- after VLM annotation, inspect the updated `episodes.jsonl` and
  `training_data_set_meta.json` before training.
