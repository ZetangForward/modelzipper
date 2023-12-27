from pytorch_lightning.utilities.types import TRAIN_DATALOADERS
import torch   
from torch.utils.data import DataLoader, Dataset  
from pathlib import Path  
from typing import List, Optional, Sequence, Union, Any, Callable, Dict, Tuple  
from modelzipper.tutils import *
from torch.utils.data import DataLoader, Dataset
import pytorch_lightning as pl

class BasicDataset(Dataset):
    def __init__(self, dataset, max_path_nums=150, mode="train", pad_token_id=-1, num_bins = 9):
        super().__init__()
        self.dataset = dataset
        self.max_path_nums = max_path_nums
        self.mode = mode
        self.pad_token_id = pad_token_id
        self.num_bins = num_bins

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        item = self.dataset[idx]
        keywords, sample = item['keywords'], item['mesh_data']
        if len(sample) < self.max_path_nums:
            sample = torch.cat([sample, torch.empty(self.max_path_nums - len(sample), self.num_bins).fill_(self.pad_token_id)])
        else:
            sample = sample[:self.max_path_nums]
        padding_mask = ~(sample == -1).all(dim=1, keepdim=True).squeeze()
        return {
            "svg_path": sample, 
            "padding_mask": padding_mask,
        }

    @staticmethod
    def custom_datacollator(batch):
        return batch
    

class SvgDataModule(pl.LightningDataModule):
    
    def __init__(self, config, transform=None):
        self.cfg = config       
        self.transform = transform

    def prepare_data(self) -> None:
        # dataset processing operations here
        return None
    
    def setup(self, stage: str = 'fit') -> None:
        self.svg_files = auto_read_data(self.cfg.train_data_path)
        self.train_file = self.svg_files[:-500]
        self.valid_file = self.svg_files[-500:]

        self.train_dataset = BasicDataset(
            self.train_file, max_path_nums=self.cfg.max_path_nums, 
            mode='train', pad_token_id=self.cfg.pad_token_id
        )
        self.valid_dataset = BasicDataset(
            self.valid_file, max_path_nums=self.cfg.max_path_nums, 
            mode='valid', pad_token_id=self.cfg.pad_token_id
        )    

    def train_dataloader(self) -> TRAIN_DATALOADERS:
        return DataLoader(
            self.train_dataset, batch_size=self.cfg.batch_size, 
            num_workers=self.cfg.nworkers, sampler=self.train_sampler, 
            pin_memory=self.cfg.pin_memory, drop_last=True, shuffle=True, 
            collate_fn=BasicDataset.custom_datacollator,
        )
    
    def valid_dataloader(self) -> TRAIN_DATALOADERS:
        return DataLoader(
            self.valid_dataset, batch_size=self.cfg.batch_size, 
            num_workers=self.cfg.nworkers, sampler=self.valid_sampler, 
            pin_memory=self.cfg.pin_memory, drop_last=True, shuffle=False,
            collate_fn=BasicDataset.custom_datacollator
        )




### for data testing
# data_module = SvgDataModule(config.dataset)
# data_module.setup()  
# tmp = data_module.train_dataset[0]
# print(tmp)