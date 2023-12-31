from pathlib import Path

# Fetch the notebook utils script from the openvino_notebooks repo
import urllib.request
from typing import Tuple, Dict
import cv2
import numpy as np
from PIL import Image
from ultralytics.utils.plotting import colors
from ultralytics.utils import ops
import sys, json
from notebook_utils import download_file, VideoPlayer
import torch
from argparse import ArgumentParser, SUPPRESS
import collections
from amqpconnection import AmqpConnection
from threading import Thread
from queue import Queue 
import time
import random
import pika, os
from ultralytics import YOLO
from openvino.runtime import Core, Model, serialize, Type, Layout
from openvino.preprocess import PrePostProcessor

global observed_classes
observed_classes = { }
_sentinel = object()

def plot_one_box(box:np.ndarray, img:np.ndarray, color:Tuple[int, int, int] = None, mask:np.ndarray = None, label:str = None, line_thickness:int = 5):
    """
    Helper function for drawing single bounding box on image
    Parameters:
        x (np.ndarray): bounding box coordinates in format [x1, y1, x2, y2]
        img (no.ndarray): input image
        color (Tuple[int, int, int], *optional*, None): color in BGR format for drawing box, if not specified will be selected randomly
        mask (np.ndarray, *optional*, None): instance segmentation mask polygon in format [N, 2], where N - number of points in contour, if not provided, only box will be drawn
        label (str, *optonal*, None): box label string, if not provided will not be provided as drowing result
        line_thickness (int, *optional*, 5): thickness for box drawing lines
    """
    # Plots one bounding box on image img
    tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1  # line/font thickness
    color = color or [random.randint(0, 255) for _ in range(3)]
    c1, c2 = (int(box[0]), int(box[1])), (int(box[2]), int(box[3]))
    cv2.rectangle(img, c1, c2, color, thickness=tl, lineType=cv2.LINE_AA)
    if label:
        tf = max(tl - 1, 1)  # font thickness
        t_size = cv2.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        cv2.rectangle(img, c1, c2, color, -1, cv2.LINE_AA)  # filled
        cv2.putText(img, label, (c1[0], c1[1] - 2), 0, tl / 3, [225, 255, 255], thickness=tf, lineType=cv2.LINE_AA)
    if mask is not None:
        image_with_mask = img.copy()
        mask
        cv2.fillPoly(image_with_mask, pts=[mask.astype(int)], color=color)
        img = cv2.addWeighted(img, 0.5, image_with_mask, 0.5, 1)
    return img


def draw_results(results:Dict, source_image:np.ndarray, label_map:Dict):
    """
    Helper function for drawing bounding boxes on image
    Parameters:
        image_res (np.ndarray): detection predictions in format [x1, y1, x2, y2, score, label_id]
        source_image (np.ndarray): input image for drawing
        label_map; (Dict[int, str]): label_id to class name mapping
    Returns:
        
    """
    boxes = results["det"]
    masks = results.get("segment")
    h, w = source_image.shape[:2]
    for idx, (*xyxy, conf, lbl) in enumerate(boxes):
        label = f'{label_map[int(lbl)]} {conf:.2f}'
        mask = masks[idx] if masks is not None else None
        source_image = plot_one_box(xyxy, source_image, mask=mask, label=label, color=colors(int(lbl)), line_thickness=1)
    return source_image

def build_args():
    parser = ArgumentParser(add_help=False)
    args = parser.add_argument_group('Options')
    args.add_argument('-d', '--device', default='CPU', type=str,
                      help='Optional. Specify the target device to infer on; CPU, GPU, HDDL or MYRIAD is '
                           'acceptable. The demo will look for a suitable plugin for device specified. '
                           'Default value is CPU.')
    args.add_argument('-i', '--input', required=True,
                      help='Required. An input to process. The input must be a single image, '
                           'a folder of images, video file or camera id.')
    args.add_argument('-m', '--model', required=True,
                      help='Required. OpenVino Model filename ')
    args.add_argument('--publish_sysout', help="Optional. Don't show output.", action='store_true')
    args.add_argument('--publish_rmq', help="Optional. Don't publish to rmq stream", action='store_true')
    args.add_argument('-v', '--rmq_vhost', default='/edge-vhost', help="Optional. RMQ VHost", type=str)
    return parser

