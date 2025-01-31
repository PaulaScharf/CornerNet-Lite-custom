import os
import json
import numpy as np

from .detection import DETECTION
from ..paths import get_file_path

# COCO bounding boxes are 0-indexed

class CUSTOM(DETECTION):
    def __init__(self, db_config, split=None, sys_config=None):
        assert split is None or sys_config is not None
        super(CUSTOM, self).__init__(db_config)

        # TODO: what is this??
        self._mean    = np.array([0.40789654, 0.44719302, 0.47026115], dtype=np.float32)
        self._std     = np.array([0.28863828, 0.27408164, 0.27809835], dtype=np.float32)
        self._eig_val = np.array([0.2141788, 0.01817699, 0.00341571], dtype=np.float32)
        self._eig_vec = np.array([
            [-0.58752847, -0.69563484, 0.41340352],
            [-0.5832747, 0.00994535, -0.81221408],
            [-0.56089297, 0.71832671, 0.41158938]
        ], dtype=np.float32)

        for _ in range(db_config["multi_frame"]*(4 if db_config["four_channels"] else 3)-3):
            self._mean = np.append(self._mean,0.40789654)
            self._std = np.append(self._std,0.28863828)
            self._eig_val = np.append(self._eig_val,0.2141788)

        if db_config["four_channels"]:
            self._eig_vec = np.append(self._eig_vec,[[-0.56089297], [0.71832671], [0.41158938]], axis=1)
            self._eig_vec = np.append(self._eig_vec,[[-0.56089297, 0.71832671, 0.41158938, 0.41158938]], axis=0)
        self._coco_cls_ids = [
            1
        ]

        self._coco_cls_names = [
            'insects'
        ]

        self._cls2coco  = {ind + 1: coco_id for ind, coco_id in enumerate(self._coco_cls_ids)}
        self._coco2cls  = {coco_id: cls_id for cls_id, coco_id in self._cls2coco.items()}
        self._coco2name = {cls_id: cls_name for cls_id, cls_name in zip(self._coco_cls_ids, self._coco_cls_names)}
        self._name2coco = {cls_name: cls_id for cls_name, cls_id in self._coco2name.items()}

        self._four_channels = db_config["four_channels"] if db_config["four_channels"] is not None else False
        self._multi_frame = db_config["multi_frame"] if db_config["multi_frame"] is not None else 1

        if split is not None:
            dir_name = "yolo_normal"
            if db_config["name"] is not None:
                dir_name = db_config["name"]
            custom_dir = os.path.join(sys_config.data_dir, dir_name)
            print("[INFO] data dir name: " + dir_name)

            self._split     = {
                "train": "train",
                "val":  "val",
                "test":  "test"
            }[split]
            self._data_dir  = os.path.join(custom_dir, "images", self._split)
            self._anno_file = os.path.join(custom_dir, "annotations", "instances_{}.json".format(self._split))

            self._detections, self._eval_ids = self._load_coco_annos()
            self._image_ids = list(self._detections.keys())
            self._db_inds   = np.arange(len(self._image_ids))

    def _load_coco_annos(self):
        from pycocotools.coco import COCO

        coco = COCO(self._anno_file)
        self._coco = coco

        class_ids = coco.getCatIds()
        image_ids = coco.getImgIds()
        
        eval_ids   = {}
        detections = {}
        for image_id in image_ids:
            image = coco.loadImgs(image_id)[0]
            dets  = []
            
            eval_ids[image["file_name"]] = image_id
            for class_id in class_ids:
                annotation_ids = coco.getAnnIds(imgIds=image["id"], catIds=class_id)
                annotations    = coco.loadAnns(annotation_ids)
                category       = self._coco2cls[class_id]
                for annotation in annotations:
                    det     = annotation["bbox"] + [category]
                    det[2] += det[0]
                    det[3] += det[1]
                    dets.append(det)

            file_name = image["file_name"]
            if len(dets) == 0:
                detections[file_name] = np.zeros((0, 5), dtype=np.float32)
            else:
                detections[file_name] = np.array(dets, dtype=np.float32)
        return detections, eval_ids

    def image_path(self, ind):
        if self._data_dir is None:
            raise ValueError("Data directory is not set")

        db_ind    = self._db_inds[ind]
        file_name = self._image_ids[db_ind]
        return os.path.join(self._data_dir, file_name)

    def detections(self, ind):
        db_ind    = self._db_inds[ind]
        file_name = self._image_ids[db_ind]
        return self._detections[file_name].copy()

    def cls2name(self, cls):
        coco = self._cls2coco[cls]
        return self._coco2name[coco]

    def _to_float(self, x):
        return float("{:.2f}".format(x))

    def convert_to_coco(self, all_bboxes):
        detections = []
        for image_id in all_bboxes:
            coco_id = self._eval_ids[image_id]
            for cls_ind in all_bboxes[image_id]:
                category_id = self._cls2coco[cls_ind]
                for bbox in all_bboxes[image_id][cls_ind]:
                    bbox[2] -= bbox[0]
                    bbox[3] -= bbox[1]

                    score = bbox[4]
                    bbox  = list(map(self._to_float, bbox[0:4]))

                    detection = {
                        "image_id": coco_id,
                        "category_id": category_id,
                        "bbox": bbox,
                        "score": float("{:.2f}".format(score))
                    }

                    detections.append(detection)
        return detections

    def evaluate(self, result_json, cls_ids, image_ids):
        from pycocotools.cocoeval import COCOeval

        if self._split == "testdev":
            return None

        coco = self._coco

        eval_ids = [self._eval_ids[image_id] for image_id in image_ids]
        cat_ids  = [self._cls2coco[cls_id] for cls_id in cls_ids]

        if (isinstance(result_json, str)):
            coco_dets = coco.loadRes(result_json)
        else:
            coco_dets = result_json
        coco_eval = COCOeval(coco, coco_dets, "bbox")
        coco_eval.params.imgIds = eval_ids
        coco_eval.params.catIds = cat_ids
        coco_eval.evaluate()
        coco_eval.accumulate()
        coco_eval.summarize()
        return coco_eval.stats[0], coco_eval.stats[12:]
