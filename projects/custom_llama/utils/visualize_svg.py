import numpy as np
import os
import glob
import logging
import json
import sys
sys.path.append("/workspace/zecheng/modelzipper/projects")
from tqdm import tqdm
from concurrent import futures
from argparse import ArgumentParser
from change_deepsvg.svglib.svg import SVG
from change_deepsvg.svglib.geom import Bbox, Angle, Point
from change_deepsvg.difflib.tensor import SVGTensor
from modelzipper.tutils import *
import torch
from tqdm import trange
from PIL import Image

def sanint_check_svg_tensor(x):
    """
    x: batch_size x seq_len x (7, 9)
    """
    if x.ndim == 2:
        x = x.unsqueeze(0)
    if x.size(-1) == 9:
        x[:, :, 0][x[:, :, 0] == 100] = 1
        x[:, :, 0][x[:, :, 0] == 200] = 2
    elif x.size(-1) == 7:
        x_0_y_0 = torch.zeros((x.size(0), x.size(1), 2), dtype=x.dtype, device=x.device)
        x_0_y_0[:, 1:, 0] = x[:, :-1, -2]  # x_3 of the previous row
        x_0_y_0[:, 1:, 1] = x[:, :-1, -1]  # y_3 of the previous row
        x = torch.cat((x[:, :, :1], x_0_y_0, x[:, :, 1:]), dim=2)
    return x

def convert_svg(t, colored=False, save_path=None):
    svg = SVGTensor.from_data(t)
    svg = SVG.from_tensor(svg.data, viewbox=Bbox(200))
    if save_path is not None and colored:
        svg.draw_colored(fill=True, file_path=save_path, do_display=False)
    elif colored:
        svg = svg.normalize().split_paths().set_color("random").normalize()
    str_svg = svg.numericalize(n=200).to_str()
    return svg, str_svg


def add_background(image_obj=None, image_path=None, save_suffix="b", raw_image_size_w=None, raw_image_size_h=None):
    if image_obj is not None:
        image = image_obj
    elif image_path is not None:
        image = Image.open(image_path)

    sub_image_w = raw_image_size_w if raw_image_size_w is not None else image.size[0]
    sub_image_h = raw_image_size_h if raw_image_size_h is not None else image.size[1]

    new_image_size = (sub_image_w, sub_image_h)
    background_image = Image.new('RGB', new_image_size)

    background_image.paste(image, (0, 0))

    save_path = image_path.replace(".png", f"_{save_suffix}.png")
    background_image.save(save_path)
    return background_image


def merge_images(
        folder_path, image_suffix, num_images, raw_image_size_w=None,
        raw_image_size_h=None, image_row=10, image_col=10, save_dir=None,
    ):
    image_list = []
    for i in range(num_images):
        filename = f'{i}_{image_suffix}'
        image_path = os.path.join(folder_path, filename)
        try:
            image = Image.open(image_path)
            image_list.append(image)
        except:
            print_c(f"image {image_path} not found", "red")
            continue

    sub_image_w = raw_image_size_w if raw_image_size_w is not None else image_list[0].size[0]
    sub_image_h = raw_image_size_h if raw_image_size_h is not None else image_list[0].size[1]

    big_image_size = (sub_image_w * 10, sub_image_h * 10)
    big_image = Image.new('RGB', big_image_size)
    big_images = []

    for i, image in enumerate(image_list):
        i = i % (image_row * image_col)
        row = i // image_row
        col = i % image_col
        big_image.paste(image, (col * image.size[0], row * image.size[1]))
        
        if (i + 1) % (image_row * image_col) == 0:
            big_images.append(big_image)
            big_image = Image.new('RGB', big_image_size)

    if save_dir is not None:
        for i, big_image in enumerate(big_images):
            save_path = os.path.join(save_dir, f'big_map_{i}_{image_suffix}')
            big_image.save(save_path)
            print_c(f"save big map {i} to {save_path}")
    return big_images


