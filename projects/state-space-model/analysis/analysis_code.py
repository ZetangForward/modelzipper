import os
import numpy as np
import torch.nn.functional as F
import matplotlib.pyplot as plt
from modelzipper.tutils import *
from argparse import ArgumentParser

##############################
##### 1. analysis_rank  ######
##############################
class AnalysisRank:
    def __init__(self) -> None:
        pass

    def analysis_single_hidden_state(self, hidden_states):
        """
        hidden_states is (n, 4096) matrix
        """
        if hidden_states.dim() == 3:  # prevent batch size
            hidden_states = hidden_states.squeeze(0)

        if isinstance(hidden_states, torch.Tensor):
            hidden_states = hidden_states.float().cpu().numpy()
        # SVD
        import pdb; pdb.set_trace()
        u, s, vh = np.linalg.svd(hidden_states)

        # cal rank
        rank = np.sum(s > 1e-10)
        return rank


    def analysis_multi_hidden_states(self, dir):
        """
        这个实验主要分析一下在生成过程中，随着Conv1d逐渐将历史信息丢弃，剩下内容的Rank变化
        """
        hidden_states_list = auto_read_dir(dir, file_prefix="generate", file_suffix=".pkl")
        all_rks = []
        for file in hidden_states_list:
            hidden_states = auto_read_data(os.path.join(dir, file))
            rk = self.analysis_single_hidden_state(hidden_states)
            all_rks.append(rk)
        return all_rks


