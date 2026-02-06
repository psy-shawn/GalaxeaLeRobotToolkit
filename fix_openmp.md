# 修复 macOS 上的 OpenMP 冲突问题

## 问题原因
在 macOS 上，多个 Python 包（如 numpy、opencv-python、torch 等）可能各自包含独立的 OpenMP 运行时库，导致冲突。

## 彻底解决方案

### 方案 1：使用 conda 管理依赖（推荐）

```bash
# 1. 重新创建 conda 环境
conda deactivate
conda env remove -n galaxea
conda create -n galaxea python=3.10 -y
conda activate galaxea

# 2. 先从 conda-forge 安装底层库（确保使用统一的 OpenMP）
conda install -c conda-forge numpy scipy opencv -y

# 3. 安装其他依赖
pip install loguru pyquaternion
pip install git+https://github.com/OpenGalaxea/GalaxeaLeRobot.git

# 4. 如果需要 PyTorch，也从 conda 安装
# conda install pytorch torchvision -c pytorch -y
```

### 方案 2：卸载并重装 OpenCV（使用无 OpenMP 版本）

```bash
# 1. 卸载当前的 opencv
pip uninstall opencv-python opencv-contrib-python opencv-python-headless -y

# 2. 安装 headless 版本（通常依赖更少）
pip install opencv-python-headless

# 3. 如果需要完整功能，使用以下命令
# pip install --no-binary opencv-python opencv-python
```

### 方案 3：使用 Homebrew 的 libomp（统一 OpenMP 库）

```bash
# 1. 安装 Homebrew 的 libomp
brew install libomp

# 2. 设置环境变量（添加到 ~/.zshrc）
echo 'export LDFLAGS="-L/opt/homebrew/opt/libomp/lib"' >> ~/.zshrc
echo 'export CPPFLAGS="-I/opt/homebrew/opt/libomp/include"' >> ~/.zshrc
source ~/.zshrc

# 3. 重装 numpy 和相关包
pip uninstall numpy scipy opencv-python -y
pip install --no-cache-dir --force-reinstall numpy scipy opencv-python
```

### 方案 4：检查并清理重复的库

```bash
# 查找所有 libomp 库
find $CONDA_PREFIX -name "libomp*.dylib" 2>/dev/null
find /opt/homebrew -name "libomp*.dylib" 2>/dev/null

# 如果发现多个，可能需要手动清理
```

## 验证修复

```bash
# 运行测试脚本
python -c "
import numpy as np
import cv2
print('NumPy version:', np.__version__)
print('OpenCV version:', cv2.__version__)
print('OpenMP test passed!')
"
```

## 临时解决方案（已在 run.sh 中配置）

如果以上方案都不适用，可以使用环境变量绕过：
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
```

**注意**：这只是临时方案，可能影响性能或产生不正确的结果。

## 推荐步骤

1. 先尝试**方案 1**（conda 管理）- 最彻底
2. 如果问题仍存在，尝试**方案 3**（统一使用 Homebrew 的 libomp）
3. 最后考虑临时方案

## 额外优化

如果使用多进程处理遇到问题，可以在 run.sh 中调整：
```bash
export MAX_PROCESSES=2  # 减少进程数
export OMP_NUM_THREADS=1  # 限制每个进程的线程数
```