def letterbox(img: np.ndarray, new_shape:Tuple[int, int] = (640, 640), color:Tuple[int, int, int] = (114, 114, 114), auto:bool = False, scale_fill:bool = False, scaleup:bool = False, stride:int = 32):
    """
    Resize image and padding for detection. Takes image as input, 
    resizes image to fit into new shape with saving original aspect ratio and pads it to meet stride-multiple constraints
    
    Parameters:
      img (np.ndarray): image for preprocessing
      new_shape (Tuple(int, int)): image size after preprocessing in format [height, width]
      color (Tuple(int, int, int)): color for filling padded area
      auto (bool): use dynamic input size, only padding for stride constrins applied
      scale_fill (bool): scale image to fill new_shape
      scaleup (bool): allow scale image if it is lower then desired input size, can affect model accuracy
      stride (int): input padding stride
    Returns:
      img (np.ndarray): image after preprocessing
      ratio (Tuple(float, float)): hight and width scaling ratio
      padding_size (Tuple(int, int)): height and width padding size
    
    
    """
    # Resize and pad image while meeting stride-multiple constraints
    shape = img.shape[:2]  # current shape [height, width]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # Scale ratio (new / old)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:  # only scale down, do not scale up (for better test mAP)
        r = min(r, 1.0)

    # Compute padding
    ratio = r, r  # width, height ratios
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    if auto:  # minimum rectangle
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)  # wh padding
    elif scale_fill:  # stretch
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]  # width, height ratios

    dw /= 2  # divide padding into 2 sides
    dh /= 2

    if shape[::-1] != new_unpad:  # resize
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)  # add border
    return img, ratio, (dw, dh)


def preprocess_image(img0: np.ndarray):
    """
    Preprocess image according to YOLOv8 input requirements. 
    Takes image in np.array format, resizes it to specific size using letterbox resize and changes data layout from HWC to CHW.
    
    Parameters:
      img0 (np.ndarray): image for preprocessing
    Returns:
      img (np.ndarray): image after preprocessing
    """
    # resize
    img = letterbox(img0)[0]
    
    # Convert HWC to CHW
    img = img.transpose(2, 0, 1)
    img = np.ascontiguousarray(img)
    return img


def image_to_tensor(image:np.ndarray):
    """
    Preprocess image according to YOLOv8 input requirements. 
    Takes image in np.array format, resizes it to specific size using letterbox resize and changes data layout from HWC to CHW.
    
    Parameters:
      img (np.ndarray): image for preprocessing
    Returns:
      input_tensor (np.ndarray): input tensor in NCHW format with float32 values in [0, 1] range 
    """
    input_tensor = image.astype(np.float32)  # uint8 to fp32
    input_tensor /= 255.0  # 0 - 255 to 0.0 - 1.0
    
    # add batch dimension
    if input_tensor.ndim == 3:
        input_tensor = np.expand_dims(input_tensor, 0)
    return input_tensor

def postprocess(
    pred_boxes:np.ndarray, 
    input_hw:Tuple[int, int], 
    orig_img:np.ndarray, 
    min_conf_threshold:float = 0.25, 
    nms_iou_threshold:float = 0.7, 
    agnosting_nms:bool = False, 
    max_detections:int = 300,
    pred_masks:np.ndarray = None,
    retina_mask:bool = False
):
    """
    YOLOv8 model postprocessing function. Applied non maximum supression algorithm to detections and rescale boxes to original image size
    Parameters:
        pred_boxes (np.ndarray): model output prediction boxes
        input_hw (np.ndarray): preprocessed image
        orig_image (np.ndarray): image before preprocessing
        min_conf_threshold (float, *optional*, 0.25): minimal accepted confidence for object filtering
        nms_iou_threshold (float, *optional*, 0.45): minimal overlap score for removing objects duplicates in NMS
        agnostic_nms (bool, *optiona*, False): apply class agnostinc NMS approach or not
        max_detections (int, *optional*, 300):  maximum detections after NMS
        pred_masks (np.ndarray, *optional*, None): model ooutput prediction masks, if not provided only boxes will be postprocessed
        retina_mask (bool, *optional*, False): retina mask postprocessing instead of native decoding
    Returns:
       pred (List[Dict[str, np.ndarray]]): list of dictionary with det - detected boxes in format [x1, y1, x2, y2, score, label] and segment - segmentation polygons for each element in batch
    """
    nms_kwargs = {"agnostic": agnosting_nms, "max_det":max_detections}
    #if pred_masks is not None:
    #    nms_kwargs["nm"] = 32
    #print(torch.from_numpy(pred_boxes).shape[1] - 52 - 4)
    preds = ops.non_max_suppression(
        torch.from_numpy(pred_boxes),
        min_conf_threshold,
        nms_iou_threshold,
        nc=52,
        **nms_kwargs
    )
    results = []
    proto = torch.from_numpy(pred_masks) if pred_masks is not None else None

    for i, pred in enumerate(preds):
        shape = orig_img[i].shape if isinstance(orig_img, list) else orig_img.shape
        if not len(pred):
            results.append({"det": [], "segment": []})
            continue
        if proto is None:
            pred[:, :4] = ops.scale_boxes(input_hw, pred[:, :4], shape).round()
            results.append({"det": pred})
            continue
        if retina_mask:
            pred[:, :4] = ops.scale_boxes(input_hw, pred[:, :4], shape).round()
            masks = ops.process_mask_native(proto[i], pred[:, 6:], pred[:, :4], shape[:2])  # HWC
            segments = [ops.scale_coords(input_hw, x, shape, normalize=False) for x in ops.masks2segments(masks)]
        else:
            masks = ops.process_mask(proto[i], pred[:, 6:], pred[:, :4], input_hw, upsample=True)
            pred[:, :4] = ops.scale_boxes(input_hw, pred[:, :4], shape).round()
            segments = [ops.scale_coords(input_hw, x, shape, normalize=False) for x in ops.masks2segments(masks)]
        results.append({"det": pred[:, :6].numpy(), "segment": segments})
    return results