##############################
#### 2. analysis_similar  ####
##############################
class AnalysisSimilar:
    def __init__(self) -> None:
        pass
    def anaylsis_single_file_conv1d(self, dir, passkey_length: int = None):
        """
        analysis single context length
        """
        cov1d_state_paths = auto_read_dir(dir, file_prefix='passk', file_suffix=".pkl")
        embedding_path = auto_read_dir(dir, file_prefix='input_seq_embedding', file_suffix=".pkl")[0]
        embedding = auto_read_data(embedding_path)
        if embedding.dim() == 3:
            embedding = embedding.squeeze(0)
        embedding = embedding.permute(1, 0)
        ctx_length = int(os.path.basename(dir).split("-")[-1])

        print_c(f"ctx_length: {ctx_length}", "yellow")
        cov1d_state_paths = sorted(cov1d_state_paths, key=lambda x: eval(os.path.basename(x).split("-")[-3].replace('_', '.')))

        fig, axs = plt.subplots(nrows=5, ncols=1, figsize=(200, 50))
        plt.subplots_adjust(hspace=0.5)  # 调整子图之间的垂直间距
        axs = axs.flatten() 
        per_depth_scores = {}
        per_conv1d_scores = {}

        analysis_depths = [0.2, 0.4, 0.6, 0.8, 1.0]
        
        with tqdm(total=len(analysis_depths), desc="Drawing Figure ...") as pbar:
            idx = 0
            for fpath in cov1d_state_paths:

                analysis_depth = eval(os.path.basename(fpath).split("-")[-3].replace('_', '.'))
                
                if analysis_depth not in analysis_depths:
                    continue
                
                hidden_state = auto_read_data(fpath)

                if hidden_state.dim() == 3:
                    hidden_state = hidden_state.squeeze(0)
                hidden_state = hidden_state.permute(1, 0)
                
                similarity_matrix = torch.zeros(hidden_state.size(0), embedding.size(0)).to(hidden_state.device)
                
                for i, h in enumerate(hidden_state):
                    cos_sim = F.cosine_similarity(h.unsqueeze(0), embedding)
                    similarity_matrix[i] = cos_sim
                
                top_k = 20  # 取每个conv1d state的前20个最大值

                similarity_matrix_np = similarity_matrix.cpu().numpy()
                top_indices = np.argpartition(similarity_matrix_np, -10, axis=1)[:, -top_k:]  

                # 统计每个区间出发的关键点
                ### 真实数据的位置
                highlight_mask = np.zeros_like(similarity_matrix_np, dtype=bool)
                highlight_start = int(ctx_length * analysis_depth)
                highlight_mask[:, highlight_start: highlight_start + passkey_length] = True
                # 创建一个新的掩码,将highlight_mask部分设置为绿色
                green_mask = np.zeros((*similarity_matrix_np.shape, 3))
                green_mask[highlight_mask, 1] = 1.0  # 绿色通道设为1  

                ### 划分每个区间 划分 5个区间
                num_partitions = 5
                partition_length = similarity_matrix.size(-1) // num_partitions  # 每个分区的长度
                partition_scores = np.zeros((top_indices.shape[0], num_partitions))  # 存储每个分区的得分

                # 对 top_indices 进行排序
                top_indices_sorted = np.sort(top_indices, axis=1)

                # 计算每个分区的得分
                for j in range(num_partitions): # 遍历每个分区
                    start_idx = j * partition_length
                    end_idx = start_idx + partition_length
                    # 计算每个分区中top_indices的数量
                    for k in range(top_indices_sorted.shape[0]):  # 遍历每个conv1d state
                        count_in_partition = np.sum((top_indices_sorted[k, :] >= start_idx) & (top_indices_sorted[k, :] < end_idx))
                        partition_scores[k, j] = count_in_partition / top_k  # 计算比例
                
                per_depth_scores[analysis_depth] = partition_scores
                
                mask = np.zeros_like(similarity_matrix_np, dtype=bool)
                for i in range(similarity_matrix_np.shape[0]):
                    mask[i, top_indices[i]] = True

                # 假设highlight_start是高亮区域的开始位置，passkey_length是高亮区域的长度
                ax = axs[idx]
                ax.imshow(similarity_matrix_np, cmap='Reds', aspect='auto', alpha=0.3) 
                ax.imshow(mask, cmap='hot', aspect='auto', alpha=0.9)
                ax.imshow(green_mask, aspect='auto', alpha=0.3)  # 显示红色掩码

                # 绘制竖线表示切分位置
                for j in range(1, num_partitions):
                    ax.axvline(x=j * partition_length, color='yellow', linestyle='--', linewidth=20)

                idx += 1
                pbar.update(1)

        # 调整子图位置
        print_c("begin to save figure ...")
        # plt.tight_layout()
        # plt.savefig(f"analysis/figures/cosine_similarity_heatmap_ctx_length-{ctx_length}.png")

        # 绘制 per depth score 折线图
        print_c("begin to save line figure ...")
        fig, axs = plt.subplots(nrows=1, ncols=5, figsize=(25, 5))
        axs = axs.flatten()

        x_labels = ['20%', '40%', '60%', '80%', '100%']
        x_positions = np.arange(len(x_labels))
        
        for index, analysis_depth in enumerate(analysis_depths):
            for j, s in enumerate(per_depth_scores[analysis_depth]):
                axs[analysis_depths.index(analysis_depth)].plot(x_positions, s, marker='o', label=f'Conv1d-State-{j}')
            axs[index].set_xticks(x_positions)
            axs[index].set_xticklabels(x_labels)
            axs[index].set_xlabel('Percentage of Context')
            axs[index].set_ylabel('Percentage of Top Indices (out of 50)')
            axs[index].set_title(f'Passkey Depth {analysis_depth}')
            axs[index].legend()  

            # 设置y轴的范围和刻度
            axs[index].set_ylim(0.00, 0.5)  # 设置y轴范围
            axs[index].set_yticks(np.arange(0.00, 0.5, 0.05))  # 设置y轴刻度，包含0.5

            line_position = x_positions[index]
        
            # 绘制竖线
            axs[index].axvline(x=line_position, color='black', linestyle='--', linewidth=1)


        # 调整子图位置
        plt.tight_layout()
        plt.savefig(f"analysis/figures/cosine_similarity_line_figure_offset-ctx_length-{ctx_length}.png")


    def analysis_cov1d_compress(self, fpath, dir=None, highlight_start=18, highlight_end=40):
        # read text embedding
        text_embedding_file = auto_read_dir(fpath, file_prefix="input_seq_embedding", file_suffix=".pkl")[0]
        text_embedding = auto_read_data(text_embedding_file) # torch.Size([1, 550, 2048])
        if text_embedding.dim() == 3:
            text_embedding = text_embedding.squeeze(0)

        # read all intermediate states
        file_names = auto_read_dir(fpath, file_prefix="passkey", file_suffix=".pkl")
        file_names = sorted(file_names, key=lambda x: int(os.path.basename(x).split("-")[2]))

        sub_files = []
        with tqdm(total=len(file_names), desc="Drawing Figure ...") as pbar:
            for file_index, file_name in enumerate(file_names):
                sub_files.append(file_name)
                
                if (file_index + 1) % 5 == 0:  # 每5个文件为一组 （因为探针了5层）
                    offset = int(file_name.split("-")[2])
                    
                    sub_files = sorted(sub_files, key=lambda x: int(os.path.basename(x).split("-")[-1].split('.')[0]))
                    fig, axs = plt.subplots(nrows=5, ncols=1, figsize=(200, 50))
                    plt.subplots_adjust(hspace=0.5)  # 调整子图之间的垂直间距

                    axs = axs.flatten() 
                    layers, per_layer_scores = [], {}

                    for idx, file_name in enumerate(sub_files):
                        layer_idx = int(os.path.basename(file_name).split("-")[-1].split(".")[0])
                        layers.append(layer_idx)

                        hidden_state = auto_read_data(file_name) 
                        
                        if hidden_state.dim() == 3:
                            hidden_state = hidden_state.squeeze(0)
                        
                        hidden_state = hidden_state.permute(1, 0)

                        if hidden_state.size(-1) != text_embedding.size(-1):
                            h_avg_pooled = F.avg_pool1d(hidden_state, kernel_size=2, stride=2)

                        similarity_matrix = torch.zeros(4, 550).to(h_avg_pooled.device)
                        for i, h in enumerate(h_avg_pooled):
                            cos_sim = F.cosine_similarity(h.unsqueeze(0), text_embedding)
                            similarity_matrix[i] = cos_sim
                        
                        similarity_matrix_np = similarity_matrix.cpu().numpy()
                        top_indices = np.argpartition(similarity_matrix_np, -50, axis=1)[:, -50:]
                        
                        # 统计每个区间出发的关键点
                        ### 真实数据的位置
                        highlight_mask = np.zeros_like(similarity_matrix_np, dtype=bool)
                        highlight_mask[:, highlight_start: highlight_end] = True
                        # 创建一个新的掩码,将highlight_mask部分设置为红色
                        green_mask = np.zeros((*similarity_matrix_np.shape, 3))
                        green_mask[highlight_mask, 1] = 1.0  # 绿色通道设为1  

                        ### 划分每个区间
                        num_partitions = 5
                        partition_length = similarity_matrix.size(-1) // num_partitions  # 每个分区的长度
                        partition_scores = np.zeros((top_indices.shape[0], num_partitions))  # 存储每个分区的得分

                        # 对 top_indices 进行排序
                        top_indices_sorted = np.sort(top_indices, axis=1)

                        # 计算每个分区的得分
                        for j in range(num_partitions):
                            start_idx = j * partition_length
                            end_idx = start_idx + partition_length
                            # 计算每个分区中top_indices的数量
                            for k in range(top_indices_sorted.shape[0]):  # 遍历每个压缩的状态
                                count_in_partition = np.sum((top_indices_sorted[k, :] >= start_idx) & (top_indices_sorted[k, :] < end_idx))
                                partition_scores[k, j] = count_in_partition / 50.0  # 计算比例
                        
                        per_layer_scores[layer_idx] = partition_scores
                        
                        mask = np.zeros_like(similarity_matrix_np, dtype=bool)
                        for i in range(similarity_matrix_np.shape[0]):
                            mask[i, top_indices[i]] = True

                        ax = axs[idx]
                        ax.imshow(similarity_matrix_np, cmap='Reds', aspect='auto', alpha=0.3) 
                        ax.imshow(mask, cmap='hot', aspect='auto', alpha=0.9)
                        ax.imshow(green_mask, aspect='auto', alpha=0.3)  # 显示红色掩码

                        # 绘制竖线表示切分位置
                        for j in range(1, num_partitions):
                            ax.axvline(x=j * partition_length, color='yellow', linestyle='--', linewidth=20)

                        # ax.set_title(f"Layer {layer_idx}", fontsize=24)
                        # print_c(f"Layer {layer_idx} partition_scores:\n{partition_scores * 100}", "yellow")
                        
                    # 调整子图位置
                    plt.tight_layout()
                    plt.savefig(f"analysis/figures/cosine_similarity_heatmap_offset-{offset}.png")

                    # 绘制 per_layer_scores 折线图
                    fig, axs = plt.subplots(nrows=1, ncols=5, figsize=(25, 5))
                    axs = axs.flatten()

                    x_labels = ['20%', '40%', '60%', '80%', '100%']
                    x_positions = np.arange(len(x_labels))
                    
                    for index, j in enumerate(per_layer_scores.keys()):
                        for k in range(per_layer_scores[j].shape[0]):  # 循环每一种压缩程度
                            axs[index].plot(x_positions, per_layer_scores[j][k, :], marker='o', label=f'Conv1d-State-{k}')
                        axs[index].set_xticks(x_positions)
                        axs[index].set_xticklabels(x_labels)
                        axs[index].set_xlabel('Percentage of Text')
                        axs[index].set_ylabel('Percentage of Top Indices')
                        axs[index].set_title(f'Layer {j+1}')
                        axs[index].legend()  # 将图例放在右上角

                    plt.tight_layout()
                    plt.savefig(f"analysis/figures/partition_scores_line_plot_offset-{offset}.png")

                    sub_files.clear()  # 存储下一组数据

                    pbar.update(5)   


