

class TaskConfig:
    def __init__(
            self, data_name, data_path, processed_data_path,
            module, class_name, nworkers, max_seq_length, train_batch_size,
            val_batch_size, inference_mode, pin_memory, cluster_batch,
            **other_cfgs
        ) -> None:
        """ 
        default config can only contain:
            - data_path
            - processed_data_path
            - module
            - class_name
            - nworkers
            - max_seq_length
            - train_batch_size
            - val_batch_size
            - inference_mode
            - pin_memory
            - cluster_batch
        
        other_cfgs should be a dict, which can contains specific configs for the task
        """
        self.data_name = data_name
        self.data_path = data_path
        self.processed_data_path = processed_data_path
        self.module = module
        self.class_name = class_name
        self.nworkers = nworkers
        self.max_seq_length = max_seq_length
        self.train_batch_size = train_batch_size
        self.val_batch_size = val_batch_size
        self.inference_mode = inference_mode
        self.pin_memory = pin_memory
        self.cluster_batch = cluster_batch
        self.other_cfgs = other_cfgs
        
        self.return_config(
            data_name, processed_data_path,
            train_batch_size, val_batch_size,
            inference_mode,
        )

    def return_config(
        data_name,
        processed_data_path,
        train_batch_size,
        val_batch_size,
        inference_mode,
    ):
        if "mqar" in data_name.lower():   
            config_pool = []

            return TaskConfig.mqar_config(
                inference_mode = inference_mode,
                train_batch_size = train_batch_size if not inference_mode else val_batch_size,
                processed_data_path = processed_data_path,
                vocab_size = 8192,
                num_examples = 3000,
                input_seq_len = 4096,
                num_kv_pairs = 64,
                test_power_a = 0.01,
            )
        elif "passkey" in data_name.lower():
            return TaskConfig.passkey_config()

        elif "longalpaca" in data_name.lower():
            return TaskConfig.longalpaca_config()
    

    @classmethod
    def mqar_config(
        cls, processed_data_path, inference_mode, vocab_size, 
        num_examples, input_seq_len, num_kv_pairs, test_power_a
    ):
        mqar_confg = {
            "data_name": "MQAR",
            "data_path": None, 
            "processed_data_path": processed_data_path,
            "module": 'custom_dataset.AR_ywj', 
            "class_name": 'MQARDataset',
            "nworkers": 4,
            "max_seq_length": 5000,
            "train_batch_size": 1,
            "val_batch_size": 1
            "inference_mode": True
            "pin_memory": False
            "cluster_batch": False


        }

        return adamw_config


    @classmethod
    def passkey_config(cls):
        passkey_config = {
            "data_name": "PasskeySearch",
            "data_path": "needle/PaulGrahamEssays/*.txt",
            "processed_data_path": "needle/processed_data/128k_500_insert_ids.pkl",
            "module": 'custom_dataset.passkey_search',
            "class_name": 'PasskeySearchDataset',
            "nworkers": 4,
            "max_seq_length": 128000,
            "val_batch_size": 1,
            "inference_mode": True,
            "pin_memory": False,
            "cluster_batch": False,
            "depth": 0.5,
            "key": "The best thing to do in San Francisco is",
            "value": "eat a sandwich and sit in Dolores Park on a sunny day.",
        }
        return passkey_config
    
    @classmethod
    def longalpaca_config(cls):
        longalpaca_config = {
            "data_path": "LongAlpaca-12k/LongAlpaca-12k.json",
            "processed_data_path": None,
            "max_seq_length": 3000,
            "module": 'custom_dataset.longlora',
            "class_name": 'LongLoRA',  
            "nworkers": 4,
            "train_batch_size": 1,
            "val_batch_size": 1,
            "pin_memory": False,
            "inference_mode": False,
            "cluster_batch": True  
        }

        return longalpaca_config




    

