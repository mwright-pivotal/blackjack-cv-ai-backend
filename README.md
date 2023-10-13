# blackjack-cv-ai-backend
Uses object detection model trained with playing cards to observe from camera during blackjack game

build this Python app using the cloud native buildpack cli `pack` and builder generated from https://github.com/mwright-pivotal/openvino-buildpack

```
pack build blackjack-backend --builder cv-builder:1.0 --env BP_CPYTHON_VERSION=3.9.*
```

then run resulting container:

```
docker run -e VIDEO_INPUT=cards-sample.m4v -e ACCELERATION_DEVICE=CPU -e INFERENCING_MODEL=dummy blackjack-backend
```