##############################
#### 3. analysis_forget  ####
##############################

class ForgetAnalysis:
    def __init__(self, ctx_dir, save_root_dir) -> None:
        auto_mkdir(save_root_dir)
        all_layer_subdirs = list_subdirs(ctx_dir)
        for subdir in all_layer_subdirs:
            dir_name = os.path.basename(subdir)
            layer_subdirs = list_subdirs(subdir)
            num_subdirs = len(layer_subdirs)

            # 创建一个足够大的子图布局
            nrows = int(np.ceil(np.sqrt(num_subdirs)))
            ncols = nrows
            fig, axs = plt.subplots(nrows, ncols, figsize=(15, 15))  # 调整大小
            fig.subplots_adjust(hspace=0.4, wspace=0.4)  # 调整子图之间的间距

            for idx, layer_dir in enumerate(layer_subdirs):
                layer_name = os.path.basename(layer_dir)
                save_mark = f"{dir_name}-{layer_name}"
                ax = axs[idx // ncols, idx % ncols]  # 定位当前子图
                self.analysis_single_dir_hidden_state(layer_dir, save_mark, save_root_dir, ax)

            # 隐藏空白子图
            for idx in range(num_subdirs, nrows*ncols):
                axs[idx // ncols, idx % ncols].axis('off')

            # 保存整个子图集合
            plt.savefig(os.path.join(save_root_dir, f"{dir_name}_all_layers.png"))
            plt.close(fig)  # 关闭图形，释放内存

    def analysis_single_dir_hidden_state(self, dir, save_mark=None, save_root_dir=None, ax=None):
        """
        anchor_states is (1, 4096) vector
        hidden_states is (n, 4096) matrix
        """
        
        all_files = auto_read_dir(dir, file_suffix=".pkl", file_prefix="hidden_state")
        anchor_file = auto_read_dir(dir, file_suffix=".pkl", file_prefix="first_hidden_state")

        anchor_vector = auto_read_data(anchor_file[0])
        if anchor_vector.dim() == 3:
            anchor_vector = anchor_vector.squeeze(0)

        all_hidden_states = []
        for file in all_files:
            hidden_state = auto_read_data(file)
            if hidden_state.dim() == 3:
                hidden_state = hidden_state.squeeze(0)
            all_hidden_states.append(hidden_state)

        all_hidden_states = torch.cat(all_hidden_states, dim=0)
        cos_sim = F.cosine_similarity(anchor_vector, all_hidden_states)
        cos_sim = np.abs(cos_sim.float().cpu().numpy())
        
        # 使用传入的ax作为绘图的轴
        ax.plot(cos_sim)
        ax.set_title(save_mark)
        ax.set_xlabel('Generation Step')
        ax.set_ylabel('Cosine Similarity')
        

##############################
#### 3. analysis_salicy  ####
##############################
class SalicyAnalysis:
    def __init__(self, file_path) -> None:
        self.content = auto_read_data(file_path)
        self.analysis_single_file()

    def analysis_single_file(self, save_mark=None, save_root_dir=None, ax=None):
        num_layers, num_exp = len(self.content[0]), len(self.content)
        # 假设 self.content 是您的数据
        # 构造热力图的数据
        heatmap_data = np.zeros((num_layers, num_exp))  # 初始化一个全零矩阵
        for i in range(num_layers):
            for j in range(num_exp):
                heatmap_data[i, j] = self.content[j][i]['proportion'].item()

        # 绘制热力图
        plt.figure(figsize=(12, 8))
        plt.imshow(heatmap_data, cmap='viridis', aspect='auto')  # 使用viridis颜色地图，调整纵横比
        plt.colorbar()
        plt.xlabel('Experiment Index')
        plt.ylabel('Layer')
        plt.title('Proportion Heatmap')
        plt.tight_layout()
        plt.savefig("/nvme/zecheng/evaluation/analysis/proportion_heatmap.png")



if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--dir", "-d", type=str, default="analysis/inner_state")
    parser.add_argument("--fpath", "-f", type=str, default=None)
    parser.add_argument("--tokenizer_name_or_path", "-tkp", type=str, default="/nvme/hf_models/EleutherAI/gpt-neox-20b")
    parser.add_argument("--analysis_task", "-at", type=str, default="low_rank")
    parser.add_argument("--save_dir", "-sd", type=str, default="low_rank")
    args = parser.parse_args() 
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_name_or_path)

    save_root_dir = os.path.join(args.save_dir, args.analysis_task)

    if "passkey" in args.analysis_task.lower():

        passkey = "The best thing to do in San Francisco is eat a sandwich and sit in Dolores Park on a sunny day."
        passkey_length = len(tokenizer(passkey)['input_ids'])

        # anaylsis_single_file_conv1d(args.dir, passkey_length)

    elif "rank" in args.analysis_task.lower():
        # all_rks = analysis_multi_hidden_states(args.dir)
        # print_c(f"all_rks: {all_rks}", "yellow")
        ...

    elif "forget" in args.analysis_task.lower():
        
        log_c(f"begin to analysis forget ...\nsave results to {save_root_dir}", "yellow")

        analysisor = ForgetAnalysis(args.dir, save_root_dir)

    elif "salicy" in args.analysis_task.lower():
        
        analysisor = SalicyAnalysis(args.fpath)