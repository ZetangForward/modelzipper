deepspeed --num_gpus 16 \
    --num_nodes 4 \
    --master_addr worker-0 \
    --master_port 5669 \
    --hostfile "/workspace/zecheng/modelzipper/projects/custom_llama/configs/machine/hostfile_v64_sxm4" \
    icon-shop/train.py \
    --model_name_or_path "/zecheng2/model_hub/flan-t5-xl" \
    --data_path "/zecheng2/svg/icon-shop/meta_data" \
    --output_dir "/zecheng2/vqllama/baselines/iconshop" \
    --num_train_epochs 10 \
    --model_max_length 1024 \
    --per_device_train_batch_size 10 \
    --per_device_eval_batch_size 10 \
    --gradient_accumulation_steps 1 \
    --evaluation_strategy "no" \
    --save_strategy "steps" \
    --save_steps 250 \
    --save_total_limit 15 \
    --learning_rate 3e-6 \
    --warmup_steps 20 \
    --logging_steps 1 \
    --dataloader_num_workers 12 \
    --lr_scheduler_type "cosine" \
    --report_to "tensorboard" \
    --gradient_checkpointing True \
    --deepspeed "/workspace/zecheng/modelzipper/projects/custom_llama/configs/deepspeed/stage3.json" \
    --fp16 False \
    --remove_unused_columns False;



