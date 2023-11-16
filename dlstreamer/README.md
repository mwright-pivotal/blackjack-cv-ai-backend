*** Important ***
If you want to use your own YOLOv5 based model, be sure to examine the layers of the resulting model to determine the proper params when converting to Openvino IR.  More details here: https://dlstreamer.github.io/dev_guide/yolov5_model_preparation.html#model-pre-post-processing

From within a dlstreamer container, convert your model using "mo" util from Intel

1. Run docker container (remove device reference if you don't have Intel graphics)
`docker run -it --device /dev/dri --group-add=$(stat -c "%g" /dev/dri/render*) --rm -v /home/mwright/projects/blackjack:/home/dlstreamer/blackjack -e XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR} -e CAM_USER=root -e CAM_PASSWORD=camera-password?? intel/dlstreamer:devel`

2. Convert your yolov5 model then edit dlstreamer.sh to reference it
`mo  --input_model cards-yolov5.onnx --model_name yolov5s --scale 255 --reverse_input_channels --output /model.24/m.0/Conv,/model.24/m.1/Conv,/model.24/m.2/Conv --output_dir .`

3. Run dlstreamer.sh
