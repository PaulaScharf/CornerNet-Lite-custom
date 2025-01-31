#!/usr/bin/env python
import os
import json
import torch
import pprint
import argparse
import importlib

from core.dbs import datasets
from core.test import test_func
from core.config import SystemConfig
from core.nnet.py_factory import NetworkFactory

torch.backends.cudnn.benchmark = False

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluation Script")
    parser.add_argument("cfg_file", help="config file", type=str)
    parser.add_argument("model", help="model", type=str)
    parser.add_argument("--testiter", dest="testiter",
                        help="test at iteration i",
                        default=None, type=int)
    parser.add_argument("--data", default=None, type=str)
    parser.add_argument("--split", dest="split",
                        help="which split to use",
                        default="validation", type=str)
    parser.add_argument("--suffix", dest="suffix", default=None, type=str)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument('--four-channels', action='store_true', help='accept input images with 4 channels')
    parser.add_argument('--multi-frame', type=int, default=1, choices=range(1,101), help='how many frames to load at once')
    parser.add_argument("--snapshot-name", default=None, type=str)

    args = parser.parse_args()
    return args

def make_dirs(directories):
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

def test(db, system_config, db_config, model, args):
    split    = args.split
    testiter = args.testiter
    debug    = args.debug
    suffix   = args.suffix

    result_dir = system_config.result_dir
    result_dir = os.path.join(result_dir, str(testiter), split)

    if suffix is not None:
        result_dir = os.path.join(result_dir, suffix)

    print('saving results to: ' + str(result_dir))
    make_dirs([result_dir])

    test_iter = system_config.max_iter if testiter is None else testiter
    print("loading parameters at iteration: {}".format(test_iter))

    print("building neural network...")
    nnet = NetworkFactory(system_config, db_config, model)
    print("loading parameters...")
    nnet.load_params(test_iter)

    nnet.cuda()
    nnet.eval_mode()
    test_func(system_config, db, nnet, result_dir, debug=debug)

def main(args):
    if args.suffix is None:
        cfg_file = os.path.join("./configs", args.cfg_file + ".json")
    else:
        cfg_file = os.path.join("./configs", args.cfg_file + "-{}.json".format(args.suffix))
    print("cfg_file: {}".format(cfg_file))

    with open(cfg_file, "r") as f:
        config = json.load(f)
            
    config["system"]["snapshot_name"] = args.cfg_file
    if args.snapshot_name is not None:
        config["system"]["snapshot_name"] = args.snapshot_name
    system_config = SystemConfig().update_config(config["system"])

    config["db"]["name"] = args.data
    config["db"]["four_channels"] = args.four_channels
    config["db"]["multi_frame"] = args.multi_frame
    channels = ((4 if args.four_channels else 3) * args.multi_frame)

    model_file  = "core.models.{}".format(args.model)
    model_file  = importlib.import_module(model_file)
    model       = model_file.model(input_channels=channels)
    print('loading model file: ' + str(model_file))

    train_split = system_config.train_split
    val_split   = system_config.val_split
    test_split  = system_config.test_split

    split = {
        "training": train_split,
        "validation": val_split,
        "testing": test_split
    }[args.split]

    print("loading all datasets...")
    dataset = system_config.dataset
    print("split: {}".format(split))
    testing_db = datasets[dataset](config["db"], split=split, sys_config=system_config)

    print("system config...")
    pprint.pprint(system_config.full)

    print("db config...")
    pprint.pprint(testing_db.configs)

    test(testing_db, system_config, config["db"], model, args)

if __name__ == "__main__":
    args = parse_args()
    main(args)
