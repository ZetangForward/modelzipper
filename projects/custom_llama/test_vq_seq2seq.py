import random
import os
import transformers
from dataclasses import dataclass, field
from tqdm import tqdm, trange
from torch import Tensor
from modelzipper.tutils import *
from models.vq_seq2seq import VQSVGSeq2SeqModel
from data.vqseq2seq_dataset import VQSeq2SeqData
from models.vqvae import VQVAE
from utils.visualize_svg import sanint_check_svg_tensor, convert_svg, merge_images

IGNORE_INDEX = -100
DEFAULT_PAD_TOKEN = "<PAD>"
DEFAULT_BOS_TOKEN = "<s>"
DEFAULT_EOS_TOKEN = "</s>"
DEFAULT_UNK_TOKEN = "<unk>"
DEFAULT_SVG_BEGIN_TOKEN = "<SVG>"


@dataclass
class TestConfig:
    vqvae_config_path: str = field(default=None)
    tokenier_config_path: str = field(default=None)
    ckpt: str = field(default=None)
    data_path: str = field(default=None)
    predict_batch_size: int = field(default=1)
    dataloader_num_workers: int = field(default=0)
    max_generate_length: int = field(default=1024)
    do_sample: bool = field(default=False)
    top_p: float = field(default=0.9)
    top_k: int = field(default=40)
    num_beams: int = field(default=1)
    temperature: float = field(default=0.8)
    save_dir: str = field(default=None)
    fp16: bool = field(default=True)
    model_max_length: int = field(default=1024)
    inference_nums: int = field(default=1)
    decode_golden: bool = field(default=False)
    do_raster: bool = field(default=False)
    do_inference: bool = field(default=True)
    snap_id: int = field(default=0)


