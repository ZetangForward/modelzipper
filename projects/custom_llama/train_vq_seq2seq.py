import random
import os
import transformers
from dataclasses import dataclass, field
from transformers import Trainer, T5Config
from modelzipper.tutils import *
from models.vq_seq2seq import VQSVGSeq2SeqModel
from data.vqlseq2seq_dataset import VQDataCollator, VQSeq2SeqData

@dataclass
class VQVAEConfig:
    config_path: str = field(default=None)
    
@dataclass
class ModelArguments:
    model_name_or_path: Optional[str] = field(default="facebook/opt-125m")
    
@dataclass
class DataArguments:
    data_path: str = field(default=None, metadata={"help": "Path to the training data."})
    vq_svg_pad_file: str = field(default=None, metadata={"help": "Path to the vq svg pad file."})


@dataclass
class TrainingArguments(transformers.TrainingArguments):
    cache_dir: Optional[str] = field(default=None)
    optim: str = field(default="adamw_torch")
    model_max_length: int = field(
        default=512,
        metadata={"help": "Maximum sequence length. Sequences will be right padded (and possibly truncated)."},
    )
    freezen_llm: bool = field(default=False)
    

def safe_save_model_for_hf_trainer(trainer: transformers.Trainer, output_dir: str):
    """Collects the state dict and dump to disk."""
    state_dict = trainer.model.state_dict()
    if trainer.args.should_save:
        cpu_state_dict = {key: value.cpu() for key, value in state_dict.items()}
        del state_dict
        trainer._save(output_dir, state_dict=cpu_state_dict)  # noqa




class CustomTrainier(Trainer):
    def __init__(self, model, args, train_dataset, eval_dataset, tokenizer, **kwargs):
        super().__init__(
            model=model, 
            args=args, 
            train_dataset=train_dataset, 
            eval_dataset=eval_dataset, 
            tokenizer=tokenizer,
            **kwargs,
        )
 
        
    def compute_loss(self, model, inputs, return_outputs=False):
        outputs = model(**inputs)
        loss = None
        
        if self.model.training:
            loss = outputs.pop("train_loss")
        else:
            loss = outputs.pop("eval_loss")
            
        for key in outputs:
            outputs[key] = outputs[key].item()
            
        self.log(outputs)  # log other metrics
        
        return (loss, outputs) if return_outputs else loss 


class PluginVQVAE(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model


def train():
    parser = transformers.HfArgumentParser((ModelArguments, DataArguments, TrainingArguments, VQVAEConfig))
    model_args, data_args, training_args, vqvae_args = parser.parse_args_into_dataclasses()
    
    # parsing vqvae_config:
    vqvae_config = load_yaml_config(vqvae_args.config_path)

    # config 
    flant5config = transformers.AutoConfig.from_pretrained(model_args.model_name_or_path)
    flant5config.frozen_llm = training_args.freezen_llm
    flant5config.max_text_length = 64
    flant5config.min_path_nums = 4
    flant5config.max_path_nums = 512
    
    flant5_tokenizer = transformers.AutoTokenizer.from_pretrained(
        model_args.model_name_or_path,
        cache_dir=training_args.cache_dir,
        model_max_length=training_args.model_max_length,  # 512
        padding_side="right",
        use_fast=True,
    )
    
    svg_data_module = VQSeq2SeqData(
        flant5config, 
        data_args.data_path, 
        tokenizer=flant5_tokenizer, 
        offline_mode=True,
        task="generation",
        svg_begin_token = None
    )

    data_collator = VQDataCollator(
        max_svg_length=flant5_tokenizer.max_path_nums,
        offline_mode=True,
        return_all_token_mask=True, # for offline setting
    )
    
    data_module = dict(
        train_dataset=svg_data_module.train_dataset, 
        eval_dataset=svg_data_module.valid_dataset, 
        data_collator=data_collator
    )

    SvgSeq2SeqModel = VQSVGSeq2SeqModel.from_pretrained(
        model_args.model_name_or_path, 
        config=flant5config,
        codebook_size=vqvae_config.vqvae.l_bins,
        cache_dir=training_args.cache_dir,
        tokenizer=flant5_tokenizer,
    )

    SvgSeq2SeqModel.is_parallelizable = False
    SvgSeq2SeqModel.model_parallel = False

    # # init optimizer
    # if svgllama.model_parallel:
    #     all_params = [param for module in svgllama.modules() for param in module.parameters()]
    # else:
    #     all_params = svgllama.parameters()
    
    # trainable_params = [p for p in all_params if p.requires_grad]
    # optimizer = torch.optim.AdamW(trainable_params, lr=training_args.learning_rate)

    # # init lr scheduler
    # lr_scheduler = transformers.get_linear_schedule_with_warmup(
    #     optimizer,
    #     num_warmup_steps=training_args.warmup_steps,
    #     num_training_steps=training_args.max_steps,
    # )

    trainer = CustomTrainier(model=SvgSeq2SeqModel, tokenizer=flant5_tokenizer, args=training_args, **data_module)
    
    SvgSeq2SeqModel.config.use_cache = False

    trainer.train()
    trainer.save_state()
    safe_save_model_for_hf_trainer(trainer=trainer, output_dir=training_args.output_dir)


if __name__ == "__main__":
    train()