def detect(image:np.ndarray, model:Model):
    """
    OpenVINO YOLOv8 model inference function. Preprocess image, runs model inference and postprocess results using NMS.
    Parameters:
        image (np.ndarray): input image.
        model (Model): OpenVINO compiled model.
    Returns:
        detections (np.ndarray): detected boxes in format [x1, y1, x2, y2, score, label]
    """
    num_outputs = len(model.outputs)
    preprocessed_image = preprocess_image(image)
    input_tensor = image_to_tensor(preprocessed_image)
    result = model(input_tensor)
    boxes = result[model.output(0)]
    #print(model.output(0))
    masks = None
    if num_outputs > 1:
        masks = result[model.output(1)]
        #print(model.output(1))
    input_hw = input_tensor.shape[2:]
    detections = postprocess(pred_boxes=boxes, input_hw=input_hw, orig_img=image, pred_masks=masks)
    return detections

def detect_without_preprocess(image:np.ndarray, model:Model):
    """
    OpenVINO YOLOv8 model with integrated preprocessing inference function. Preprocess image, runs model inference and postprocess results using NMS.
    Parameters:
        image (np.ndarray): input image.
        model (Model): OpenVINO compiled model.
    Returns:
        detections (np.ndarray): detected boxes in format [x1, y1, x2, y2, score, label]
    """
    output_layer = model.output(0)
    img = letterbox(image)[0]
    input_tensor = np.expand_dims(img, 0)
    input_hw = img.shape[:2]
    result = model(input_tensor)[output_layer]
    detections = postprocess(result, input_hw, image)
    return detections

def sysout_results(results:Dict, source_image:np.ndarray, label_map:Dict, msg):
    """
    Helper function for drawing bounding boxes on image
    Parameters:
        image_res (np.ndarray): detection predictions in format [x1, y1, x2, y2, score, label_id]
        source_image (np.ndarray): input image for drawing
        label_map; (Dict[int, str]): label_id to class name mapping
    Returns:
        
    """
    boxes = results["det"]
    masks = results.get("segment")
    h, w = source_image.shape[:2]

    for idxPred, det in enumerate(boxes):
        for idx, (*xyxy, conf, lbl) in reversed(det):
            print('Label nbr: ' + str(lbl))
            label = f'{label_map[int(lbl)]} {conf:.2f}'
            object_class = label_map[int(lbl)]
            messageBody = '{"class": "' + label_map[int(lbl)] + '", "score": "' + str(conf.item()) + '", "x1": "' + str(xyxy[0].item()) \
                    + '", "y1": "' + str(xyxy[1].item()) + '", "msg": "' + msg + '" }'
            print(messageBody)
        
    return