def main(cl: int = 0, rd: str = None):
    """
    c_l: compress_level
    """
    assert cl in [1, 2, 3], "compress level must be 1, 2, 3"
    print_c(f"visualize compress level: {cl}", "magenta")
    assert rd is not None, "must specify root dir"
    print_c(f"root dir: {rd}", "magenta")

    ROOT_DIR = rd
    COMPRESS_LEVEL = cl
    FILE_PATH = os.path.join(ROOT_DIR, f"compress_level_{COMPRESS_LEVEL}_predictions.pkl")
    
    SAVE_DIR = auto_mkdir(os.path.join(ROOT_DIR, f"visualized_compress_level_{COMPRESS_LEVEL}"))
    BIG_MAP_SAVED_DIR = auto_mkdir(os.path.join(SAVE_DIR, "big_map")) # save big picture map
    SINGLE_IMAGE_SAVED_DIR = auto_mkdir(os.path.join(SAVE_DIR, "single_image")) # save single image    
    PATH_SAVED_PATH = os.path.join(SAVE_DIR, "svg_paths.jsonl") # save svg path

    DIRECT_GENERATE_BIG_MAP = False
    DIRECT_GENERATE_SINGLE_IMAGE = True
    DIRECT_ADD_BACKGROUND = False

    all_image_paths = []

    if DIRECT_GENERATE_SINGLE_IMAGE:
        results = auto_read_data(FILE_PATH)
        keys = ['raw_predict', 'p_predict1', 'p_predict2', 'golden', 'zs', 'xs_quantised']
        num_svgs = len(results[keys[0]])
        # num_svgs = 2000
        str_paths = []
        # special_lst = [815, 36, 196, 200, 1202]
        for i in trange(num_svgs):
        # for i in special_lst:
            raw_predict = results['raw_predict'][i]
            p_predict1 = results['p_predict1'][i]
            p_predict2 = results['p_predict2'][i]
            golden = results['golden'][i]

            p_predict1 = sanint_check_svg_tensor(p_predict1).squeeze(0)
            p_svg1, p_svg_str1 = convert_svg(p_predict1, True)
            p_predict2 = sanint_check_svg_tensor(p_predict2).squeeze(0)
            p_svg2, p_svg_str2 = convert_svg(p_predict2, True)
            golden = sanint_check_svg_tensor(golden).squeeze(0)
            g_svg, g_svg_str = convert_svg(golden, True)
            import pdb; pdb.set_trace()
            ## tmp save
            _ = p_svg1.normalize().draw_colored(fill=True, file_path=os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg1.png"))
            _ = p_svg2.normalize().draw_colored(fill=True, file_path=os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg2.png"))
            _ = g_svg.normalize().draw_colored(fill=True, file_path=os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_g_svg.png"))
            
            str_paths.append({
                "p_svg_str1": p_svg_str1,
                "p_svg_str2": p_svg_str2,
                "g_svg_str": g_svg_str,
            })
            
            # p_svg1.save_png(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg1.png"))
            # p_svg2.save_png(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg2.png"))
            # g_svg.save_png(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_g_svg.png"))
            all_image_paths.append(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg1.png"))
            all_image_paths.append(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg2.png"))
            all_image_paths.append(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_g_svg.png"))

        auto_save_data(str_paths, PATH_SAVED_PATH)

    if DIRECT_GENERATE_BIG_MAP:
        p_svg_images1 = merge_images(
            folder_path=SINGLE_IMAGE_SAVED_DIR, 
            image_suffix='p_svg1.png', 
            num_images=1999, 
            save_dir=BIG_MAP_SAVED_DIR
        )
        p_svg_images2 = merge_images(
            folder_path=SINGLE_IMAGE_SAVED_DIR, 
            image_suffix='p_svg2.png', 
            num_images=1999, 
            save_dir=BIG_MAP_SAVED_DIR
        )
        g_svg_images = merge_images(
            folder_path=SINGLE_IMAGE_SAVED_DIR, 
            image_suffix='g_svg.png', 
            num_images=1999, 
            save_dir=BIG_MAP_SAVED_DIR
        )

    if DIRECT_ADD_BACKGROUND:
        if len(all_image_paths) == 0:
            print_c(f"no image path, read all image paths from {SINGLE_IMAGE_SAVED_DIR}", "magenta")
            all_image_paths = glob.glob(os.path.join(SINGLE_IMAGE_SAVED_DIR, "*.png"))
        for i in trange(len(all_image_paths)):
            image_path = all_image_paths[i]
            if "_b.png" in image_path:
                continue
            add_background(image_path=image_path)

    
if __name__ == "__main__":
    fire.Fire(main)