class PluginVQVAE(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model


def saint_check_input(prompt, input_lst):
    while True:  
        user_input = input(prompt).strip()  
        if user_input.lower() in input_lst:  
            return user_input.lower()  
        else:  
            print(f"Invalid input. Please enter one of the following: {input_lst}") 


def interative_loop(model, image_save_root_dir, vqvae, tokenizer, max_generate_length=512, **kwargs):
    """
    For user interactive input
    """
    input_text = "begin"
    while input_text.lower() not in ("q", "quit"):
        input_text = input("Please input text: (press q to quit)").strip()
        input_ids = tokenizer(input_text, return_tensors="pt").input_ids.squeeze(0)
        input_ids = input_ids.to(model.device)
        svg_decoder_input_ids = torch.tensor([4097], dtype=input_ids.dtype, device=input_ids.device).unsqueeze(0)
        with torch.no_grad():
            outputs = model.generate(  # List[Tensor]
                input_ids=input_ids, max_new_tokens=max_generate_length, decoder_input_ids=svg_decoder_input_ids, use_cache=True, **kwargs
            )
            svg_token_ids = outputs[0]
            token_ids_to_find = [4097, 4096]
            if svg_token_ids[0] == 0:
                svg_token_ids = svg_token_ids[2:]
            min_index = None  
            for token_id in token_ids_to_find:  
                indices = torch.where(svg_token_ids == token_id)[0]  
                if len(indices) > 0:  
                    if min_index is None or indices[0] < min_index:  
                        min_index = indices[0]    
                if min_index is not None:  
                    svg_token_ids = svg_token_ids[:min_index]  
                        
            decoded_svg_path_pi = vqvae.decode(zs=[svg_token_ids], start_level=0, end_level=1, padding_mask=None, path_interpolation=True, return_postprocess=True)[0]
            decoded_svg_path_pc = vqvae.decode(zs=[svg_token_ids], start_level=0, end_level=1, padding_mask=None, path_interpolation=False, return_postprocess=True)[0]
           
            svg_pi, svg_str = convert_svg(decoded_svg_path_pi, True)
            svg_pc, svg_str = convert_svg(decoded_svg_path_pc, True)
            
        whether_save_image = saint_check_input("Whether to save the image? (y/n)", ['y', 'n', 'Y', 'N'])
        if whether_save_image == 'y':
            save_file_name = input_text.replace(" ", "_")
            svg_pi.save_png(os.path.join(image_save_root_dir, f"{save_file_name}-pi.png"))
            svg_pc.save_png(os.path.join(image_save_root_dir, f"{save_file_name}-pc.png"))
            
        

def predict_loop(model, vqvae, dataloader, tokenizer, max_generate_length=1024, decoder_input_ids=None, **kwargs) -> List[Tensor]:
    """
    For testing the whole dataset
    """
    res = []
    with tqdm(desc="Predicting", total=len(dataloader)) as pbar:
        for batch_ in dataloader:
            cur_batch_res = []
            # text_input_ids = batch_.get("text_input_ids")
            # text_attention_mask = batch_.get("text_attention_mask")
            # golden_svg_path = batch_.get("svg_tensors")
            # golden_svg_path_mask = batch_.get("svg_attention_mask")
            
            text_input_ids = batch_.get("input_ids")
            text_attention_mask = batch_.get("attention_mask")
            golden_svg_path = batch_.get("decoder_input_ids")
            golden_svg_path_mask = batch_.get("decoder_attention_mask")
            raw_data = batch_.get("raw_data")
            raw_data_mask = ~(raw_data == 0).all(dim=2, keepdim=True)
            
            text_input_ids = text_input_ids.to(model.device) if text_input_ids is not None else None
            text_attention_mask = text_attention_mask.to(model.device) if text_attention_mask is not None else None
            golden_svg_path = golden_svg_path.to(model.device) if golden_svg_path is not None else None
            
            svg_decoder_input_ids = torch.empty(golden_svg_path.size(0), 1).fill_(decoder_input_ids).to(model.device).long() if decoder_input_ids is not None else None

            with torch.no_grad():
                outputs = model.generate(input_ids=text_input_ids, attention_mask=text_attention_mask,max_new_tokens=max_generate_length, decoder_input_ids=svg_decoder_input_ids, use_cache=True, **kwargs)
                token_ids_to_find = [4097, 4096]  
                
                for i, svg_token_ids in enumerate(outputs):
                    ## sanint check
                    if svg_token_ids[0] == 0:
                        svg_token_ids = svg_token_ids[2:]
                    min_index = None  
                    for token_id in token_ids_to_find:  
                        indices = torch.where(svg_token_ids == token_id)[0]  
                        if len(indices) > 0:  
                            if min_index is None or indices[0] < min_index:  
                                min_index = indices[0]  
                    if min_index is not None:  
                        svg_token_ids = svg_token_ids[:min_index]  

                    decoded_svg_path_pi = vqvae.decode(zs=[svg_token_ids], start_level=0, end_level=1, padding_mask=None, path_interpolation=True, return_postprocess=True)[0]
                    decoded_svg_path_pc = vqvae.decode(zs=[svg_token_ids], start_level=0, end_level=1, padding_mask=None, path_interpolation=False, return_postprocess=True)[0]
                    
                    text = tokenizer.decode(text_input_ids[i], skip_special_tokens=True)
                    cur_batch_res.append(  # move to the CPU menory
                        dict(
                            golden_svg_path = golden_svg_path[i][:golden_svg_path_mask[i].sum()].cpu(),
                            generated_svg_path_pi = decoded_svg_path_pi.cpu(),
                            generated_svg_path_pc = decoded_svg_path_pc.cpu(),
                            text = text,
                            raw_data = raw_data[i][:raw_data_mask[i].sum()].cpu(),
                        )
                    )
            res.extend(cur_batch_res)
            pbar.update(1)
    return res


def text_only_predict_loop(model, vqvae, dataloader, tokenizer, max_generate_length=1024, decoder_input_ids=None, **kwargs) -> List[Tensor]:
    """
    For testing the whole dataset
    """
    res = []
    with tqdm(desc="Predicting", total=len(dataloader)) as pbar:
        for batch_ in dataloader:
            cur_batch_res = []
            
            text_input_ids = batch_.get("input_ids")
            text_attention_mask = batch_.get("attention_mask")
            golden_svg_path = batch_.get("decoder_input_ids")
            golden_svg_path_mask = batch_.get("decoder_attention_mask")
            raw_data = batch_.get("raw_data")
            raw_data_mask = ~(raw_data == 0).all(dim=2, keepdim=True)
            
            text_input_ids = text_input_ids.to(model.device) if text_input_ids is not None else None
            text_attention_mask = text_attention_mask.to(model.device) if text_attention_mask is not None else None
            golden_svg_path = golden_svg_path.to(model.device) if golden_svg_path is not None else None
            
            svg_decoder_input_ids = torch.empty(golden_svg_path.size(0), 1).fill_(decoder_input_ids).to(model.device).long() if decoder_input_ids is not None else None

            with torch.no_grad():
                outputs = model.generate(input_ids=text_input_ids, attention_mask=text_attention_mask,max_new_tokens=max_generate_length, decoder_input_ids=svg_decoder_input_ids, use_cache=True, **kwargs)
                
                token_ids_to_find = [4097, 4096]  
                
                for i, svg_token_ids in enumerate(outputs):
                    ## sanint check
                    if svg_token_ids[0] == 0:
                        svg_token_ids = svg_token_ids[2:]
                    min_index = None  
                    for token_id in token_ids_to_find:  
                        indices = torch.where(svg_token_ids == token_id)[0]  
                        if len(indices) > 0:  
                            if min_index is None or indices[0] < min_index:  
                                min_index = indices[0]  
                    if min_index is not None:  
                        svg_token_ids = svg_token_ids[:min_index]  

                    decoded_svg_path_pi = vqvae.decode(zs=[svg_token_ids], start_level=0, end_level=1, padding_mask=None, path_interpolation=True, return_postprocess=True)[0]
                    decoded_svg_path_pc = vqvae.decode(zs=[svg_token_ids], start_level=0, end_level=1, padding_mask=None, path_interpolation=False, return_postprocess=True)[0]
                    
                    text = tokenizer.decode(text_input_ids[i], skip_special_tokens=True)
                    cur_batch_res.append(  # move to the CPU menory
                        dict(
                            golden_svg_path = golden_svg_path[i][:golden_svg_path_mask[i].sum()].cpu(),
                            generated_svg_path_pi = decoded_svg_path_pi.cpu(),
                            generated_svg_path_pc = decoded_svg_path_pc.cpu(),
                            text = text,
                            raw_data = raw_data[i][:raw_data_mask[i].sum()].cpu(),
                        )
                    )
            res.extend(cur_batch_res)
            pbar.update(1)
    return res
                    
                    
def post_process(res: List[Dict], save_dir=None, generate_big_map=True, add_background=False, save_intermediate_results=False, vqvae=None, decode_golden=False) -> None:
    
    assert save_dir is not None, "save_dir must be specified!"
    SINGLE_IMAGE_SAVED_DIR = auto_mkdir(os.path.join(save_dir, "rendered_single_image")) # save single image
    SVG_PATH_SAVED_PATH = os.path.join(save_dir, "svg_paths.jsonl") # save svg path
    
    auto_mkdir(SINGLE_IMAGE_SAVED_DIR)
    
    str_paths = []
    all_image_paths = []
    
    for i in trange(len(res)):
        try:
            generated_svg_path_pi = res[i]['generated_svg_path_pi']
            generated_svg_path_pc = res[i]['generated_svg_path_pc']
            golden_svg_path = res[i]['golden_svg_path']
            text = res[i]['text']
            ## decode golden
            if decode_golden:
                golden_svg_path = vqvae.decode(zs=[golden_svg_path[1:].cuda()], start_level=0, end_level=1, padding_mask=None, path_interpolation=True, return_postprocess=True)[0]
        
            predict_pi = sanint_check_svg_tensor(generated_svg_path_pi).squeeze(0)
            p_svg_pi, p_svg_str_pi = convert_svg(predict_pi, True)
            predict_pc = sanint_check_svg_tensor(generated_svg_path_pc).squeeze(0)
            p_svg_pc, p_svg_str_pc = convert_svg(predict_pc, True)
            golden = sanint_check_svg_tensor(golden_svg_path).squeeze(0)
            g_svg, g_svg_str = convert_svg(golden, True)
            
            str_paths.append({
                "text": text,
                "p_svg_str_pi": p_svg_str_pi,
                "p_svg_str_pc": p_svg_str_pc, 
                "g_svg_str": g_svg_str,
            })
            
            if 'raw_data' in res[i]:
                raw_data = res[i]['raw_data']
                raw = sanint_check_svg_tensor(raw_data).squeeze(0)
                r_svg, r_svg_str = convert_svg(raw, True)
                str_paths[-1]["r_svg_str"] = r_svg_str
                str_paths[-1]['r_svg_path'] = os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_r_svg.png")
                r_svg.save_png(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_r_svg.png"))
                all_image_paths.append(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_r_svg.png"))
            
            p_svg_pi.save_png(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg_pi.png"))
            p_svg_pc.save_png(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg_pc.png"))
            g_svg.save_png(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_g_svg.png"))
            all_image_paths.append(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg_pi.png"))
            all_image_paths.append(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg_pc.png"))
            all_image_paths.append(os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_g_svg.png"))
            
            str_paths[-1]['p_svg_path_pi'] = os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg_pi.png")
            str_paths[-1]['p_svg_path_pc'] = os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_p_svg_pc.png")
            str_paths[-1]['g_svg_path'] = os.path.join(SINGLE_IMAGE_SAVED_DIR, f"{i}_g_svg.png")
        
        except Exception as e:
            print_c(f"Error: {e}", "red")
            print_c(f"Error in {i}", "red")
            continue
        
    auto_save_data(str_paths, SVG_PATH_SAVED_PATH)

    
    if generate_big_map:
        print_c("begin to generate big map", "magenta")
        BIG_MAP_SAVED_DIR = auto_mkdir(os.path.join(save_dir, "rendered_big_map"))
        p_svg_images_pi = merge_images(folder_path=SINGLE_IMAGE_SAVED_DIR, image_suffix='p_svg_pi.png', num_images=len(str_paths), save_dir=BIG_MAP_SAVED_DIR)
        p_svg_images = merge_images(folder_path=SINGLE_IMAGE_SAVED_DIR, image_suffix='p_svg_pc.png', num_images=len(str_paths), save_dir=BIG_MAP_SAVED_DIR)
        g_svg_images = merge_images(folder_path=SINGLE_IMAGE_SAVED_DIR, image_suffix='g_svg.png', num_images=len(str_paths), save_dir=BIG_MAP_SAVED_DIR)
        g_svg_images = merge_images(folder_path=SINGLE_IMAGE_SAVED_DIR, image_suffix='r_svg.png', num_images=len(str_paths), save_dir=BIG_MAP_SAVED_DIR)
    
    if add_background:
        print_c(f"add background to {len(all_image_paths)} images", "magenta")
        for i in trange(len(all_image_paths)):
            image_path = all_image_paths[i]
            if "_b.png" in image_path:
                continue
            add_background(image_path=image_path)
            
    if save_intermediate_results:
        raise NotImplementedError("save_intermediate_results is not implemented yet!")
        

def test():
    parser = transformers.HfArgumentParser((TestConfig))
    test_args = parser.parse_args_into_dataclasses()[0]
    
    # parsing vqvae_config:
    vqvae_config = load_yaml_config(test_args.vqvae_config_path)

    # parsing trained model path
    MODEL_NAME_OR_PATH = test_args.ckpt
    SAVE_DIR = test_args.save_dir
    auto_mkdir(SAVE_DIR)
    
    predicted_results = None
   
    flant5_tokenizer = transformers.AutoTokenizer.from_pretrained(
        test_args.tokenier_config_path,
        model_max_length=test_args.model_max_length,
        padding_side="right",
        use_fast=True,
    )
    
    # init VQVAE
    block_kwargs = dict(
        width=vqvae_config.vqvae_conv_block.width, 
        depth=vqvae_config.vqvae_conv_block.depth, 
        m_conv=vqvae_config.vqvae_conv_block.m_conv,
        dilation_growth_rate=vqvae_config.vqvae_conv_block.dilation_growth_rate,
        dilation_cycle=vqvae_config.vqvae_conv_block.dilation_cycle,
        reverse_decoder_dilation=vqvae_config.vqvae_conv_block.vqvae_reverse_decoder_dilation
    )
    vqvae = VQVAE(vqvae_config, multipliers=None, **block_kwargs)
    plugin_vqvae = PluginVQVAE(vqvae)
    checkpoint = torch.load(vqvae_config.ckpt_path)  # load vqvae ckpt
    plugin_vqvae.load_state_dict(checkpoint['state_dict'])
    print_c("VQVAE loaded!", "green")
    vqvae = plugin_vqvae.model
    vqvae.eval().cuda()
    
    vqvae = vqvae.half() if test_args.fp16 else vqvae
    
    if test_args.do_inference:
        ### Load T5 Model for inference
        # config 
        flant5config = transformers.AutoConfig.from_pretrained(MODEL_NAME_OR_PATH)
        flant5config.frozen_llm = False
        flant5config.max_text_length = 64
        flant5config.min_path_nums = 4
        flant5config.max_path_nums = 512
        flant5config.use_cache = False
        flant5config.predict_batch_size = test_args.predict_batch_size
        flant5config.dataloader_num_workers = test_args.dataloader_num_workers

        svg_data_module = VQSeq2SeqData(
            flant5config, 
            test_args.data_path, 
            tokenizer=flant5_tokenizer, 
            offline_mode=True,
            mode="test",
            svg_begin_token = None,
            inferece_nums=test_args.inference_nums,
            use_custom_collate_fn=True,
        )
        
        predict_dataloader = svg_data_module.predict_dataloader()

        svgllama = VQSVGSeq2SeqModel.from_pretrained(
        MODEL_NAME_OR_PATH, 
            config=flant5config, 
            codebook_size=vqvae_config.vqvae.l_bins,
        )
        
        svgllama.eval().cuda()
        svgllama = svgllama.half() if test_args.fp16 else svgllama
          
        sampling_strategy = dict(
            do_sample=test_args.do_sample,
            temperature=test_args.temperature,
            top_p=test_args.top_p,
            top_k=test_args.top_k,
            num_beams=test_args.num_beams,
        )

        # interative_loop(svgllama, "./", vqvae, flant5_tokenizer, max_generate_length=test_args.max_generate_length, **sampling_strategy)
        
        
        # exit()
        
        predicted_results = predict_loop(
            model=svgllama, 
            vqvae=vqvae,
            dataloader=predict_dataloader, 
            tokenizer=flant5_tokenizer,
            max_generate_length=test_args.max_generate_length,
            decoder_input_ids = vqvae_config.vqvae.l_bins + 1,
            **sampling_strategy,
        )
        print_c("begin to save predicted results", "magenta")
        auto_save_data(predicted_results, os.path.join(SAVE_DIR, f"snap_{test_args.snap_id}_results.pkl"))
    
    if test_args.do_raster:
        
        if predicted_results is None:
            predicted_results = []
            for id_ in range(8):
                predicted_results.extend(auto_read_data(os.path.join(SAVE_DIR, f"snap_{id_}_results.pkl")))
        
        post_process(
            predicted_results, 
            vqvae=vqvae,
            save_dir=SAVE_DIR, 
            generate_big_map=True, 
            add_background=False, 
            save_intermediate_results=False,
            decode_golden=True,
        )
    

if __name__ == "__main__":
    test()