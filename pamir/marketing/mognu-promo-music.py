import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
SR=48000; DUR=41.0; N=int(SR*DUR); rng=np.random.default_rng(33)
def lp(x,f): return sosfilt(butter(2,f/(SR/2),'low',output='sos'),x)
def hp(x,f): return sosfilt(butter(2,f/(SR/2),'high',output='sos'),x)
def hz(m): return 440*2**((m-69)/12)
def env(n,a=.005,r=.2): t=np.arange(n)/SR; return np.minimum(1,t/max(a,1e-4))*np.exp(-t/r)
def place(b,x,t,g=1):
    i=int(t*SR); j=min(N,i+len(x))
    if i<N: b[i:j]+=x[:j-i]*g
def tone(f,n,r=.3,a=.005,saw=False):
    t=np.arange(n)/SR; w=(2*((t*f)%1)-1) if saw else np.sin(2*np.pi*f*t); return w*env(n,a,r)
mus=np.zeros(N); sfx=np.zeros(N)
# 0–3.1 тихое вступление (шёпот): мягкий пад + тиканье
n=int(3.2*SR); t=np.arange(n)/SR
place(mus,sum(tone(hz(m),n,9,.6) for m in (57,60,64))*.06*np.minimum(1,(3.2-t)/.15),0)
for k in np.arange(.3,3.0,.5): place(sfx,hp(rng.standard_normal(500),4500)*env(500,.0005,.006)*.12,k)
# удары на сменах сцен
def boom(): m=int(.6*SR); tt=np.arange(m)/SR; return np.sin(2*np.pi*np.cumsum(45+140*np.exp(-tt*22))/SR)*np.exp(-tt*5)+lp(rng.standard_normal(m),2500)*np.exp(-tt*10)*.4
def whoosh(): m=int(.45*SR); tt=np.arange(m)/SR; return hp(rng.standard_normal(m),1200)*np.sin(np.pi*tt/.45)**2
def pop(f=900): m=int(.18*SR); tt=np.arange(m)/SR; return np.sin(2*np.pi*np.cumsum(f+600*tt/.18)/SR)*env(m,.002,.05)
def ding(base=84): 
    m=int(.9*SR); return sum(tone(hz(base+x),m,.35) for x in (0,4,7))/3
place(sfx,boom()*.7,3.1)
for tt_ in (5.0,9.7,13.7,18.2,22.3,27.0,31.2,34.25): place(sfx,whoosh()*.22,tt_-.2)
place(sfx,boom()*.5,7.0)            # нажатие кнопки
place(sfx,ding(84)*.25,6.1)          # «подключён»
for j in range(4): place(sfx,pop(700+j*120)*.3,9.7+j*.55)       # флаги
place(sfx,tone(hz(45),int(.5*SR),.2,saw=True)*.12,13.9)          # «режет» — бззз
place(sfx,ding(79)*.25,15.3)                                       # LTE включился
m=int(1.1*SR); tt=np.arange(m)/SR; place(sfx,lp(rng.standard_normal(m),1800)*np.sin(np.pi*tt/1.1)**2*.25,18.2)  # самолёт
for j in range(5): place(sfx,pop(500+j*90)*.28,22.3+j*.22)       # окна рекламы
for j in range(10): place(sfx,lp(rng.standard_normal(int(.08*SR)),900)*env(int(.08*SR),.001,.03)*.4,24.4+j*.15)  # ням-ням
for j in range(3): place(sfx,pop(800+j*150)*.3,27.0+j*.35)        # устройства
place(sfx,boom()*.5,31.2); place(sfx,ding(88)*.3,31.6)            # подарок
place(sfx,boom()*.6,33.05)
for j in range(2): place(sfx,ding(84+j*5)*.22,34.4+j*2.5)         # адреса
# 3.1–41 бит 118 bpm
bpm=118; beat=60/bpm; t0=3.1
def kick(): m=int(.32*SR); tt=np.arange(m)/SR; return np.sin(2*np.pi*np.cumsum(50+120*np.exp(-tt*30))/SR)*np.exp(-tt*8)
def hat(): m=int(.05*SR); return hp(rng.standard_normal(m),7000)*env(m,.0005,.015)
def clap(): m=int(.2*SR); return hp(rng.standard_normal(m),1500)*env(m,.001,.05)
chords=[(60,64,67),(57,60,64),(53,57,60),(55,59,62)]; bass=[48,45,41,43]
mel=[72,76,79,76,72,74,76,79,77,76,74,72,74,76,79,84]
for i in range(200):
    tb=t0+i*beat
    if tb>DUR-.5: break
    place(mus,kick()*.6,tb)
    if i%2: place(mus,clap()*.3,tb)
    place(mus,hat()*.15,tb+beat/2)
    if i%4==0:
        c=chords[(i//4)%4]; m=int(beat*4*SR)
        place(mus,lp(sum(tone(hz(x),m,1.2,.01,True) for x in c),2400)*.07,tb)
    place(mus,lp(tone(hz(bass[(i//4)%4]),int(beat*SR),.18,.004,True),600)*.22,tb)
    if i%2==0: place(mus,tone(hz(mel[(i//2)%16]),int(.28*SR),.12)*.08,tb+beat/2)
fade=np.ones(N); fl=int(1.0*SR); fade[-fl:]=np.linspace(1,0,fl)
sr,vo=wavfile.read('vo.wav'); vo=vo.astype(np.float64)/32768; vo=np.pad(vo,(0,max(0,N-len(vo))))[:N]
e=np.convolve(np.abs(vo),np.ones(int(.08*SR))/int(.08*SR),'same'); duck=1-.6*np.clip(e/(e.max()*.2),0,1)
duck=np.convolve(duck,np.ones(int(.15*SR))/int(.15*SR),'same')
out=(mus*duck*.85+sfx*.8)*fade+vo*1.15
out=out/np.abs(out).max()*.95
wavfile.write('mix.wav',SR,np.stack([out,out],1).astype(np.float32)); print('ok')
