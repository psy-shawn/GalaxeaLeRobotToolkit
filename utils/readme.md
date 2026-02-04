# 录制所需
1. 下载pyorbbecsdk
```bash
git clone https://github.com/orbbec/pyorbbecsdk.git
```

2. 复制到指定位置
```bash
#将lib下的依赖放到pyorbbecsdk/sdk/lib/macOS
/Users/hsong/repos/pyorbbecsdk/sdk/lib/macOS
├── libOrbbecSDK.2.7.2.dylib
├── libOrbbecSDK.2.dylib -> libOrbbecSDK.2.7.2.dylib
└── libOrbbecSDK.dylib -> libOrbbecSDK.2.7.2.dylib
```

3. 编译
参考https://pypi.org/project/pyorbbecsdk/,进行编译


> 文件的使用在其中注释，或者查看feishu遥操采集流程https://li.feishu.cn/wiki/WvZ3wxnLxiviBMk3rtTc4ZHWnBc
# 数据处理步骤

1. 数据传输
    1. 从机器人上、和从录制了外部相机视角的mac电脑上 上传数据 --> lpai服务器（目录严格对应）
    2. 从机器人上copy原始数据 --> 本地mac进行转换后（转换时顺便把meta.yaml也复制到转换后的目录里） --> lpai
    3. 外部相机的目录会有提前，撰写一个脚本，按照相近的时间信息匹配mac上传的外部相机数据和转换后数据目录对应关系，进行**合并**
2. 后处理
    1. 裁剪视频对齐
    ```bash
    # 输入外部相机的目录+1个原始的metayaml
    DATA_ROOT="/home/r1lite/OpenGalaxea/LerobotGalaxeaDataset/for_calibration/extra_camera/....RAW" # 希望可以输入一个目录，进行所有后处理。

    CAMERA_DIR="/home/r1lite/OpenGalaxea/LerobotGalaxeaDataset/for_calibration/extra_camera/20260130_203427"
    METADATA_YAML="/home/r1lite/GalaxeaDataset/20260130/RB251106042_20260130203432633_RAW/metadata.yaml"
    # 俯视相机
    python3 /home/r1lite/OpenGalaxea/extra_camera/scripts/align_and_crop_cam.py \
    --metadata "$METADATA_YAML" \
    --csv "$CAMERA_DIR/cam_CP0E753000BN/timestamps.csv" \
    --rgb "$CAMERA_DIR/cam_CP0E753000BN/rgb_video.mp4" \
    --depth_is_video \
    --depth "$CAMERA_DIR/cam_CP0E753000BN/depth_video.mp4" \
    --out_video "$CAMERA_DIR/cam_CP0E753000BN/aligned_rgb.mp4" \
    --out_depth "$CAMERA_DIR/cam_CP0E753000BN/aligned_depth.mp4" \
    --ext_fps 15
    
    # 侧视相机
    python3 /home/r1lite/OpenGalaxea/extra_camera/scripts/align_and_crop_cam.py \
    --metadata "$METADATA_YAML" \
    --csv "$CAMERA_DIR/cam_CP0E753000AH/timestamps.csv" \
    --rgb "$CAMERA_DIR/cam_CP0E753000AH/rgb_video.mp4" \
    --depth_is_video \
    --depth "$CAMERA_DIR/cam_CP0E753000AH/depth_video.mp4" \
    --out_video "$CAMERA_DIR/cam_CP0E753000AH/rgb_cropped.mp4" \
    --out_depth "$CAMERA_DIR/cam_CP0E753000AH/depth_cropped" \
    --ext_fps 15
    ```
    2. 得到内部相机camera_poses: 从一个parquet文件中得到2个json文件
    ```bash
    # 输入转换后的parquet文件，输出json*2，第一个相对于躯干关节，第二个相对于底座
    python3 process_camera_poses.py --input episode_000000.parquet --output with_cameraposes_torso.json --frame torso_link3 
    # --visualize

    python3 process_camera_poses.py --input episode_000000.parquet --output with_cameraposes_base.json --frame base_link 
    # --visualize

    得到后放到对应目录
    # 可视化相机轨迹
    python3 visualize_trajectory.py output_torso.json --frame torso_link3 --animate
    ```

    3. 外部相机的标定：流程稍微复杂，就是把两个mp4抽帧放到对应目录运行标定程序，其实下个软件也可以，详见《摇操采集相关流程》https://li.feishu.cn/wiki/WvZ3wxnLxiviBMk3rtTc4ZHWnBc

    4. 质检
    ```bash
    # 输入路径，跳出网页，标注得到json文件，想办法将json文件追加到对应文件中完成标注
    ```

    5.训练集划分

    6.模型微调验证