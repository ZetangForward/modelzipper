import random
import os
import transformers
import sys
sys.path.append("/workspace/zecheng/modelzipper/projects/custom_llama")
from dataclasses import dataclass, field
from transformers import Trainer
from modelzipper.tutils import *
from data.vqllama_dataset import VQDataCollator, VQLLaMAData
from models.vqvae import VQVAE, postprocess
from data.svg_data import *
import pytorch_lightning as pl
from utils.visualize_svg import convert_svg

VQVAE_CONFIG_PATH = "/workspace/zecheng/modelzipper/projects/custom_llama/configs/deepspeed/vqvae_config.yaml"
DATA_PATH = "/zecheng2/svg/icon-shop/test_data_snaps/test_data_all_seq_with_mesh.pkl"

content = auto_read_data(DATA_PATH)
dataset = BasicDataset(dataset=content)
vqvae_config = load_yaml_config(VQVAE_CONFIG_PATH)

block_kwargs = dict(
        width=vqvae_config.vqvae_conv_block.width, 
        depth=vqvae_config.vqvae_conv_block.depth, 
        m_conv=vqvae_config.vqvae_conv_block.m_conv,
        dilation_growth_rate=vqvae_config.vqvae_conv_block.dilation_growth_rate,
        dilation_cycle=vqvae_config.vqvae_conv_block.dilation_cycle,
        reverse_decoder_dilation=vqvae_config.vqvae_conv_block.vqvae_reverse_decoder_dilation
    )

class PluginVQVAE(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

vqvae = VQVAE(vqvae_config, multipliers=None, **block_kwargs)
plugin_vqvae = PluginVQVAE(vqvae)
checkpoint = torch.load(vqvae_config.ckpt_path)  # load vqvae ckpt
plugin_vqvae.load_state_dict(checkpoint['state_dict'])
plugin_vqvae.eval()
plugin_vqvae.cuda()
plugin_vqvae.model.half()


def cal_compress_padding_mask(x):

    # add one more False to make sure the odd of the length of x when it is even
    if len(x) % 2 != 0:
        x = torch.cat((x, torch.tensor([False])))
    x = x.view(-1, 2).any(dim=1)
    return x

sample = dataset[0]['svg_path']
max_seq_len = 512
padded_sample = torch.concatenate([sample, torch.zeros(max_seq_len - sample.shape[0], 9)]).to(torch.float16).cuda()
padding_mask = ~(padded_sample == 0).all(dim=1, keepdim=True).squeeze()
compress_padding_mask = cal_compress_padding_mask(padding_mask)

padding_mask = padding_mask.cuda()
compress_padding_mask = compress_padding_mask.cuda()

# raw forward function
outputs, raw_zs, raw_quantized_zs = plugin_vqvae.model(padded_sample.unsqueeze(0), padding_mask, return_all_quantized_res=True, denormalize=True)
output = outputs[0]
post_process_output = postprocess(output, padding_mask, False)[0]  # path interpolation
raw_rendered, raw_str = convert_svg(post_process_output, True)
raw_rendered.save_png("/workspace/zecheng/modelzipper/projects/custom_llama/notebook/raw_rendered_half.png")

svg_token_ids = plugin_vqvae.model.encode(padded_sample.unsqueeze(0), start_level=0, end_level=1)
svg_token_ids = svg_token_ids[0]  # 这里是不加padding mask的svg token ids

remain_svg_token_ids = svg_token_ids[:, :compress_padding_mask.sum()] # 这里是加入padding mask的svg token ids

postprocess_output_no_padding = plugin_vqvae.model.decode(svg_token_ids, 0, 1, padding_mask, True, True)[0]
postprocess_output_with_padding = plugin_vqvae.model.decode(remain_svg_token_ids, 0, 1, padding_mask, True, True)[0]


p_svg_no_padding, p_svg_str_no_padding = convert_svg(postprocess_output_no_padding, True)
p_svg_with_padding, p_svg_str_with_padding = convert_svg(postprocess_output_with_padding, True)

p_svg_no_padding.save_png("/workspace/zecheng/modelzipper/projects/custom_llama/notebook/no_padding_half.png")
p_svg_with_padding.save_png("/workspace/zecheng/modelzipper/projects/custom_llama/notebook/with_padding_half.png")