def setup_rabbit():
    rabbitmq_hostname = os.environ.get(
        'AMQP_HOSTNAME', 'localhost'
    )
    rabbitmq_port = os.environ.get(
        'AMQP_PORT', '5672'
    )
    rabbitmq_user = os.environ.get(
        'AMQP_USER', 'user'
    )
    rabbitmq_password = os.environ.get(
        'AMQP_PASSWORD', 'guest'
    )
    rabbitmq_vhost = os.environ.get(
        'RMQ_VHOST', '/'
    )
    rabbitmq_exchange = os.environ.get(
        'RMQ_EXCHANGE', ''
    )
    mq = AmqpConnection(hostname=rabbitmq_hostname,port=rabbitmq_port,username=rabbitmq_user,
                        password=rabbitmq_password,vhost=rabbitmq_vhost,exchange=rabbitmq_exchange)
    mq.connect()
    mq.setup_queues()
    return mq

# A thread that produces data 
def sender_thread(mq, in_q): 
    while True: 
        data = in_q.get() 
        if data == _sentinel:
            break
        #mq.do_async(mq.publish, payload=data)
        try:
            mq.publish(payload=data)
        except (pika.exceptions.StreamLostError, pika.exceptions.AMQPHeartbeatTimeout):
            print("Network dropped, reconnecting...")
            mq = setup_rabbit()
            print("Reconnected")

#def stream_results(rmqChannel, results:Dict, source_image:np.ndarray, label_map:Dict):
#def stream_results(mq, results:Dict, source_image:np.ndarray, label_map:Dict):
def stream_results(messageQueue, results:Dict, source_image:np.ndarray, label_map:Dict, inf_time, fps):
    """
    Helper function for drawing bounding boxes on image
    Parameters:
        image_res (np.ndarray): detection predictions in format [x1, y1, x2, y2, score, label_id]
        source_image (np.ndarray): input image for drawing
        label_map; (Dict[int, str]): label_id to class name mapping
    Returns:
        
    """
    boxes = results["det"]
    masks = results.get("segment")
    h, w = source_image.shape[:2]
    global observed_classes
    
    if len(boxes) == 0:
        if not 'NONE' in observed_classes.keys():
            messageBody = '{"class": "NONE", "score": "1", "x1": "0", "y1": "0", "inf_time": "' + str(inf_time) + '", "fps": "' + str(fps) + '" }'
            #reset the classes observed previously...
            print('previous inferencing diagnostics - ' + str(observed_classes))
            observed_classes = { 'NONE': 0 }
            # rmqChannel.basic_publish(
            #     exchange='',
            #     routing_key='inferencing_stream',
            #     body=messageBody
            # )
            #mq.do_async(mq.publish, payload=messageBody)
            #mq.publish(payload=messageBody)
            messageQueue.put(messageBody)
            return
        else:
            return
    
    if 'NONE' in observed_classes.keys():
        print('deleting NONE from dict')
        del observed_classes['NONE']
    
    for idx, (*xyxy, conf, lbl) in enumerate(boxes):
        label = f'{label_map[int(lbl)]} {conf:.2f}'
        object_class = label_map[int(lbl)]
        #if this class was detected previously record the confidence if higher than before, don't publish to RabbitMQ
        if not (object_class in observed_classes.keys() and conf.item() < float(observed_classes[object_class])):
            messageBody = '{"class": "' + label_map[int(lbl)] + '", "score": "' + str(conf.item()) + '", "x1": "' + str(xyxy[0].item()) \
                + '", "y1": "' + str(xyxy[1].item()) + '", "inf_time": "' + str(inf_time) + '", "fps": "' + str(fps) + '" }'
            # rmqChannel.basic_publish(
            #     exchange='',
            #     routing_key='inferencing_stream',
            #     body=messageBody
            # )
            #mq.do_async(mq.publish, payload=messageBody)
            #mq.publish(payload=messageBody)
            messageQueue.put(messageBody)
        
            observed_classes[object_class] = conf.item()
        
    return

