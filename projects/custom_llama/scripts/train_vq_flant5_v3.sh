OUTPUT_DIR="/zecheng2/vqllama/vqllama_flant5/version_3"

mkdir -p ${OUTPUT_DIR}

deepspeed --num_gpus 8 \
    --num_nodes 3 \
    --master_addr worker-0 \
    --master_port 6345 \
    --hostfile configs/machine/hostfile_v24 \
    train_vq_seq2seq.py \
    --model_name_or_path "/zecheng2/model_hub/flan-t5-xl" \
    --data_path "/zecheng2/svg/icon-shop/pkl_data/efficient_inference_full_data/test_vqllama_quantizer/version_8/epoch_84/inference_full_data_compress_1_snaps_merged.pkl" \
    --output_dir ${OUTPUT_DIR} \
    --num_train_epochs 20 \
    --model_max_length 512 \
    --per_device_train_batch_size 54 \
    --per_device_eval_batch_size 8 \
    --gradient_accumulation_steps 1 \
    --evaluation_strategy "steps" \
    --greater_is_better False \
    --save_strategy "steps" \
    --load_best_model_at_end True \
    --metric_for_best_model "loss" \
    --eval_steps 300 \
    --save_steps 300 \
    --save_total_limit 10 \
    --learning_rate 3e-5 \
    --warmup_steps 3 \
    --logging_steps 1 \
    --dataloader_num_workers 0 \
    --lr_scheduler_type "cosine" \
    --report_to "tensorboard" \
    --gradient_checkpointing True \
    --deepspeed configs/deepspeed/stage3_test.json \
    --fp16 False \
    --remove_unused_columns False \
    --freezen_llm True \
    --config_path "configs/deepspeed/vqvae_config.yaml";
