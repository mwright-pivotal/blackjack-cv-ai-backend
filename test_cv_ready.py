from openvino.runtime import Core, Model
from PIL import Image
from numpy import asarray

def load_model(modelpath):
    core = Core()
    det_ov_model = core.read_model(modelpath)
    compiled_model = core.compile_model(det_ov_model, "CPU")
    return compiled_model

def test_answer():
    from PIL import Image
    from numpy import asarray
    # load the image
    image = Image.open('card.jpg')
    data = asarray(image)
    print(type(data))

    model = load_model("card-detect-0728_openvino_model/card-detect-0728.xml")

    assert model