# Main processing function to run object detection.
def run_object_detection(flip=False, use_popup=False, skip_first_frames=0):
    player = None
    args = build_args().parse_args()
    publishSysout = args.publish_sysout
    publishRMQ = args.publish_rmq
    robotDance = False
    #rmqChannel = setup_rabbit() if publishRMQ else None
    mq = setup_rabbit() if publishRMQ else None
    mc = None
    
    device = args.device
    source = args.input

    DET_MODEL_NAME = args.model
    #SEG_MODEL_NAME = "card-segment-08823"

    #det_model = YOLO(f'./models/cards-yolov5.pt')
    classesJson = '{"0": "10C", "1": "10D", "2": "10H", "3": "10S", "4": "2C", "5": "2D", "6": "2H", "7": "2S", "8": "3C", "9": "3D", "10": "3H", "11": "3S", "12": "4C", "13": "4D", "14": "4H", "15": "4S", "16": "5C", "17": "5D", "18": "5H", "19": "5S", "20": "6C", "21": "6D", "22": "6H", "23": "6S", "24": "7C", "25": "7D", "26": "7H", "27": "7S", "28": "8C", "29": "8D", "30": "8H", "31": "8S", "32": "9C", "33": "9D", "34": "9H", "35": "9S", "36": "AC", "37": "AD", "38": "AH", "39": "AS", "40": "JC", "41": "JD", "42": "JH", "43": "JS", "44": "KC", "45": "KD", "46": "KH", "47": "KS", "48": "QC", "49": "QD", "50": "QH", "51": "QS"}'
    
    #label_map = det_model.model.names
    label_map = json.loads(classesJson)
    print(label_map)

    from openvino.runtime import Core, Model

    core = Core()
    det_model_path = f"{DET_MODEL_NAME}.xml"

    #seg_model_path = models_dir / f"{SEG_MODEL_NAME}_openvino_model/{SEG_MODEL_NAME}.xml"

    det_ov_model = core.read_model(det_model_path)
    #seg_ov_model = core.read_model(seg_model_path)
    #det_ov_model = core.read_model('./nvidia_results/best.xml')
    if device != "CPU":
        det_ov_model.reshape({0: [1, 3, 640, 640]})
        available_devices = core.available_devices
        print(available_devices)
        
    ppp = PrePostProcessor(det_ov_model)
    ppp.input(0).tensor().set_shape([1, 640, 640, 3]).set_element_type(Type.u8).set_layout(Layout('NHWC'))
    ppp.input(0).preprocess().convert_element_type(Type.f32).convert_layout(Layout('NCHW')).scale([255., 255., 255.])
    print(ppp)

    quantized_model_with_preprocess = ppp.build()
    #serialize(quantized_model_with_preprocess, str(f"{DET_MODEL_NAME}_with_preprocess.xml"))
    compiled_model = core.compile_model(quantized_model_with_preprocess, device)

    #start seperate thread for sending to RabbitMQ (pika is not threadsafe so we wrap in a class)
    q = Queue() 
    t1 = Thread(target = sender_thread, args =(mq, q))
    t1.start()

    try:
        # Create a video player to play with target fps.
        player = VideoPlayer(
            source=source, flip=flip, fps=1, skip_first_frames=skip_first_frames, scale=1.0
        )
        # Start capturing.
        player.start()
        if use_popup:
            title = "Press ESC to Exit"
            cv2.namedWindow(
                winname=title, flags=cv2.WINDOW_GUI_NORMAL | cv2.WINDOW_AUTOSIZE
            )

        processing_times = collections.deque()
        prev_card_code = ''
        
        while True:
            sys.stdout.flush()
            # Grab the frame.
            frame = player.next()
            if frame is None:
                print("Source ended")
                break
            # If the frame is larger than full HD, reduce size to improve the performance.
            scale = 1280 / max(frame.shape)
            if scale < 1:
                frame = cv2.resize(
                    src=frame,
                    dsize=None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_AREA,
                )
            # Get the results.
            input_image = np.array(frame)
           
            start_time = time.time()
            # model expects RGB image, while video capturing in BGR
            # detections = detect(input_image[:, :, ::-1], compiled_model)[0]
            detections = detect_without_preprocess(input_image, compiled_model)[0]
            stop_time = time.time()
            
            processing_times.append(stop_time - start_time)
            # Use processing times from last 200 frames.
            if len(processing_times) > 200:
                processing_times.popleft()
            processing_time = np.mean(processing_times) * 1000
            fps = 1000 / processing_time
            timings_text=f"Inference time: {processing_time:.1f}ms ({fps:.1f} FPS)"

            if publishRMQ:
                stream_results(q, detections, input_image, label_map, processing_time, fps)
                
            if publishSysout:
                sysout_results(detections, input_image, label_map, timings_text)
    
    # ctrl-c
    except KeyboardInterrupt:
        print("Interrupted")
        q.put(_sentinel)
    # any different error
    except RuntimeError as e:
        print(e)
    finally:
        if player is not None:
            # Stop capturing.
            player.stop()
        if mq is not None:
            mq.connection.close()
            
def main():
    run_object_detection(flip=False, use_popup=False)
    
if __name__ == '__main__':
    sys.exit(main() or 0)
