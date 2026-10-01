import sys,numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
d=np.load(sys.argv[1]); B,J=d['B'],d['J']
fig,axs=plt.subplots(2,4,figsize=(18,9))
for ax,y0 in zip(axs[0],(-0.04,-0.01,0.02,0.05)):
    for V,c in ((B,'k'),(J,'b')):
        s=(abs(V[:,1]-y0)<0.004)&(abs(V[:,0])<0.12)&(V[:,2]>0.6)&(V[:,2]<0.85)
        ax.scatter(V[s,0],V[s,2],s=1,c=c)
    ax.set_title(f"front slab y={y0}"); ax.set_aspect('equal'); ax.grid(1)
for ax,x0 in zip(axs[1],(0.0,0.02,0.04,0.07)):
    for V,c in ((B,'k'),(J,'b')):
        s=(abs(V[:,0]-x0)<0.004)&(V[:,2]>0.6)&(V[:,2]<0.9)
        ax.scatter(V[s,1],V[s,2],s=1,c=c)
    ax.set_title(f"side slab x={x0}"); ax.set_aspect('equal'); ax.grid(1)
plt.tight_layout(); plt.savefig(sys.argv[2],dpi=70)
