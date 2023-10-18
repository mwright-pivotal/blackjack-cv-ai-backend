from openvino.runtime import Core, Model
from PIL import Image
from numpy import asarray
import numpy as np

def load_model(modelpath):
    core = Core()
    det_ov_model = core.read_model(modelpath)
    compiled_model = core.compile_model(det_ov_model, "CPU")
    return compiled_model

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

def test_answer():
    from PIL import Image
    from numpy import asarray
    # load the image
    image = Image.open('card.jpg')
    data = asarray(image)
    print(type(data))

    model = load_model("card-detect-0728_openvino_model/card-detect-0728.xml")

    image_tensor = image_to_tensor(data)
    result = model(image_tensor)
    boxes = result[model.output(0)]
    print(boxes)
    assert model