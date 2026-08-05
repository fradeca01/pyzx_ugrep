import matplotlib.pyplot as plt

x_values = []
times = []
with open("mzn_times2") as f:
    for l in f.readlines():
        parts = l.strip().split(',')
        if len(parts) == 2:
            x_values.append(int(parts[0]))   
            times.append(float(parts[1]))   


target_ticks = [x for x in x_values if x > 20]
filtered_x = []
filtered_times = []

for x, t in zip(x_values, times):
    if x in target_ticks:
        filtered_x.append(x)
        filtered_times.append(t)

plt.figure(figsize=(4, 2)) 

plt.plot(filtered_x, filtered_times, 
         marker='.',           
         markersize=5,
         linestyle='-',        
         linewidth=1,          
         color='#ff8c42',     
         markeredgecolor='#ff8c42',
         markerfacecolor="#ff8c42",
         zorder=3)
plt.xticks(target_ticks, fontsize=6)
plt.yticks(fontsize=6)

plt.xlim(left=20)
plt.grid(True, linestyle='--', alpha=0.6, zorder=0) 
plt.xlabel("No. of qubits ($n$)", fontsize=6)
plt.ylabel("Time (seconds)", fontsize=6)
plt.title("Minizinc Execution Times", fontsize=8)

plt.tight_layout(pad=0.2)
plt.savefig(
    "distance_plot.png",
    dpi=1200,
    bbox_inches="tight",
    pad_inches=0.02,
)

plt.show()