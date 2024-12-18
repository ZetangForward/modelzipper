# read data
import openpyxl  
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.pyplot import MultipleLocator

# golbal config
# plt.rcParams['font.weight'] = 'bold'
bar_width = 0.25
opacity = 0.7
fig, ax = plt.subplots(figsize=(8,6))  

# 加载工作簿（将路径替换为您的文件路径）  
workbook = openpyxl.load_workbook('save_figs/data.xlsx')  
  
# 获取工作表（这将获取第一个工作表，如果有多个，请根据需要修改）  
worksheet = workbook.active  
  
# 创建一个空列表以保存数据  
data = []  
  
# 通过行和列迭代数据并保存到列表中  
for row in worksheet.iter_rows(min_row=1, max_row=13, min_col=5, max_col=11):  
    row_data = []  
    for cell in row:  
        row_data.append(cell.value)  
    data.append(row_data)  
  
# 关闭工作簿  
workbook.close()  

toxic_portation = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
# str_toxic_portation = 
str_toxic_portation = ['<0.3','0.4','0.5','0.6','0.7','0.8','>0.8']
prompt_portion = data[1]
prompt_toxicity = data[2]
llama_toxicity = data[3]
gptxl_toxicity = data[4]
dexperts_toxicity = data[5]
gedi_toxicity = data[6]
sgeat_toxicity = data[7]
mask_llama_toxicity = data[8]
mask_gptxl_toxicity = data[9]
mask_dexperts_toxicity = data[10]
mask_gedi_toxicity = data[11]
mask_sgeat_toxicity = data[12]

index = np.arange(len(toxic_portation))  

dexperts_toxicity = [eval(i) for i in dexperts_toxicity]
gedi_toxicity = [eval(i) for i in gedi_toxicity]

gptxl_toxicity = [min(eval(i), 0.25) for i in gptxl_toxicity]
plt.plot(index , gptxl_toxicity, linewidth=2, marker='o', label='GPT2-XL', alpha=opacity, color='orange') 
plt.plot(index + bar_width, gedi_toxicity, linewidth=2, marker='o', label='Gedi', alpha=opacity, color='g')  
plt.plot(index + bar_width*2, dexperts_toxicity, linewidth=2, marker='o', label='DExperts', alpha=opacity, color='c')  
# plt.plot(index + bar_width*2, sgeat_toxicity, linewidth=2, marker='o', label='SGEAT', alpha=opacity, color='orange') 

plt.ylim(0.0, 0.32)

ax.set_yticks([0.0, 0.1, 0.2, 0.25])
ax.set_yticklabels(["0.0", "0.1", "0.2", ">0.25"])
plt.xlabel('Context Toxicity', fontsize=16, fontname= 'DejaVu Sans Mono', fontweight=600, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=1))  
# plt.ylabel('Generation Toxicity', fontsize=16, fontname='DejaVu Sans Mono', fontweight=600,bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=1))   
plt.xticks(index + 1*bar_width, str_toxic_portation, fontsize=16, fontname='DejaVu Sans Mono', fontweight=600)  
plt.yticks(fontsize=16, fontname='DejaVu Sans Mono', fontweight=600) 
ax.yaxis.grid(True, linewidth=0.5, color='gray')
plt.legend(loc='upper left', prop={'family': 'DejaVu Sans Mono', 'weight': 600, 'size': 14})  

ax2 = ax.twinx()  
# ax2.set_ylabel('Generation Toxicity[MASK]', fontsize=14, fontname= 'DejaVu Sans Mono', fontweight=600,bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=1))  
plt.ylim(0, 0.32)
ax2.set_yticks([0.0, 0.1, 0.2, 0.25])
ax2.set_yticklabels(["0.0", "0.1", "0.2", ">0.25"])

mask_sgeat_toxicity = [eval(i) for i in mask_sgeat_toxicity]
mask_gedi_toxicity = [eval(i) for i in mask_gedi_toxicity]
mask_dexperts_toxicity = [eval(i) for i in mask_dexperts_toxicity]

plt.bar(index, mask_sgeat_toxicity, bar_width, alpha=opacity, color='orange', label='GPT2-XL[MASK]') 
plt.bar(index + bar_width, mask_gedi_toxicity, bar_width, alpha=opacity, color='g', label='Gedi[MASK]')  
plt.bar(index + bar_width*2, mask_dexperts_toxicity, bar_width, alpha=opacity, color='c', label='DExperts[MASK]') 
# plt.bar(index + bar_width*2, mask_sgeat_toxicity, bar_width, alpha=opacity, color='orange', label='SGEAT[MASK]') 

plt.yticks(fontsize=16, fontname= 'DejaVu Sans Mono', fontweight=600)  
ax2.legend(loc='upper right', prop={'family': 'DejaVu Sans Mono', 'weight': 600, 'size': 14})  

plt.tight_layout()     
plt.savefig(r"save_figs/pre_toxic_no_legend.pdf")




