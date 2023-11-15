#!/bin/bash
# chmod +x ./person_bike_vehicle_detection_v2.sh
#while getopts i:a:f: flag
while getopts :i:I: flag; do
    case "${flag}" in
        i) LOCATION=${OPTARG};;
	I) LOCATION=${OPTARG};;
#	h) echo "TEST" ;; TODO Passing help
    esac
done

##################################################################################
##################################################################################
source /opt/intel/openvino_2021/bin/setupvars.sh 
##################################################################################
echo "##############################################################################"
echo "# Path to Me --------------->  ${PWD}     "
echo "# Parent Path -------------->  ${0%/*}  "
echo "# My Name ------------------>  ${0##*/} "

echo "##############################################################################"
echo "#                       #           #               ^                        #"
echo "##                    #   #       #   #           ^   ^                     ##"
echo "###                 #       # @ #       #                                  ###"
echo "####              #           #           #                               ####"
###################################################################################
#LOCATION=traffic_cam_intel.mp4
#LOCATION=../cards-sample.m4v
#LOCATION=rtsp://${CAM_USER}:${CAM_PASSWORD}@192.168.0.33/axis-media/media.amp?videocodec=h264
LOCATION=rtsp://${CAM_USER}:${CAM_PASSWORD}@192.168.0.33/axis-media/media.amp
if [[ $LOCATION == "/dev/video"* ]]; then
  SOURCE_ELEMENT="v4l2src device=${LOCATION}"
elif [[ $LOCATION == *"://"* ]]; then
  SOURCE_ELEMENT="urisourcebin buffer-size=4096 uri=${LOCATION}"
else
  SOURCE_ELEMENT="filesrc location=${LOCATION}"
fi

###################################################################################
DETECTION_MODEL=../models/cards-yolov5-ov.xml
#DETECTION_MODEL=model_intel/person-vehicle-bike-detection-crossroad-0078/FP32/person-vehicle-bike-detection-crossroad-0078.xml
#DETECTION_MODEL_PROC=model_proc/person-vehicle-bike-detection-crossroad-0078.json
DETECTION_MODEL_PROC=blackjack-model-proc-v2.json
###################################################################################
TRACK="queue2 ! gvatrack tracking-type=short-term-imageless ! queue2"
###################################################################################
DEVICE=GPU
THRESHOLD=0.75
INFRENCE_INTERVAL=1
###################################################################################
#SINK_ELEMENT="videoconvert ! gvafpscounter ! fpsdisplaysink video-sink=xvimagesink sync=false"
#SINK_ELEMENT="videoconvert ! gvafpscounter ! fakesink"
#SINK_ELEMENT="videoconvert ! gvafpscounter ! gvametaconvert format=dump-detection"
SINK_ELEMENT="gvametaconvert ! gvametapublish file-format=json-lines file-path=output.json ! fakesink async=false "
#SINK_ELEMENT="videoconvert ! gvafpscounter ! fpsdisplaysink video-sink=autovideosink sync=false"
###################################################################################
#PIPELINE="gst-launch-1.0 -vvv filesrc location=${LOCATION} ! decodebin ! gvadetect model=${DETECTION_MODEL} model-proc=${DETECTION_MODEL_PROC} device=${DEVICE} threshold=${THRESHOLD} inference-interval=${INFRENCE_INTERVAL} nireq=4 ! ${TRACK} ! gvawatermark ! ${SINK_ELEMENT}"
PIPELINE="gst-launch-1.0 ${SOURCE_ELEMENT} ! decodebin ! gvadetect model=${DETECTION_MODEL} model_proc=${DETECTION_MODEL_PROC} device=${DEVICE} ! queue ! ${SINK_ELEMENT}"
#PIPELINE="gst-launch-1.0 -vvv ${SOURCE_ELEMENT} ! decodebin ! gvadetect model=${DETECTION_MODEL} model_proc=${DETECTION_MODEL_PROC} device=${DEVICE} ! gvaclassify model=${DETECTION_MODEL} model_proc=${DETECTION_MODEL_PROC} device=${DEVICE} ! queue ! ${SINK_ELEMENT}"
###################################################################################
echo "##############################################################################"
echo "PLAYING CARD DETECTION"
echo "VIDEO NAME :::" ${LOCATION}
echo "MODEL NAME :::" ${DETECTION_MODEL}
echo "DEVICE :::" ${DEVICE}
echo "THRESHOLD :::" ${THRESHOLD}
echo "##############################################################################"
echo "GST PIPELINE::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::"
echo ${PIPELINE}
echo "##############################################################################"
seconds=2; date1=$((`date +%s` + $seconds)); 
while [ "$date1" -ge `date +%s` ]; do 
  echo -ne "PIPELINE ROLLS IN ::----------->>>$(date -u --date @$(($date1 - `date +%s` )) +%H:%M:%S)\r"; 
done
${PIPELINE}
echo "##############################################################################"

