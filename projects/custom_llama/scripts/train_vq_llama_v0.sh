deepspeed --num_gpus 16 \
    --num_nodes 4 \
    --master_addr worker-0 \
    --master_port 7329 \
    --hostfile configs/machine/hostfile_v64_sxm4 \
    train_vqllama.py \
    --model_name_or_path "/zecheng2/model_hub/Llama-2-7b-hf" \
    --data_path "/zecheng2/svg/icon-shop/test_data_snaps/test_mesh_data_svg_convert_p.pkl" \
    --output_dir "/zecheng2/vqllama/vqllama_llama/version_0" \
    --num_train_epochs 60 \
    --model_max_length 1500 \
    --per_device_train_batch_size 1 \
    --per_device_eval_batch_size 1 \
    --gradient_accumulation_steps 1 \
    --evaluation_strategy "no" \
    --save_strategy "steps" \
    --save_steps 80 \
    --save_total_limit 10 \
    --learning_rate 3e-6 \
    --warmup_steps 20 \
    --logging_steps 1 \
    --dataloader_num_workers 24 \
    --lr_scheduler_type "cosine" \
    --report_to "tensorboard" \
    --gradient_checkpointing True \
    --deepspeed configs/deepspeed/stage3.json \
    --fp16 True \
    --remove_unused_columns False \
    --config_path "configs/deepspeed/vqvae_config.yaml";

