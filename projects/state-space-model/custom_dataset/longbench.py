from modelzipper.datamanager import *
from modelzipper.tutils import *
from transformers import AutoTokenizer
from torch.utils.data import DataLoader, Dataset
import pytorch_lightning as pl
import torch
import glob
from datasets import load_from_disk


class LongBenchDataset(Dataset):
    def __init__(self, content=None, tokenizer=None, split="train", *args, **kwargs):
        super().__init__()
        self.split = split
        self.content = content
        self.tokenizer = tokenizer
        self.max_seq_length = kwargs["max_seq_length"]
        self.cluster_batch = kwargs["cluster_batch"]
        self.filter_length(kwargs["testing_max_ctx"])

    def filter_length(self, max_ctx_length=12000):
        new_content = []
        print_c(f"begin to filter the context length | total {len(self.content)} instances", "yellow")
        for item in self.content:
            if item['ctx_length'] <= max_ctx_length:
                new_content.append(item)
        new_content = sorted(new_content, key=lambda x: x['ctx_length'], reverse=True)  # from long to short
        self.content = new_content
        print_c(f"filtering finished | total {len(self.content)} instances", "yellow")


    @classmethod
    def load_context(cls, fpath, ctx_len=10000, tokenizer=None):
        context = ""
        for file in glob.glob(fpath):
            with open(file, 'r') as f: 
                context += f.read()
        tokenized_context = tokenizer(context, return_tensors="pt").input_ids
        tok_ids_len = len(tokenized_context[0])
        RATIO = len(context) / tok_ids_len
        context = context[: int(ctx_len * RATIO)]
        return context
    
    
    @classmethod
    def insert_needle(cls, context, needle, depth):
        context = context.split(".")
        c_len = len(context)
        needle_place = int(depth * c_len)
        context = ".".join(context[:needle_place]) + " ." + needle + ". ".join(context[needle_place:])
        return context


    @classmethod
    def build_dataset(cls, fpath, key, value, ctx_len, tokenizer):
        all_insert_data = []
        depth_lst = [i * 0.05 for i in range(1, 21)]
        ctx_lst = [round(i / 500) * 500 for i in range(500, ctx_len+1, 500)]
        passkey = key + " " + value
        with tqdm(total=len(ctx_lst) * len(depth_lst)) as pbar:
            for i, tmp_ctx_len in enumerate(ctx_lst):
                context = cls.load_context(fpath=fpath, ctx_len=tmp_ctx_len, tokenizer=tokenizer)
                for j, depth in enumerate(depth_lst):
                    context_insert = cls.insert_needle(context, passkey, depth=depth)
                    # needle_idx = context_insert.find(key)
                    # print_c(f"insert passkey into {tmp_ctx_len} length context, depth: {depth}", "yellow")
                    # print_c("Context has %d chars, passkey inserted at %d char location:\n" % (len(context_insert), needle_idx), 'magenta')
                    # print_c(context_insert[needle_idx - 150: needle_idx + 150], 'cyan') # look at how the needle is inserted 
                    # print_c("-"*30)
                    passkey_context = context_insert + key
                    all_insert_data.append(
                        {
                            "depth": depth, 
                            "key": key,
                            "value": value,
                            "passkey_context": passkey_context,
                            "ctx_length": tmp_ctx_len
                        }
                    )
                    pbar.update(1)

        return all_insert_data

    def cluster_batch_fn(self):
        tmp = [item['source'] + ' ' + item['target'] for item in self.content]
        # tok_tmp = [self.tokenizer(item, return_tensors="pt") for item in tmp]
        sorted_tok_tmp = sorted(tmp, key=lambda x: len(x.split()))
        self.content = sorted_tok_tmp

    def __len__(self):
        return len(self.content)
    
    def __getitem__(self, index) -> Any:
        item = self.content[index]
        passkey_context = item.pop('passkey_context')
        tokenized_sequence = self.tokenizer(  # re-tokenize to get attention mask
            passkey_context,  
            return_tensors="pt",
        )

        input_ids = tokenized_sequence.input_ids[0]
        attention_mask = tokenized_sequence.attention_mask[0]
       
        res = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }

        res.update(item)

        return res
