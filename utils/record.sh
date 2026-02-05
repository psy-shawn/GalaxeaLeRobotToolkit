cd ~/workspace/pyorbbecsdk
sudo killall VDCAssistant
export PYTHONPATH=$PYTHONPATH:$(pwd)/install/lib/
export DYLD_LIBRARY_PATH=/Users/psy/workspace/pyorbbecsdk/install/lib:/Users/psy/workspace/pyorbbecsdk/sdk/lib/macOS:$DYLD_LIBRARY_PATH
python /Users/psy/workspace/GalaxeaLeRobotToolkit/utils/record.py