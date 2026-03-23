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

plt.figure(figsize=(8, 5)) # Set a good figure size

plt.plot(filtered_x, filtered_times, 
         marker='o',           
         markersize=10,
         linestyle='-',        
         linewidth=2,          
         color='#ff8c42',     
         markeredgecolor='#ff8c42',
         markerfacecolor="white",
         zorder=3)
plt.xticks(target_ticks, fontsize=11)
plt.yticks(fontsize=11)

plt.xlim(left=20)
plt.grid(True, linestyle='--', alpha=0.6, zorder=0) # Zorder 0 keeps the grid behind the points
plt.xlabel("No. of qubits ($n$)", fontsize=12, fontweight='bold')
plt.ylabel("Time (seconds)", fontsize=12, fontweight='bold')
plt.title("Minizinc Execution Times", fontsize=14, fontweight='bold')

plt.tight_layout() # Ensures nothing gets cut off
plt.savefig("distance_plot.png", dpi=300)
